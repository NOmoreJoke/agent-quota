"""Preview or explicitly migrate legacy keychain names, never credential values.

Run with uv. --apply requires Agent Quota to be closed and allows macOS to ask
the user for permission to edit ACL descriptions. This does not grant access to
new applications and does not perform a Provider request.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import pwd
import stat
import subprocess
from pathlib import Path

from agent_quota.filesystem import open_directory_nofollow, read_regular_at
from agent_quota.native_control import MAX_STATE_BYTES, NativeControlPlane


def load_accounts(root: Path) -> tuple[list[dict[str, object]], str]:
    directory = open_directory_nofollow(root, require_owner=True, require_mode=0o700)
    try:
        payload, metadata = read_regular_at(
            directory, "native-accounts-v1.json", max_bytes=MAX_STATE_BYTES
        )
    finally:
        os.close(directory)
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise ValueError("Account state must be private (0600)")
    document = json.loads(payload)
    NativeControlPlane._validate_state(document)
    return document["accounts"], hashlib.sha256(payload).hexdigest()


def acquire_lease(root: Path) -> int:
    directory = open_directory_nofollow(root.parent, require_owner=True)
    try:
        descriptor = os.open(
            ".agent-quota-host-instance.lock",
            os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
    finally:
        os.close(directory)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
        ):
            raise ValueError("Unsafe application instance lock")
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True, help="Verified new Agent Quota.app")
    parser.add_argument(
        "--apply", action="store_true", help="Allow macOS name-change authorization"
    )
    args = parser.parse_args()
    root = (
        Path(pwd.getpwuid(os.geteuid()).pw_dir)
        / "Library/Application Support/com.agentquota.desktop"
    )
    app = args.app.absolute()
    if app.is_symlink() or app.resolve(strict=True) != app:
        raise ValueError("App path must not contain symlinks")
    helper = (
        app
        / "Contents/Resources/native-helper/AgentQuotaNative.app/Contents/MacOS/AgentQuotaNative"
    )
    subprocess.run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)], check=True)
    if not helper.is_file() or helper.is_symlink():
        raise ValueError("Native helper is missing or unsafe")
    lease = acquire_lease(root) if args.apply else None
    try:
        accounts, initial_hash = load_accounts(root)
        failed = False
        for account in accounts:
            reference = str(account["credential_reference"])
            provider = str(account["provider_id"])
            row = {"provider": provider, "credential_id": reference.removeprefix("credential-")[:8]}
            if args.apply:
                if load_accounts(root)[1] != initial_hash:
                    raise ValueError("Account state changed; stop migration")
                request = {
                    "action": "keychain-rename",
                    "opaqueReference": reference,
                    "provider": provider,
                }
                response = subprocess.run(
                    [str(helper)],
                    input=json.dumps(request) + "\n",
                    text=True,
                    capture_output=True,
                    check=True,
                    timeout=180,
                    env={},
                )
                if len(response.stdout.encode()) > 4096:
                    raise ValueError("Unexpected helper response size")
                result = json.loads(response.stdout)
                row["status"] = result.get("status", "error")
                # Stop after rejection/error instead of presenting another authorization dialog.
                failed = row["status"] not in {"renamed", "unchanged"}
            else:
                row["status"] = "preview"
            print(json.dumps(row, ensure_ascii=False), flush=True)
            if failed:
                break
        if load_accounts(root)[1] != initial_hash:
            raise ValueError("Account state changed during migration")
        return int(failed)
    finally:
        if lease is not None:
            os.close(lease)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BlockingIOError:
        raise SystemExit("Quit Agent Quota before applying credential-name migration") from None
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit(f"Credential-name migration stopped: {type(error).__name__}") from None
