"""Anonymous-pipe sidecar entrypoint with closed, bounded framing."""

from __future__ import annotations

import hmac
import json
import os
import struct
import sys
from dataclasses import dataclass
from hashlib import sha256
from typing import BinaryIO, Final

from agent_quota.dto import RendererContract
from agent_quota.errors import ContractViolation

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
    return json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()


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

        self.contract.validate_command_request(command_id, payload)
        self.last_request_id = request_id
        response = _safe_dispatch(command_id, payload)
        self.contract.validate_command_response(command_id, response)
        return {
            "request_id": request_id,
            "response": response,
            "session_proof": session_proof(
                self.secret,
                {"request_id": request_id, "response": response},
            ),
        }


def _safe_dispatch(command_id: str, payload: dict[str, object]) -> dict[str, object]:
    if command_id == "bootstrap_state":
        return {
            "application_state": {"launch_state": "ready", "offline": False},
            "status": "ok",
        }
    if command_id == "accounts_read":
        return {"accounts": [], "status": "ok"}
    if command_id == "quota_overview":
        return {
            "projection": {
                "capability_rows": [],
                "freshness": "stale",
                "scope_ref": payload["scope_ref"],
            },
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


def serve(
    input_stream: BinaryIO,
    output_stream: BinaryIO,
    secret: bytes,
) -> None:
    session = SidecarSession(secret=secret, contract=RendererContract())
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
        serve(sys.stdin.buffer, sys.stdout.buffer, secret)
    except (ContractViolation, EOFError, OSError):
        return 64
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
