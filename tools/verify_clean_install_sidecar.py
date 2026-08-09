"""Prove that the packaged sidecar starts with zero saved accounts."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import socket
import stat
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import BinaryIO

MAX_FRAME_BYTES = 1024 * 1024
SESSION_SECRET_BYTES = 32
SESSION_SECRET_FD = 3


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def session_proof(secret: bytes, value: object) -> str:
    return hmac.new(secret, canonical_json(value), hashlib.sha256).hexdigest()


def read_exact(stream: BinaryIO, length: int) -> bytes:
    output = bytearray()
    while len(output) < length:
        chunk = stream.read(length - len(output))
        if not chunk:
            raise ValueError("packaged sidecar response is truncated")
        output.extend(chunk)
    return bytes(output)


def read_frame(stream: BinaryIO) -> dict[str, object]:
    length = struct.unpack(">I", read_exact(stream, 4))[0]
    if not 1 <= length <= MAX_FRAME_BYTES:
        raise ValueError("packaged sidecar response size is invalid")
    value = json.loads(read_exact(stream, length))
    if not isinstance(value, dict):
        raise ValueError("packaged sidecar response shape is invalid")
    return value


def write_frame(stream: BinaryIO, value: dict[str, object]) -> None:
    body = canonical_json(value)
    if not 1 <= len(body) <= MAX_FRAME_BYTES:
        raise ValueError("packaged sidecar request size is invalid")
    stream.write(struct.pack(">I", len(body)))
    stream.write(body)
    stream.flush()


def call(
    process: subprocess.Popen[bytes],
    secret: bytes,
    request_id: int,
    command_id: str,
    payload: dict[str, object],
) -> dict[str, object]:
    if process.stdin is None or process.stdout is None:
        raise ValueError("packaged sidecar pipes are unavailable")
    unsigned: dict[str, object] = {
        "command_id": command_id,
        "payload": payload,
        "remaining_budget_ns": 2_000_000_000,
        "request_id": request_id,
    }
    write_frame(process.stdin, {**unsigned, "session_proof": session_proof(secret, unsigned)})
    envelope = read_frame(process.stdout)
    if set(envelope) != {"request_id", "response", "session_proof"}:
        raise ValueError("packaged sidecar response field closure mismatch")
    response = envelope["response"]
    expected = session_proof(secret, {"request_id": request_id, "response": response})
    if (
        envelope["request_id"] != request_id
        or not isinstance(response, dict)
        or not isinstance(envelope["session_proof"], str)
        or not hmac.compare_digest(envelope["session_proof"], expected)
    ):
        raise ValueError("packaged sidecar response proof mismatch")
    return response


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sidecar", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    metadata = args.sidecar.lstat()
    if args.sidecar.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o022:
        raise SystemExit("packaged sidecar path is unsafe")
    sidecar = args.sidecar.resolve(strict=True)

    with tempfile.TemporaryDirectory(prefix="agent-quota-clean-install-") as temporary:
        data_root = Path(temporary).resolve(strict=True) / "data"
        data_root.mkdir(mode=0o700)
        parent_secret, child_secret = socket.socketpair()
        secret = os.urandom(SESSION_SECRET_BYTES)
        child_secret_fd = child_secret.fileno()

        def prepare_secret_fd() -> None:
            if child_secret_fd != SESSION_SECRET_FD:
                os.dup2(child_secret_fd, SESSION_SECRET_FD, inheritable=True)
            else:
                os.set_inheritable(SESSION_SECRET_FD, True)

        process = subprocess.Popen(
            [str(sidecar), "--data-root", str(data_root)],
            env={"AQ_SESSION_SECRET_FD": str(SESSION_SECRET_FD)},
            pass_fds=tuple(sorted({child_secret_fd, SESSION_SECRET_FD})),
            preexec_fn=prepare_secret_fd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        child_secret.close()
        parent_secret.sendall(secret)
        parent_secret.shutdown(socket.SHUT_WR)
        parent_secret.close()
        try:
            bootstrap = call(process, secret, 1, "bootstrap_state", {})
            accounts = call(process, secret, 2, "accounts_read", {"scope_ref": "scope-all"})
            if bootstrap.get("status") != "ok" or accounts != {"accounts": [], "status": "ok"}:
                raise ValueError("packaged sidecar clean-install state is not empty")
        finally:
            if process.stdin is not None:
                process.stdin.close()
            return_code = process.wait(timeout=5)
        if return_code != 0:
            raise ValueError("packaged sidecar clean-install process failed")

        state_file = data_root / "native-accounts-v1.json"
        if state_file.exists():
            document = json.loads(state_file.read_bytes())
            if document.get("accounts") != []:
                raise ValueError("packaged sidecar persisted account details on clean install")
        report = {
            "accounts_count": 0,
            "artifact_class": "local unsigned development package",
            "sidecar_sha256": sha256(sidecar),
            "state_file_present": state_file.exists(),
            "status": "pass",
        }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
