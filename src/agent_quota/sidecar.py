"""Anonymous-pipe sidecar entrypoint with closed, bounded framing."""

from __future__ import annotations

import hmac
import json
import os
import struct
import sys
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import BinaryIO, Final, cast

from agent_quota.dto import RendererContract
from agent_quota.errors import ContractViolation
from agent_quota.native_control import NativeControlPlane

MAX_FRAME_BYTES: Final = 1024 * 1024
MAX_REMAINING_BUDGET_NS: Final = 9_000_000_000
SESSION_SECRET_BYTES: Final = 32
ENVELOPE_FIELDS: Final = {
    "command_id",
    "payload",
    "remaining_budget_ns",
    "request_id",
    "session_proof",
}
INTERNAL_COMMANDS: Final = {
    "host_internal.cleanup_ack",
    "host_internal.cleanup_pending",
    "host_internal.credential_context",
    "host_internal.credential_candidate_create",
    "host_internal.credential_commit",
    "host_internal.credential_prepare",
    "host_internal.destructive_cancel",
    "host_internal.destructive_commit",
    "host_internal.destructive_prepare",
    "host_internal.provider_response_commit",
    "host_internal.provider_failure_commit",
}


def read_exact(stream: BinaryIO, length: int) -> bytes:
    if length < 0:
        raise ContractViolation("negative read length")
    output = bytearray()
    while len(output) < length:
        chunk = stream.read(length - len(output))
        if not chunk:
            raise EOFError("truncated sidecar frame")
        output.extend(chunk)
    return bytes(output)


def read_frame(stream: BinaryIO) -> dict[str, object]:
    length = struct.unpack(">I", read_exact(stream, 4))[0]
    if not 1 <= length <= MAX_FRAME_BYTES:
        raise ContractViolation("invalid sidecar frame size")
    body = read_exact(stream, length)
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContractViolation("invalid sidecar JSON frame") from error
    if not isinstance(value, dict):
        raise ContractViolation("sidecar frame must be an object")
    return value


def write_frame(stream: BinaryIO, value: dict[str, object]) -> None:
    body = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    if not 1 <= len(body) <= MAX_FRAME_BYTES:
        raise ContractViolation("invalid sidecar response size")
    stream.write(struct.pack(">I", len(body)))
    stream.write(body)
    stream.flush()


