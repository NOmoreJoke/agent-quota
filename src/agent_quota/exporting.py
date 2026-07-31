"""Redacted exports that never include adapter payloads or credentials."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

from agent_quota.model import AccountScope
from agent_quota.storage import Store

FORBIDDEN_EXPORT_KEYS = frozenset(
    {
        "credential",
        "credential_ref",
        "secret",
        "token",
        "api_key",
        "header",
        "raw_response",
        "identity_evidence",
        "request_digest",
    }
)


def redacted_document(store: Store) -> dict[str, Any]:
    accounts = store.list_accounts()
    projections = []
    for row in accounts:
        scope = AccountScope(
            str(row["principal_id"]),
            str(row["subject_id"]),
            str(row["capability_id"]),
        )
        snapshot = store.latest_snapshot(scope)
        if snapshot is not None:
            projections.append(snapshot.renderer_projection())
    document: dict[str, Any] = {
        "schema": "agent-quota-redacted-export-v1",
        "accounts": accounts,
        "projections": projections,
        "diagnostic_counts": store.diagnostic_counts(),
    }
    _assert_redacted(document)
    return document


def write_redacted_export(store: Store, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    metadata = os.lstat(destination.parent)
    if not stat.S_ISDIR(metadata.st_mode) or destination.parent.is_symlink():
        raise ValueError("export parent must be a non-symlink directory")
    data = json.dumps(redacted_document(store), ensure_ascii=False, sort_keys=True, indent=2)
    descriptor = os.open(
        destination,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        raw = (data + "\n").encode()
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                raise OSError("export write made no progress")
            offset += written
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    parent = os.open(
        destination.parent,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        os.fsync(parent)
    finally:
        os.close(parent)


def _assert_redacted(value: object) -> None:
    if isinstance(value, dict):
        if FORBIDDEN_EXPORT_KEYS.intersection(key.casefold() for key in value):
            raise ValueError("export contains a forbidden key")
        for item in value.values():
            _assert_redacted(item)
    elif isinstance(value, list):
        for item in value:
            _assert_redacted(item)
