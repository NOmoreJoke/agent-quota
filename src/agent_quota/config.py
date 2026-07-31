"""Crash-recoverable TOML config journal coordinated by a fenced writer."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import secrets
import stat
import tomllib
from pathlib import Path
from typing import Any

from agent_quota.filesystem import open_directory_nofollow, read_regular_at, same_identity
from agent_quota.storage import Lease, Store


def canonical_config(config: dict[str, Any]) -> bytes:
    allowed = {"theme", "timezone", "reduce_motion", "offline_mode"}
    if set(config) != allowed:
        raise ValueError("config field closure mismatch")
    if config["theme"] not in {"light", "dark", "system"}:
        raise ValueError("invalid theme")
    if (
        not isinstance(config["timezone"], str)
        or not config["timezone"]
        or len(config["timezone"].encode()) > 64
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in config["timezone"])
    ):
        raise ValueError("invalid timezone")
    if not isinstance(config["reduce_motion"], bool) or not isinstance(
        config["offline_mode"], bool
    ):
        raise ValueError("invalid config boolean")
    lines = [
        f"theme = {json.dumps(config['theme'], ensure_ascii=False)}",
        f"timezone = {json.dumps(config['timezone'], ensure_ascii=False)}",
        f"reduce_motion = {str(config['reduce_motion']).lower()}",
        f"offline_mode = {str(config['offline_mode']).lower()}",
    ]
    return ("\n".join(lines) + "\n").encode()


def config_digest(raw: bytes) -> str:
    return hashlib.sha256(b"agent-quota:config:v1\0" + raw).hexdigest()


def apply_config(
    store: Store,
    path: Path,
    config: dict[str, Any],
    lease: Lease,
    *,
    journal_id: str,
    fail_after: str | None = None,
) -> str:
    store.assert_fence(lease)
    if (
        not path.is_absolute()
        or path.parent.absolute() != store.path.parent.absolute()
        or path.name in {"", ".", ".."}
        or "/" in path.name
    ):
        raise ValueError("config path must be inside the private data root")
    raw = canonical_config(config)
    root = open_directory_nofollow(
        path.parent,
        require_owner=True,
        require_mode=0o700,
    )
    try:
        try:
            old_raw, old_identity = read_regular_at(root, path.name)
            if stat.S_IMODE(old_identity.st_mode) != 0o600:
                raise ValueError("config file mode mismatch")
        except FileNotFoundError:
            old_raw, old_identity = b"", None
        old_digest = config_digest(old_raw)
        new_digest = config_digest(raw)
        with store.transaction() as connection:
            store.assert_fence(lease, connection)
            connection.execute(
                "INSERT INTO config_journal VALUES(?,?,?,?,?)",
                (journal_id, old_digest, new_digest, "planned", lease.fence),
            )
        if fail_after == "planned":
            raise RuntimeError("injected crash after planned")
        temporary_name = f".config-{secrets.token_hex(16)}"
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=root,
        )
        try:
            os.fchmod(descriptor, 0o600)
            offset = 0
            while offset < len(raw):
                written = os.write(descriptor, raw[offset:])
                if written <= 0:
                    raise OSError("config write made no progress")
                offset += written
            os.fsync(descriptor)
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or metadata.st_nlink != 1
            ):
                raise ValueError("config temporary file identity mismatch")
        finally:
            os.close(descriptor)
        try:
            if old_identity is None:
                try:
                    os.stat(path.name, dir_fd=root, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise ValueError("config target appeared during apply")
            else:
                current = os.stat(path.name, dir_fd=root, follow_symlinks=False)
                if not same_identity(old_identity, current):
                    raise ValueError("config target changed during apply")
            os.rename(
                temporary_name,
                path.name,
                src_dir_fd=root,
                dst_dir_fd=root,
            )
            os.fsync(root)
        except BaseException:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary_name, dir_fd=root)
            raise
        if fail_after == "renamed":
            raise RuntimeError("injected crash after config rename")
        with store.transaction() as connection:
            store.assert_fence(lease, connection)
            connection.execute(
                "UPDATE config_journal SET state='file_committed' WHERE journal_id=?",
                (journal_id,),
            )
        if fail_after == "file_committed":
            raise RuntimeError("injected crash after file commit")
        with store.transaction() as connection:
            store.assert_fence(lease, connection)
            connection.execute(
                "UPDATE config_journal SET state='done' WHERE journal_id=?",
                (journal_id,),
            )
        return new_digest
    finally:
        os.close(root)


def recover_config(store: Store, path: Path) -> int:
    if path.parent.absolute() != store.path.parent.absolute():
        raise ValueError("config path must be inside the private data root")
    rows = store.connection.execute(
        "SELECT * FROM config_journal WHERE state!='done' ORDER BY journal_id"
    ).fetchall()
    recovered = 0
    for row in rows:
        try:
            live_raw = _read_config_bytes(path)
        except FileNotFoundError:
            live_raw = b""
        live = config_digest(live_raw)
        if row["state"] == "file_committed" and live == row["new_digest"]:
            store.connection.execute(
                "UPDATE config_journal SET state='done' WHERE journal_id=?",
                (row["journal_id"],),
            )
            recovered += 1
        elif row["state"] == "planned":
            if live == row["old_digest"]:
                store.connection.execute(
                    "DELETE FROM config_journal WHERE journal_id=?",
                    (row["journal_id"],),
                )
                recovered += 1
            elif live == row["new_digest"]:
                store.connection.execute(
                    "UPDATE config_journal SET state='done' WHERE journal_id=?",
                    (row["journal_id"],),
                )
                recovered += 1
            else:
                raise RuntimeError("config journal requires operator recovery")
        else:
            raise RuntimeError("config journal requires operator recovery")
    return recovered


def read_config(path: Path) -> dict[str, Any]:
    return tomllib.loads(_read_config_bytes(path).decode("utf-8"))


def _read_config_bytes(path: Path) -> bytes:
    root = open_directory_nofollow(
        path.parent,
        require_owner=True,
        require_mode=0o700,
    )
    try:
        raw, metadata = read_regular_at(root, path.name)
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise ValueError("config file mode mismatch")
        return raw
    finally:
        os.close(root)
