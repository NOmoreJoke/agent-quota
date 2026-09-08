from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent_quota.filesystem import atomic_write_private, open_directory_nofollow, read_regular_at


def test_directory_open_requires_absolute_private_mode(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        open_directory_nofollow(Path("relative"))
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    directory.chmod(0o755)
    with pytest.raises(ValueError):
        open_directory_nofollow(directory, require_mode=0o700)


def test_directory_open_rejects_symlink_component(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir(mode=0o700)
    link = tmp_path / "linked"
    link.symlink_to(actual, target_is_directory=True)
    with pytest.raises(OSError):
        open_directory_nofollow(link)


def test_regular_read_rejects_hardlink(tmp_path: Path) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    original = root / "value"
    original.write_text("private")
    os.link(original, root / "duplicate")
    descriptor = open_directory_nofollow(root)
    try:
        with pytest.raises(ValueError):
            read_regular_at(descriptor, "value")
    finally:
        os.close(descriptor)


def test_private_io_enforces_explicit_bounds(tmp_path: Path) -> None:
    root = (tmp_path / "private").absolute()
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    path = root / "value"
    atomic_write_private(path, b"1234", max_bytes=4)
    descriptor = open_directory_nofollow(root)
    try:
        with pytest.raises(ValueError, match="read bound"):
            read_regular_at(descriptor, "value", max_bytes=True)
        with pytest.raises(ValueError, match="exceeds read bound"):
            read_regular_at(descriptor, "value", max_bytes=3)
    finally:
        os.close(descriptor)
    with pytest.raises(ValueError, match="private write"):
        atomic_write_private(path, b"1234", max_bytes=3)
    assert path.read_bytes() == b"1234"


def test_regular_read_rejects_fifo_without_waiting_for_writer(tmp_path: Path) -> None:
    import subprocess
    import sys

    fifo = tmp_path / "pipe"
    os.mkfifo(fifo, 0o600)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os, sys; from agent_quota.filesystem import read_regular_at; "
            "fd = os.open(sys.argv[1], os.O_RDONLY); "
            "read_regular_at(fd, 'pipe')",
            str(tmp_path),
        ],
        capture_output=True,
        timeout=3,
    )
    assert result.returncode == 1
    assert b"private file identity mismatch" in result.stderr
