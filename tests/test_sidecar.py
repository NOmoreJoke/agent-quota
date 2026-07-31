from __future__ import annotations

import io
import json
import os
import struct

import pytest

from agent_quota.dto import RendererContract
from agent_quota.errors import ContractViolation
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
    assert main() == 0

    def fail() -> bytes:
        raise ContractViolation("no secret")

    monkeypatch.setattr("agent_quota.sidecar.read_session_secret", fail)
    assert main() == 64
