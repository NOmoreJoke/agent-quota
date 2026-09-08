from __future__ import annotations

import errno
import os
import runpy
from pathlib import Path

import pytest

module = runpy.run_path(Path(__file__).parents[1] / "tools" / "publish_artifact_directory.py")
publish = module["publish"]
rename_noreplace = module["_rename_noreplace"]
PublicationOutcomeUnknown = module["PublicationOutcomeUnknown"]


def test_native_rename_never_replaces_existing_target(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    parent = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    rename_noreplace(parent, source.name, target.name)
    assert target.is_dir()

    replacement = tmp_path / "replacement"
    replacement.mkdir()
    with pytest.raises(FileExistsError):
        rename_noreplace(parent, replacement.name, target.name)
    os.close(parent)
    assert replacement.is_dir()


def test_publish_uses_staged_no_replace_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage = tmp_path / ".release.stage"
    target = tmp_path / "release-deadbeef"
    stage.mkdir(mode=0o700)
    (stage / "evidence.txt").write_text("verified")

    def rename(parent: int, source: str, destination: str) -> None:
        os.rename(source, destination, src_dir_fd=parent, dst_dir_fd=parent)

    monkeypatch.setitem(publish.__globals__, "_rename_noreplace", rename)
    publish(stage, target)

    assert not stage.exists()
    assert (target / "evidence.txt").read_text() == "verified"


def test_publish_preserves_existing_release_and_rejects_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage = tmp_path / ".release.stage"
    target = tmp_path / "release-deadbeef"
    stage.mkdir(mode=0o700)
    target.mkdir()
    (target / "evidence.txt").write_text("prior")
    with pytest.raises(FileExistsError):
        publish(stage, target)
    assert (target / "evidence.txt").read_text() == "prior"

    (target / "evidence.txt").unlink()
    target.rmdir()
    (stage / "escape").symlink_to(tmp_path / "outside")
    monkeypatch.setitem(
        publish.__globals__,
        "_rename_noreplace",
        lambda *_args: (_ for _ in ()).throw(OSError(errno.EEXIST, "race")),
    )
    with pytest.raises(ValueError, match="symlink"):
        publish(stage, target)


def test_post_rename_fsync_failure_is_explicitly_ambiguous(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage = tmp_path / ".release.stage"
    target = tmp_path / "release-deadbeef"
    stage.mkdir(mode=0o700)
    (stage / "evidence.txt").write_text("verified")
    monkeypatch.setitem(
        publish.__globals__,
        "_fsync_parent",
        lambda *_args: (_ for _ in ()).throw(OSError(errno.EIO, "fsync failed")),
    )

    with pytest.raises(PublicationOutcomeUnknown, match="publication_outcome_unknown"):
        publish(stage, target)
    assert target.is_dir()
    assert not stage.exists()


def test_publish_rejects_symlink_parent(tmp_path: Path) -> None:
    real_parent = tmp_path / "real-artifacts"
    real_parent.mkdir()
    linked_parent = tmp_path / "artifacts"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    stage = linked_parent / ".release.stage"
    target = linked_parent / "release-deadbeef"
    stage.mkdir(mode=0o700)

    with pytest.raises(OSError):
        publish(stage, target)
    assert not target.exists()


def test_parent_swap_after_rename_reports_unknown_without_redirecting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publication_parent = tmp_path / "artifacts"
    publication_parent.mkdir()
    stage = publication_parent / ".release.stage"
    target = publication_parent / "release-deadbeef"
    stage.mkdir(mode=0o700)
    replacement_parent = tmp_path / "replacement"
    replacement_parent.mkdir()
    original_rename = rename_noreplace

    def rename_then_swap(parent: int, source: str, destination: str) -> None:
        original_rename(parent, source, destination)
        publication_parent.rename(tmp_path / "detached-artifacts")
        replacement_parent.rename(publication_parent)

    monkeypatch.setitem(publish.__globals__, "_rename_noreplace", rename_then_swap)
    with pytest.raises(PublicationOutcomeUnknown, match="publication_outcome_unknown"):
        publish(stage, target)
    assert not target.exists()
    assert (tmp_path / "detached-artifacts/release-deadbeef").is_dir()
