from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from agent_quota.exporting import FORBIDDEN_EXPORT_KEYS, redacted_document, write_redacted_export
from agent_quota.purge import commit_purge, plan_purge
from agent_quota.storage import Store


def test_redacted_export_has_closed_safe_keys(store: Store, tmp_path: Path) -> None:
    document = redacted_document(store)
    serialized = json.dumps(document).casefold()
    assert not any(f'"{key}"' in serialized for key in FORBIDDEN_EXPORT_KEYS)
    destination = tmp_path / "export" / "redacted.json"
    write_redacted_export(store, destination)
    assert destination.stat().st_mode & 0o777 == 0o600
    assert json.loads(destination.read_text()) == document
    with pytest.raises(FileExistsError):
        write_redacted_export(store, destination)


def test_export_rejects_symlink_parent(store: Store, tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    link = tmp_path / "linked"
    os.symlink(actual, link)
    with pytest.raises(ValueError):
        write_redacted_export(store, link / "export.json")


def test_purge_projection_omits_paths(tmp_path: Path) -> None:
    root = tmp_path / "application" / "data"
    root.mkdir(parents=True)
    root.chmod(0o700)
    (root / "state.sqlite").write_bytes(b"db")
    (root / "config.toml").write_text("theme='light'\n")
    projection = plan_purge(root, 1).renderer_projection()
    assert "path" not in json.dumps(projection).casefold()
    assert projection["status"] == "confirmation-required"


def test_purge_rejects_drift_and_unknown(tmp_path: Path) -> None:
    root = tmp_path / "application" / "data"
    root.mkdir(parents=True)
    root.chmod(0o700)
    (root / "state.sqlite").write_bytes(b"db")
    plan = plan_purge(root, 1)
    (root / "unexpected.txt").write_text("x")
    with pytest.raises(ValueError):
        commit_purge(
            root,
            plan,
            expected_digest=plan.digest,
            expected_generation=plan.generation,
        )
    updated = plan_purge(root, 1)
    with pytest.raises(ValueError):
        commit_purge(
            root,
            updated,
            expected_digest="0" * 64,
            expected_generation=updated.generation,
        )
    with pytest.raises(ValueError):
        commit_purge(
            root,
            updated,
            expected_digest=updated.digest,
            expected_generation=updated.generation,
        )


@pytest.mark.parametrize("root", [Path("/"), Path.home()])
def test_purge_rejects_broad_roots(root: Path) -> None:
    with pytest.raises(ValueError):
        plan_purge(root, 1)


def test_purge_commits_known_empty_cache(tmp_path: Path) -> None:
    root = tmp_path / "application" / "data"
    root.mkdir(parents=True)
    root.chmod(0o700)
    (root / "state.sqlite").write_bytes(b"db")
    (root / "config.toml").write_text("theme='light'\n")
    (root / "cache").mkdir()
    plan = plan_purge(root, 2)
    commit_purge(
        root,
        plan,
        expected_digest=plan.digest,
        expected_generation=2,
    )
    assert list(root.iterdir()) == []


def test_purge_rejects_symlink_and_hardlink(tmp_path: Path) -> None:
    root = tmp_path / "application" / "data"
    root.mkdir(parents=True)
    root.chmod(0o700)
    external = tmp_path / "external"
    external.write_text("keep")
    os.symlink(external, root / "state.sqlite")
    plan = plan_purge(root, 1)
    assert any(entry.kind == "unknown" for entry in plan.entries)
    with pytest.raises(ValueError):
        commit_purge(
            root,
            plan,
            expected_digest=plan.digest,
            expected_generation=1,
        )
    (root / "state.sqlite").unlink()
    local = root / "state.sqlite"
    local.write_text("db")
    os.link(local, tmp_path / "hardlink")
    hardlink_plan = plan_purge(root, 2)
    with pytest.raises(ValueError):
        commit_purge(
            root,
            hardlink_plan,
            expected_digest=hardlink_plan.digest,
            expected_generation=2,
        )
    assert external.read_text() == "keep"


def test_purge_rejects_nonempty_cache(tmp_path: Path) -> None:
    root = tmp_path / "application" / "data"
    root.mkdir(parents=True)
    root.chmod(0o700)
    cache = root / "cache"
    cache.mkdir()
    (cache / "entry").write_text("keep")
    plan = plan_purge(root, 1)
    with pytest.raises(ValueError):
        commit_purge(
            root,
            plan,
            expected_digest=plan.digest,
            expected_generation=plan.generation,
        )