def _proof_body(envelope: dict[str, object]) -> bytes:
    unsigned = {key: value for key, value in envelope.items() if key != "session_proof"}
    return json.dumps(
        unsigned,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def session_proof(secret: bytes, envelope: dict[str, object]) -> str:
    return hmac.new(secret, _proof_body(envelope), sha256).hexdigest()


def read_session_secret(environment: dict[str, str] | None = None) -> bytes:
    env = os.environ if environment is None else environment
    raw_fd = env.get("AQ_SESSION_SECRET_FD")
    if raw_fd is None or not raw_fd.isascii() or not raw_fd.isdigit():
        raise ContractViolation("session secret pipe is unavailable")
    fd = int(raw_fd)
    if not 3 <= fd <= 2**31 - 1:
        raise ContractViolation("session secret descriptor is invalid")
    with os.fdopen(fd, "rb", closefd=True) as secret_stream:
        secret = read_exact(secret_stream, SESSION_SECRET_BYTES)
        if secret_stream.read(1):
            raise ContractViolation("session secret pipe contains trailing data")
    return secret


@dataclass
class SidecarSession:
    secret: bytes
    contract: RendererContract
    native: NativeControlPlane | None = None
    last_request_id: int = 0

    def dispatch(self, envelope: dict[str, object]) -> dict[str, object]:
        if set(envelope) != ENVELOPE_FIELDS:
            raise ContractViolation("sidecar envelope field closure mismatch")
        request_id = envelope["request_id"]
        budget = envelope["remaining_budget_ns"]
        command_id = envelope["command_id"]
        payload = envelope["payload"]
        proof = envelope["session_proof"]
        if (
            isinstance(request_id, bool)
            or not isinstance(request_id, int)
            or request_id != self.last_request_id + 1
            or request_id > 2**64 - 1
        ):
            raise ContractViolation("sidecar request order mismatch")
        if (
            isinstance(budget, bool)
            or not isinstance(budget, int)
            or not 1 <= budget <= MAX_REMAINING_BUDGET_NS
        ):
            raise ContractViolation("sidecar remaining budget mismatch")
        if not isinstance(command_id, str) or not isinstance(payload, dict):
            raise ContractViolation("sidecar request shape mismatch")
        if not isinstance(proof, str) or not hmac.compare_digest(
            proof,
            session_proof(self.secret, envelope),
        ):
            raise ContractViolation("sidecar session proof mismatch")

        internal = command_id in INTERNAL_COMMANDS
        if internal:
            _validate_internal_request(command_id, payload)
        else:
            self.contract.validate_command_request(command_id, payload)
        self.last_request_id = request_id
        response = self._dispatch(command_id, payload)
        if internal:
            _validate_internal_response(command_id, response)
        else:
            self.contract.validate_command_response(command_id, response)
        return {
            "request_id": request_id,
            "response": response,
            "session_proof": session_proof(
                self.secret,
                {"request_id": request_id, "response": response},
            ),
        }

    def _dispatch(self, command_id: str, payload: dict[str, object]) -> dict[str, object]:
        if command_id in INTERNAL_COMMANDS:
            if self.native is None:
                raise ContractViolation("native control plane is unavailable")
            return _internal_dispatch(self.native, command_id, payload)
        return _safe_dispatch(command_id, payload, self.native)


def _safe_dispatch(
    command_id: str,
    payload: dict[str, object],
    native: NativeControlPlane | None = None,
) -> dict[str, object]:
    if command_id == "bootstrap_state":
        return {
            "application_state": {"launch_state": "ready", "offline": False},
            "status": "ok",
        }
    if command_id == "accounts_read":
        return {
            "accounts": [] if native is None else native.renderer_accounts(),
            "status": "ok",
        }
    if command_id == "quota_overview":
        return {
            "projection": (
                {
                    "capability_rows": [],
                    "freshness": "stale",
                    "scope_ref": payload["scope_ref"],
                }
                if native is None
                else native.quota_projection(str(payload["scope_ref"]))
            ),
            "status": "ok",
        }
    if command_id == "refresh_scope":
        return {"refresh_state": {"phase": "completed"}, "status": "ok"}
    if command_id == "config_validate_apply":
        return {"classification": "nondestructive-applied", "status": "ok"}
    if command_id == "credential_dialog_open":
        return {"opaque_reference_status": "cancelled", "status": "cancelled"}
    if command_id == "destructive_confirmation_open":
        return {"status": "cancelled"}
    if command_id == "reauthenticate":
        return {
            "reauth_state": "failed",
            "safe_error": {"code": "reauth-required", "retryable": False},
            "status": "error",
        }
    if command_id == "export_redacted":
        return {"export_status": "cancelled", "status": "ok"}
    if command_id == "scheduler_state":
        return {
            "scheduler_state": {"health": "absent", "installed": False},
            "status": "ok",
        }
    raise ContractViolation("unknown renderer command")


def _exact(payload: dict[str, object], fields: set[str]) -> None:
    if set(payload) != fields:
        raise ContractViolation("internal payload field closure mismatch")


def _bounded_string(value: object, maximum: int = 128) -> str:
    if not isinstance(value, str) or not 1 <= len(value.encode()) <= maximum:
        raise ContractViolation("invalid internal string")
    return value


def _bounded_integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 2**63 - 1:
        raise ContractViolation("invalid internal integer")
    return value


def _bounded_string_list(value: object) -> list[str]:
    if (
        not isinstance(value, list)
        or not 1 <= len(value) <= 192
        or any(not isinstance(item, str) or not 1 <= len(item.encode()) <= 128 for item in value)
    ):
        raise ContractViolation("invalid internal string list")
    return value


def _validate_internal_request(command_id: str, payload: dict[str, object]) -> None:
    if command_id == "host_internal.cleanup_pending":
        _exact(payload, set())
    elif command_id == "host_internal.cleanup_ack":
        _exact(payload, {"references"})
        _bounded_string_list(payload["references"])
    elif command_id == "host_internal.credential_context":
        _exact(payload, {"principal_ref"})
        _bounded_string(payload["principal_ref"])
    elif command_id == "host_internal.credential_candidate_create":
        _exact(payload, set())
    elif command_id == "host_internal.credential_prepare":
        _exact(payload, {"credential_reference"})
        _bounded_string(payload["credential_reference"])
    elif command_id == "host_internal.credential_commit":
        _exact(
            payload,
            {
                "credential_reference",
                "expected_generation",
                "principal_ref",
                "provider_id",
                "purpose",
            },
        )
        _bounded_string(payload["credential_reference"])
        _bounded_string(payload["purpose"], 32)
        _bounded_string(payload["provider_id"], 32)
        if payload["principal_ref"] is not None:
            _bounded_string(payload["principal_ref"])
        if payload["expected_generation"] is not None:
            _bounded_integer(payload["expected_generation"])
    elif command_id == "host_internal.destructive_prepare":
        _exact(payload, {"opaque_selection_handle", "operation_intent"})
        _bounded_string(payload["operation_intent"], 32)
        _bounded_string(payload["opaque_selection_handle"])
    elif command_id == "host_internal.destructive_cancel":
        _exact(payload, {"plan_id"})
        _bounded_string(payload["plan_id"], 64)
    elif command_id == "host_internal.destructive_commit":
        _exact(
            payload,
            {"digest", "generation", "nonce", "plan_id", "user_presence_token"},
        )
        for field in ("digest", "nonce", "plan_id", "user_presence_token"):
            _bounded_string(payload[field], 128)
        _bounded_integer(payload["generation"])
    elif command_id == "host_internal.provider_failure_commit":
        _exact(
            payload,
            {"expected_generation", "principal_ref", "provider_id", "safe_error_code"},
        )
        _bounded_integer(payload["expected_generation"])
        _bounded_string(payload["principal_ref"])
        _bounded_string(payload["provider_id"], 32)
        _bounded_string(payload["safe_error_code"], 64)
    elif command_id == "host_internal.provider_response_commit":
        _exact(
            payload,
            {
                "body_base64",
                "expected_generation",
                "http_status",
                "principal_ref",
                "provider_id",
            },
        )
        _bounded_string(payload["body_base64"], 512 * 1024)
        _bounded_integer(payload["expected_generation"])
        status = _bounded_integer(payload["http_status"])
        if not 100 <= status <= 599:
            raise ContractViolation("invalid provider HTTP status")
        _bounded_string(payload["principal_ref"])
        _bounded_string(payload["provider_id"], 32)
    else:
        raise ContractViolation("unknown internal command")


def _validate_internal_response(command_id: str, payload: dict[str, object]) -> None:
    if command_id == "host_internal.cleanup_pending":
        _exact(payload, {"references", "status"})
        if payload["references"] != []:
            _bounded_string_list(payload["references"])
        _bounded_string(payload["status"], 32)
    elif command_id == "host_internal.cleanup_ack":
        _exact(payload, {"status"})
        _bounded_string(payload["status"], 32)
    elif command_id == "host_internal.credential_context":
        _exact(payload, {"credential_reference", "generation", "provider_id", "status"})
        _bounded_string(payload["credential_reference"])
        _bounded_integer(payload["generation"])
        _bounded_string(payload["provider_id"], 32)
    elif command_id == "host_internal.credential_candidate_create":
        _exact(payload, {"credential_reference", "status"})
        _bounded_string(payload["credential_reference"])
        if payload["status"] != "prepared":
            raise ContractViolation("invalid credential candidate status")
    elif command_id == "host_internal.credential_prepare":
        _exact(payload, {"status"})
        if payload["status"] != "prepared":
            raise ContractViolation("invalid credential prepare status")
    elif command_id == "host_internal.credential_commit":
        _exact(payload, {"old_reference", "principal_ref", "status"})
        _bounded_string(payload["principal_ref"])
        if payload["old_reference"] is not None:
            _bounded_string(payload["old_reference"])
    elif command_id == "host_internal.destructive_prepare":
        _exact(
            payload,
            {
                "digest",
                "generation",
                "nonce",
                "operation_intent",
                "plan_id",
                "status",
                "summary",
            },
        )
        for field in (
            "digest",
            "nonce",
            "operation_intent",
            "plan_id",
            "status",
            "summary",
        ):
            _bounded_string(payload[field], 256)
        _bounded_integer(payload["generation"])
    elif command_id in {
        "host_internal.destructive_cancel",
    }:
        _exact(payload, {"status"})
        _bounded_string(payload["status"], 32)
    elif command_id == "host_internal.destructive_commit":
        _exact(payload, {"cleanup_references", "status"})
        if payload["cleanup_references"] != []:
            _bounded_string_list(payload["cleanup_references"])
        _bounded_string(payload["status"], 32)
    elif command_id == "host_internal.provider_failure_commit":
        _exact(payload, {"status"})
        _bounded_string(payload["status"], 32)
    elif command_id == "host_internal.provider_response_commit":
        _exact(payload, {"retryable", "safe_error_code", "status"})
        if not isinstance(payload["retryable"], bool):
            raise ContractViolation("invalid provider retryability")
        if payload["safe_error_code"] is not None:
            _bounded_string(payload["safe_error_code"], 64)
        _bounded_string(payload["status"], 32)
    else:
        raise ContractViolation("unknown internal command")


def _internal_dispatch(
    native: NativeControlPlane,
    command_id: str,
    payload: dict[str, object],
) -> dict[str, object]:
    try:
        if command_id == "host_internal.cleanup_pending":
            return {"references": native.cleanup_pending(), "status": "ok"}
        if command_id == "host_internal.cleanup_ack":
            native.acknowledge_cleanup(cast(list[str], payload["references"]))
            return {"status": "acknowledged"}
        if command_id == "host_internal.credential_context":
            reference, generation, provider_id = native.credential_context(
                str(payload["principal_ref"])
            )
            return {
                "credential_reference": reference,
                "generation": generation,
                "provider_id": provider_id,
                "status": "ok",
            }
        if command_id == "host_internal.credential_candidate_create":
            return {
                "credential_reference": native.create_credential_candidate(),
                "status": "prepared",
            }
        if command_id == "host_internal.credential_prepare":
            native.prepare_credential_reference(str(payload["credential_reference"]))
            return {"status": "prepared"}
        if command_id == "host_internal.credential_commit":
            commit = native.commit_prepared_credential(
                purpose=str(payload["purpose"]),
                credential_reference=str(payload["credential_reference"]),
                principal_ref=(
                    None if payload["principal_ref"] is None else str(payload["principal_ref"])
                ),
                expected_generation=(
                    None
                    if payload["expected_generation"] is None
                    else cast(int, payload["expected_generation"])
                ),
                provider_id=str(payload["provider_id"]),
            )
            return {
                "old_reference": commit.old_reference,
                "principal_ref": commit.principal_ref,
                "status": "committed",
            }
        if command_id == "host_internal.destructive_prepare":
            plan = native.prepare_destructive(
                operation_intent=str(payload["operation_intent"]),
                opaque_selection_handle=str(payload["opaque_selection_handle"]),
            )
            return {"status": "prepared", **plan.host_projection()}
        if command_id == "host_internal.destructive_cancel":
            native.cancel_destructive(str(payload["plan_id"]))
            return {"status": "cancelled"}
        if command_id == "host_internal.destructive_commit":
            cleanup_references = native.commit_destructive(
                plan_id=str(payload["plan_id"]),
                digest=str(payload["digest"]),
                generation=cast(int, payload["generation"]),
                nonce=str(payload["nonce"]),
                user_presence_token=str(payload["user_presence_token"]),
            )
            return {
                "cleanup_references": list(cleanup_references),
                "status": "committed",
            }
        if command_id == "host_internal.provider_response_commit":
            safe_error_code, retryable = native.commit_provider_response(
                principal_ref=str(payload["principal_ref"]),
                expected_generation=cast(int, payload["expected_generation"]),
                provider_id=str(payload["provider_id"]),
                http_status=cast(int, payload["http_status"]),
                body_base64=str(payload["body_base64"]),
            )
            return {
                "retryable": retryable,
                "safe_error_code": safe_error_code,
                "status": "committed" if safe_error_code is None else "rejected",
            }
        if command_id == "host_internal.provider_failure_commit":
            native.commit_provider_failure(
                principal_ref=str(payload["principal_ref"]),
                expected_generation=cast(int, payload["expected_generation"]),
                provider_id=str(payload["provider_id"]),
                safe_error_code=str(payload["safe_error_code"]),
            )
            return {"status": "committed"}
    except (OSError, OverflowError, ValueError) as error:
        raise ContractViolation("internal operation rejected") from error
    raise ContractViolation("unknown internal command")


def serve(
    input_stream: BinaryIO,
    output_stream: BinaryIO,
    secret: bytes,
    native: NativeControlPlane | None = None,
) -> None:
    session = SidecarSession(secret=secret, contract=RendererContract(), native=native)
    while True:
        try:
            envelope = read_frame(input_stream)
        except EOFError:
            return
        response = session.dispatch(envelope)
        write_frame(output_stream, response)


def main() -> int:
    try:
        secret = read_session_secret()
        arguments = sys.argv[1:]
        if len(arguments) != 2 or arguments[0] != "--data-root":
            raise ContractViolation("native data root argument is unavailable")
        data_root = Path(arguments[1])
        native = NativeControlPlane(data_root)
        serve(sys.stdin.buffer, sys.stdout.buffer, secret, native)
    except (ContractViolation, EOFError, OSError, ValueError):
        return 64
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
