from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).parents[1] / "tools" / "audit_package_size.py"


def run_audit(root: Path, limit: str = "1") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), "--root", str(root), "--max-mib", limit],
        text=True,
        capture_output=True,
        check=False,
    )


def test_package_audit_pass_and_exceed(tmp_path: Path) -> None:
    (tmp_path / "file").write_bytes(b"x" * 1024)
    assert run_audit(tmp_path).returncode == 0
    assert run_audit(tmp_path, "0.0001").returncode == 1


def test_package_audit_forbidden_relative_path(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    assert run_audit(tmp_path).returncode == 1


def test_package_audit_rejects_internal_and_root_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "file").write_text("x")
    (tmp_path / "link").symlink_to(target, target_is_directory=True)
    assert run_audit(tmp_path).returncode == 1
    assert run_audit(tmp_path / "link").returncode == 1


def test_package_audit_missing_root(tmp_path: Path) -> None:
    assert run_audit(tmp_path / "missing").returncode == 1


@pytest.mark.parametrize("limit", ["nan", "inf", "-1", "0"])
def test_package_audit_invalid_limits(tmp_path: Path, limit: str) -> None:
    assert run_audit(tmp_path, limit).returncode == 1


def test_package_audit_rejects_fifo(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "fifo")
    assert run_audit(tmp_path).returncode == 1
