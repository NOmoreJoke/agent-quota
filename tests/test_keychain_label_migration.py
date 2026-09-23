from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

from agent_quota.native_control import NativeControlPlane

SPEC = importlib.util.spec_from_file_location(
    "migrate_keychain_labels", Path(__file__).parents[1] / "tools/migrate_keychain_labels.py"
)
assert SPEC is not None and SPEC.loader is not None
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


def test_name_migration_reads_only_existing_account_metadata(tmp_path: Path) -> None:
    root = tmp_path / "private"
    control = NativeControlPlane(root)
    reference = "credential-12345678-0000-4000-8000-000000000001"
    control.commit_credential(
        purpose="create-credential-reference",
        credential_reference=reference,
        principal_ref=None,
        expected_generation=None,
    )
    before = control.path.read_bytes()
    accounts, digest = migration.load_accounts(root)
    assert accounts[0]["credential_reference"] == reference
    assert accounts[0]["provider_id"] == "deepseek"
    assert len(digest) == 64
    assert control.path.read_bytes() == before
    control.path.chmod(0o644)
    with pytest.raises(ValueError):
        migration.load_accounts(root)


def test_migration_cannot_run_while_host_holds_same_lease(tmp_path: Path) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    first = migration.acquire_lease(root)
    try:
        with pytest.raises(BlockingIOError):
            migration.acquire_lease(root)
    finally:
        os.close(first)
    next_lease = migration.acquire_lease(root)
    os.close(next_lease)


def test_migration_refuses_a_symlink_instance_lock(tmp_path: Path) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    target = tmp_path / "other"
    target.write_text("do not change")
    (tmp_path / ".agent-quota-host-instance.lock").symlink_to(target)
    with pytest.raises(OSError):
        migration.acquire_lease(root)
    assert target.read_text() == "do not change"
