from __future__ import annotations

import base64
import io
import json
import os
import struct
import sys
from pathlib import Path

import pytest

from agent_quota.dto import RendererContract
from agent_quota.errors import ContractViolation
from agent_quota.native_control import NativeControlPlane
from agent_quota.sidecar import (
    MAX_FRAME_BYTES,
    SidecarSession,
    main,
    read_exact,
    read_frame,
    read_session_secret,
    serve,
    session_proof,
    write_frame,
)


def envelope(
    secret: bytes,
    *,
    request_id: int = 1,
    budget: int = 1,
    command_id: str = "bootstrap_state",
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    value: dict[str, object] = {
        "request_id": request_id,
        "remaining_budget_ns": budget,
        "command_id": command_id,
        "payload": {} if payload is None else payload,
    }
    value["session_proof"] = session_proof(secret, value)
    return value


def test_frame_round_trip_and_big_endian() -> None:
    stream = io.BytesIO()
    write_frame(stream, {"ok": True})
    raw = stream.getvalue()
    assert struct.unpack(">I", raw[:4])[0] == len(raw) - 4
    assert read_frame(io.BytesIO(raw)) == {"ok": True}


@pytest.mark.parametrize(
    "raw",
    [
        b"\x00\x00\x00\x00",
        struct.pack(">I", MAX_FRAME_BYTES + 1),
        b"\x00\x00\x00\x02{",
        b"\x00\x00\x00\x01x",
        b"\x00\x00\x00\x01" + b"1",
    ],
)
def test_invalid_frames_fail_closed(raw: bytes) -> None:
    with pytest.raises((ContractViolation, EOFError)):
        read_frame(io.BytesIO(raw))


def test_negative_read_and_oversize_response_fail_closed() -> None:
    with pytest.raises(ContractViolation):
        read_exact(io.BytesIO(), -1)
    with pytest.raises(ContractViolation):
        write_frame(io.BytesIO(), {"large": "x" * MAX_FRAME_BYTES})


def test_secret_is_read_from_independent_fd_and_closed() -> None:
    read_fd, write_fd = os.pipe()
    secret = b"s" * 32
    os.write(write_fd, secret)
    os.close(write_fd)
    assert read_session_secret({"AQ_SESSION_SECRET_FD": str(read_fd)}) == secret
    with pytest.raises(OSError):
        os.fstat(read_fd)


def test_secret_pipe_rejects_missing_invalid_and_trailing_data() -> None:
    for environment in ({}, {"AQ_SESSION_SECRET_FD": "nope"}, {"AQ_SESSION_SECRET_FD": "2"}):
        with pytest.raises(ContractViolation):
            read_session_secret(environment)
    read_fd, write_fd = os.pipe()
    os.write(write_fd, b"x" * 33)
    os.close(write_fd)
    with pytest.raises(ContractViolation, match="trailing"):
        read_session_secret({"AQ_SESSION_SECRET_FD": str(read_fd)})


def test_session_rejects_bad_proof_reorder_budget_and_extra_fields() -> None:
    secret = b"k" * 32
    session = SidecarSession(secret, RendererContract())
    bad = envelope(secret)
    bad["session_proof"] = "0" * 64
    with pytest.raises(ContractViolation):
        session.dispatch(bad)
    with pytest.raises(ContractViolation):
        session.dispatch(envelope(secret, request_id=2))
    with pytest.raises(ContractViolation):
        session.dispatch(envelope(secret, budget=0))
    injected = envelope(secret)
    injected["url"] = "https://example.invalid"
    with pytest.raises(ContractViolation):
        session.dispatch(injected)
    wrong_shape = envelope(secret)
    wrong_shape["command_id"] = 7
    wrong_shape["session_proof"] = session_proof(secret, wrong_shape)
    with pytest.raises(ContractViolation):
        session.dispatch(wrong_shape)


def test_all_ten_commands_return_contract_valid_responses() -> None:
    secret = b"q" * 32
    session = SidecarSession(secret, RendererContract())
    requests = [
        ("bootstrap_state", {}),
        ("accounts_read", {"scope_ref": "scope"}),
        ("quota_overview", {"scope_ref": "scope"}),
        ("refresh_scope", {"scope_ref": "scope"}),
        (
            "config_validate_apply",
            {"config_change_set": {"changes": [], "expected_generation": 0}},
        ),
        ("credential_dialog_open", {"dialog_purpose": "create-credential-reference"}),
        (
            "destructive_confirmation_open",
            {"operation_intent": "purge", "opaque_selection_handle": "selection"},
        ),
        ("reauthenticate", {"principal_ref": "principal"}),
        (
            "export_redacted",
            {"export_profile": "redacted-diagnostics", "scope_ref": "scope"},
        ),
        ("scheduler_state", {}),
    ]
    for request_id, (command_id, payload) in enumerate(requests, start=1):
        response = session.dispatch(
            envelope(
                secret,
                request_id=request_id,
                command_id=command_id,
                payload=payload,
            )
        )
        assert response["request_id"] == request_id
        assert isinstance(response["response"], dict)
        assert len(json.dumps(response)) < MAX_FRAME_BYTES


def test_serve_processes_one_frame_then_clean_eof() -> None:
    secret = b"z" * 32
    input_stream = io.BytesIO()
    write_frame(input_stream, envelope(secret))
    input_stream.seek(0)
    output_stream = io.BytesIO()
    serve(input_stream, output_stream, secret)
    output_stream.seek(0)
    response = read_frame(output_stream)
    assert response["request_id"] == 1


def test_main_maps_contract_failure_and_clean_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agent_quota.sidecar.read_session_secret", lambda: b"x" * 32)
    monkeypatch.setattr("agent_quota.sidecar.serve", lambda *_args: None)
    monkeypatch.setattr("agent_quota.sidecar.NativeControlPlane", lambda _path: None)
    monkeypatch.setattr(sys, "argv", ["agent-quota-sidecar", "--data-root", "/tmp/agent-quota"])
    assert main() == 0

    def fail() -> bytes:
        raise ContractViolation("no secret")

    monkeypatch.setattr("agent_quota.sidecar.read_session_secret", fail)
    assert main() == 64

    monkeypatch.setattr("agent_quota.sidecar.read_session_secret", lambda: b"x" * 32)

    def bad_native_state(_path: Path) -> None:
        raise ValueError("invalid native state")

    monkeypatch.setattr("agent_quota.sidecar.NativeControlPlane", bad_native_state)
    assert main() == 64


def test_internal_credential_and_destructive_commands_are_host_only(tmp_path: Path) -> None:
    secret = b"i" * 32
    native = NativeControlPlane((tmp_path / "private").absolute())
    session = SidecarSession(secret, RendererContract(), native)
    session.dispatch(
        envelope(
            secret,
            request_id=1,
            command_id="host_internal.credential_prepare",
            payload={"credential_reference": "credential-00000000-0000-4000-8000-000000000001"},
        )
    )
    created = session.dispatch(
        envelope(
            secret,
            request_id=2,
            command_id="host_internal.credential_commit",
            payload={
                "credential_reference": "credential-00000000-0000-4000-8000-000000000001",
                "expected_generation": None,
                "principal_ref": None,
                "provider_id": "deepseek",
                "purpose": "create-credential-reference",
            },
        )
    )["response"]
    principal = created["principal_ref"]
    accounts = session.dispatch(
        envelope(
            secret,
            request_id=3,
            command_id="accounts_read",
            payload={"scope_ref": "scope-all"},
        )
    )["response"]["accounts"]
    assert accounts == [
        {
            "display_label": "DeepSeek",
            "lifecycle": "active",
            "principal_ref": principal,
        }
    ]
    assert "credential" not in json.dumps(accounts)
    context = session.dispatch(
        envelope(
            secret,
            request_id=4,
            command_id="host_internal.credential_context",
            payload={"principal_ref": principal},
        )
    )["response"]
    assert context["credential_reference"].endswith("000000000001")
    assert context["provider_id"] == "deepseek"
    session.dispatch(
        envelope(
            secret,
            request_id=5,
            command_id="host_internal.credential_prepare",
            payload={"credential_reference": "credential-00000000-0000-4000-8000-000000000002"},
        )
    )
    plan = session.dispatch(
        envelope(
            secret,
            request_id=6,
            command_id="host_internal.destructive_prepare",
            payload={
                "operation_intent": "purge",
                "opaque_selection_handle": "selection-all-local-data",
            },
        )
    )["response"]
    cancelled = session.dispatch(
        envelope(
            secret,
            request_id=7,
            command_id="host_internal.destructive_cancel",
            payload={"plan_id": plan["plan_id"]},
        )
    )["response"]
    assert cancelled == {"status": "cancelled"}
    plan = session.dispatch(
        envelope(
            secret,
            request_id=8,
            command_id="host_internal.destructive_prepare",
            payload={
                "operation_intent": "purge",
                "opaque_selection_handle": "selection-all-local-data",
            },
        )
    )["response"]
    committed = session.dispatch(
        envelope(
            secret,
            request_id=9,
            command_id="host_internal.destructive_commit",
            payload={
                "digest": plan["digest"],
                "generation": plan["generation"],
                "nonce": plan["nonce"],
                "plan_id": plan["plan_id"],
                "user_presence_token": "00000000-0000-4000-8000-000000000001",
            },
        )
    )["response"]
    assert committed == {
        "cleanup_references": [
            "credential-00000000-0000-4000-8000-000000000002",
            "credential-00000000-0000-4000-8000-000000000001",
        ],
        "status": "committed",
    }
    pending = session.dispatch(
        envelope(
            secret,
            request_id=10,
            command_id="host_internal.cleanup_pending",
            payload={},
        )
    )["response"]
    assert pending["references"] == committed["cleanup_references"]
    acknowledged = session.dispatch(
        envelope(
            secret,
            request_id=11,
            command_id="host_internal.cleanup_ack",
            payload={"references": pending["references"]},
        )
    )["response"]
    assert acknowledged == {"status": "acknowledged"}
    pending = session.dispatch(
        envelope(
            secret,
            request_id=12,
            command_id="host_internal.cleanup_pending",
            payload={},
        )
    )["response"]
    assert pending["references"] == []
    with pytest.raises(ContractViolation):
        session.dispatch(
            envelope(
                secret,
                request_id=13,
                command_id="host_internal.destructive_commit",
                payload={
                    "digest": plan["digest"],
                    "generation": plan["generation"],
                    "nonce": plan["nonce"],
                    "plan_id": plan["plan_id"],
                    "user_presence_token": "00000000-0000-4000-8000-000000000001",
                },
            )
        )


def test_internal_provider_response_is_fenced_persisted_and_renderer_safe(tmp_path: Path) -> None:
    secret = b"p" * 32
    native = NativeControlPlane((tmp_path / "private-provider").absolute())
    session = SidecarSession(secret, RendererContract(), native)
    session.dispatch(
        envelope(
            secret,
            request_id=1,
            command_id="host_internal.credential_prepare",
            payload={"credential_reference": "credential-00000000-0000-4000-8000-000000000009"},
        )
    )
    created = session.dispatch(
        envelope(
            secret,
            request_id=2,
            command_id="host_internal.credential_commit",
            payload={
                "credential_reference": "credential-00000000-0000-4000-8000-000000000009",
                "expected_generation": None,
                "principal_ref": None,
                "provider_id": "deepseek",
                "purpose": "create-credential-reference",
            },
        )
    )["response"]
    principal = created["principal_ref"]
    context = session.dispatch(
        envelope(
            secret,
            request_id=3,
            command_id="host_internal.credential_context",
            payload={"principal_ref": principal},
        )
    )["response"]
    body = base64.b64encode(
        json.dumps(
            {
                "is_available": True,
                "balance_infos": [{"currency": "USD", "total_balance": "7"}],
            }
        ).encode()
    ).decode()
    committed = session.dispatch(
        envelope(
            secret,
            request_id=4,
            command_id="host_internal.provider_response_commit",
            payload={
                "body_base64": body,
                "expected_generation": context["generation"],
                "http_status": 200,
                "principal_ref": principal,
                "provider_id": context["provider_id"],
            },
        )
    )["response"]
    assert committed == {"retryable": False, "safe_error_code": None, "status": "committed"}
    overview = session.dispatch(
        envelope(
            secret,
            request_id=5,
            command_id="quota_overview",
            payload={"scope_ref": "scope-all"},
        )
    )["response"]
    serialized = json.dumps(overview)
    assert "USD 7" in serialized
    assert "credential-" not in serialized
    assert body not in serialized
    failure = session.dispatch(
        envelope(
            secret,
            request_id=6,
            command_id="host_internal.provider_failure_commit",
            payload={
                "expected_generation": context["generation"],
                "principal_ref": principal,
                "provider_id": context["provider_id"],
                "safe_error_code": "keychain-locked",
            },
        )
    )["response"]
    assert failure == {"status": "committed"}
    accounts = session.dispatch(
        envelope(
            secret,
            request_id=7,
            command_id="accounts_read",
            payload={"scope_ref": "scope-all"},
        )
    )["response"]["accounts"]
    assert accounts[0]["last_error_code"] == "keychain-locked"
    cached = session.dispatch(
        envelope(
            secret,
            request_id=8,
            command_id="quota_overview",
            payload={"scope_ref": "scope-all"},
        )
    )["response"]
    assert "USD 7" in json.dumps(cached)


def test_deep_provider_json_fails_without_losing_sidecar_session(tmp_path: Path) -> None:
    secret = b"j" * 32
    native = NativeControlPlane((tmp_path / "private-deep-json").absolute())
    session = SidecarSession(secret, RendererContract(), native)
    reference = "credential-00000000-0000-4000-8000-000000000019"
    session.dispatch(
        envelope(
            secret,
            request_id=1,
            command_id="host_internal.credential_prepare",
            payload={"credential_reference": reference},
        )
    )
    created = session.dispatch(
        envelope(
            secret,
            request_id=2,
            command_id="host_internal.credential_commit",
            payload={
                "credential_reference": reference,
                "expected_generation": None,
                "principal_ref": None,
                "provider_id": "deepseek",
                "purpose": "create-credential-reference",
            },
        )
    )["response"]
    principal = created["principal_ref"]
    context = session.dispatch(
        envelope(
            secret,
            request_id=3,
            command_id="host_internal.credential_context",
            payload={"principal_ref": principal},
        )
    )["response"]
    deep_body = base64.b64encode(b"[" * 1_000 + b"0" + b"]" * 1_000).decode()
    rejected = session.dispatch(
        envelope(
            secret,
            request_id=4,
            command_id="host_internal.provider_response_commit",
            payload={
                "body_base64": deep_body,
                "expected_generation": context["generation"],
                "http_status": 200,
                "principal_ref": principal,
                "provider_id": context["provider_id"],
            },
        )
    )["response"]
    assert rejected == {
        "retryable": False,
        "safe_error_code": "contract-error",
        "status": "rejected",
    }
    good_body = base64.b64encode(
        json.dumps(
            {"is_available": True, "balance_infos": [{"currency": "CNY", "total_balance": 1}]}
        ).encode()
    ).decode()
    accepted = session.dispatch(
        envelope(
            secret,
            request_id=5,
            command_id="host_internal.provider_response_commit",
            payload={
                "body_base64": good_body,
                "expected_generation": context["generation"],
                "http_status": 200,
                "principal_ref": principal,
                "provider_id": context["provider_id"],
            },
        )
    )["response"]
    assert accepted == {"retryable": False, "safe_error_code": None, "status": "committed"}
