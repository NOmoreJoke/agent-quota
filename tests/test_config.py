from __future__ import annotations

import pytest

from agent_quota.config import apply_config, read_config, recover_config
from agent_quota.storage import Store

CONFIG = {
    "theme": "light",
    "timezone": "Asia/Shanghai",
    "reduce_motion": False,
    "offline_mode": False,
}


def test_config_apply_and_read(store: Store) -> None:
    lease = store.acquire_lease("config", "owner", 1_000_000)
    path = store.path.parent / "config.toml"
    digest = apply_config(store, path, CONFIG, lease, journal_id="j1")
    assert len(digest) == 64
    assert read_config(path) == CONFIG
    assert path.stat().st_mode & 0o777 == 0o600
    state = store.connection.execute(
        "SELECT state FROM config_journal WHERE journal_id='j1'"
    ).fetchone()[0]
    assert state == "done"


def test_planned_crash_rolls_back_journal(store: Store) -> None:
    lease = store.acquire_lease("config", "owner", 1_000_000)
    path = store.path.parent / "config.toml"
    with pytest.raises(RuntimeError):
        apply_config(store, path, CONFIG, lease, journal_id="j1", fail_after="planned")
    assert recover_config(store, path) == 1
    assert store.connection.execute("SELECT COUNT(*) FROM config_journal").fetchone()[0] == 0


def test_file_commit_crash_rolls_forward(store: Store) -> None:
    lease = store.acquire_lease("config", "owner", 1_000_000)
    path = store.path.parent / "config.toml"
    with pytest.raises(RuntimeError):
        apply_config(
            store,
            path,
            CONFIG,
            lease,
            journal_id="j1",
            fail_after="file_committed",
        )
    assert recover_config(store, path) == 1
    assert read_config(path) == CONFIG


def test_rename_crash_rolls_forward_planned_journal(store: Store) -> None:
    lease = store.acquire_lease("config", "owner", 1_000_000)
    path = store.path.parent / "config.toml"
    with pytest.raises(RuntimeError):
        apply_config(store, path, CONFIG, lease, journal_id="j1", fail_after="renamed")
    assert recover_config(store, path) == 1
    assert read_config(path) == CONFIG


def test_config_replaces_same_private_file(store: Store) -> None:
    path = store.path.parent / "config.toml"
    first = store.acquire_lease("config", "owner-a", 1_000_000)
    apply_config(store, path, CONFIG, first, journal_id="j1")
    store.release_lease(first)
    second = store.acquire_lease("config", "owner-b", 1_000_000)
    changed = {**CONFIG, "theme": "dark"}
    apply_config(store, path, changed, second, journal_id="j2")
    assert read_config(path) == changed


def test_config_rejects_non_private_existing_mode(store: Store) -> None:
    lease = store.acquire_lease("config", "owner", 1_000_000)
    path = store.path.parent / "config.toml"
    path.write_text("theme = 'light'\n")
    path.chmod(0o644)
    with pytest.raises(ValueError):
        apply_config(store, path, CONFIG, lease, journal_id="bad-mode")


@pytest.mark.parametrize(
    "config",
    [
        {**CONFIG, "unknown": True},
        {**CONFIG, "theme": "blue"},
        {**CONFIG, "reduce_motion": "false"},
        {**CONFIG, "timezone": "x" * 65},
        {**CONFIG, "timezone": 'UTC"\nsecret = "injected'},
    ],
)
def test_invalid_config_rejected_before_write(
    store: Store,
    config: dict[str, object],
) -> None:
    lease = store.acquire_lease("config", "owner", 1_000_000)
    path = store.path.parent / "config.toml"
    with pytest.raises(ValueError):
        apply_config(store, path, config, lease, journal_id="bad")
    assert not path.exists()


def test_config_target_symlink_is_rejected(store: Store) -> None:
    lease = store.acquire_lease("config", "owner", 1_000_000)
    target = store.path.parent / "target.toml"
    target.write_text("theme = 'dark'\n")
    path = store.path.parent / "config.toml"
    path.symlink_to(target)
    with pytest.raises(OSError):
        apply_config(store, path, CONFIG, lease, journal_id="symlink")


def test_config_rejects_outside_root_and_insecure_read(store: Store) -> None:
    lease = store.acquire_lease("config", "owner", 1_000_000)
    outside = store.path.parent.parent / "outside.toml"
    with pytest.raises(ValueError):
        apply_config(store, outside, CONFIG, lease, journal_id="outside")
    path = store.path.parent / "config.toml"
    path.write_text("theme = 'light'\n")
    path.chmod(0o644)
    with pytest.raises(ValueError):
        read_config(path)
    with pytest.raises(ValueError):
        recover_config(store, outside)
