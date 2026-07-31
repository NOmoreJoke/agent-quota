from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from conftest import FakeClock

from agent_quota.errors import FenceConflict, LeaseConflict
from agent_quota.model import AccountScope, CapabilityKind
from agent_quota.storage import Store


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_database_permissions_and_wal(tmp_path: Path, clock: FakeClock) -> None:
    store = Store(tmp_path / "private" / "state.sqlite", clock)
    try:
        assert mode(store.path.parent) == 0o700
        assert mode(store.path) == 0o600
        assert store.connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        store.connection.execute("CREATE TABLE permission_probe(value INTEGER)")
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{store.path}{suffix}")
            if sidecar.exists():
                assert mode(sidecar) == 0o600
    finally:
        store.close()


def test_active_lease_rejects_competitor(store: Store) -> None:
    store.acquire_lease("writer", "owner-a", 100)
    with pytest.raises(LeaseConflict):
        store.acquire_lease("writer", "owner-b", 100)


def test_expired_lease_increments_fence(store: Store, clock: FakeClock) -> None:
    first = store.acquire_lease("writer", "owner-a", 100)
    clock.mono += 101
    second = store.acquire_lease("writer", "owner-b", 100)
    assert second.fence == first.fence + 1
    with pytest.raises(FenceConflict):
        store.assert_fence(first)


def test_boot_change_forces_takeover(store: Store, clock: FakeClock) -> None:
    first = store.acquire_lease("writer", "owner-a", 100)
    clock.boot_id = "boot-b"
    second = store.acquire_lease("writer", "owner-b", 100)
    assert second.fence == first.fence + 1


def test_lease_overflow_rejected(store: Store, clock: FakeClock) -> None:
    clock.mono = 2**63 - 5
    with pytest.raises(OverflowError):
        store.acquire_lease("writer", "owner", 10)


def test_database_path_rejects_symlink(tmp_path: Path, clock: FakeClock) -> None:
    target = tmp_path / "target"
    target.write_bytes(b"")
    link = tmp_path / "state.sqlite"
    os.symlink(target, link)
    with pytest.raises(ValueError):
        Store(link, clock)


def test_scope_components_are_composite_not_global(store: Store) -> None:
    first = AccountScope("provider-a", "shared-subject", "shared-capability")
    second = AccountScope("provider-b", "shared-subject", "shared-capability")
    for scope in (first, second):
        store.seed_scope(
            scope,
            provider=scope.principal_id,
            principal_label=scope.principal_id,
            subject_label=scope.subject_id,
            kind=CapabilityKind.WINDOW,
            unit="requests",
        )
    assert store.authorize(first)
    assert store.authorize(second)
