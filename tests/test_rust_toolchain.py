from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import verify_tool_path


def executable(path: Path, mode: int = 0o755) -> Path:
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(mode)
    return path


def test_owned_nonwritable_tool_is_accepted(tmp_path: Path) -> None:
    tool = executable(tmp_path / "rustc")
    canonical, identity = verify_tool_path.inspect_trusted_executable(tool)
    assert canonical == tool
    assert identity.uid == os.geteuid()
    assert identity.mode == 0o755


def test_group_writable_tool_is_rejected(tmp_path: Path) -> None:
    tool = executable(tmp_path / "rustc", 0o775)
    with pytest.raises(verify_tool_path.UnsafeToolPath):
        verify_tool_path.inspect_trusted_executable(tool)


def test_group_writable_parent_is_rejected(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o775)
    shared.chmod(0o775)
    tool = executable(shared / "rustc")
    with pytest.raises(verify_tool_path.UnsafeToolPath):
        verify_tool_path.inspect_trusted_executable(tool)


def test_foreign_owner_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tool = executable(tmp_path / "rustc")
    foreign_euid = os.geteuid() + 1
    monkeypatch.setattr(verify_tool_path.os, "geteuid", lambda: foreign_euid)
    with pytest.raises(verify_tool_path.UnsafeToolPath):
        verify_tool_path.inspect_trusted_executable(tool)


def test_replaced_tool_fails_identity_recheck(tmp_path: Path) -> None:
    tool = executable(tmp_path / "rustc")
    _, original = verify_tool_path.inspect_trusted_executable(tool)
    tool.unlink()
    tool.write_text("#!/bin/sh\nexit 99\n")
    tool.chmod(0o755)
    _, replacement = verify_tool_path.inspect_trusted_executable(tool)
    assert replacement != original


def fake_rust_toolchain(root: Path) -> Path:
    binary = root / "bin"
    binary.mkdir(parents=True)
    executable(
        binary / "rustc",
    ).write_text(
        "#!/bin/sh\n"
        'if [ "$1" = -Vv ]; then\n'
        "  printf 'release: 1.97.1\\ncommit-hash: "
        "8bab26f4f68e0e26f0bb7960be334d5b520ea452\\nhost: aarch64-apple-darwin\\n'\n"
        "fi\n"
    )
    executable(binary / "cargo").write_text("#!/bin/sh\nprintf 'release: 1.97.1\\n'\n")
    executable(binary / "cargo-clippy").write_text(
        "#!/bin/sh\nprintf 'clippy 0.1.97 (8bab26f4f6 2026-07-14)\\n'\n"
    )
    executable(binary / "cargo-fmt").write_text(
        "#!/bin/sh\nprintf 'rustfmt 1.9.0-stable (8bab26f4f6 2026-07-14)\\n'\n"
    )
    for tool in binary.iterdir():
        tool.chmod(0o755)
    return binary


def run_verifier(
    binary: Path, *, python_path: Path | None = None
) -> subprocess.CompletedProcess[str]:
    root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PATH"] = f"{binary}:/usr/bin:/bin:/usr/sbin:/sbin"
    environment["AQ_RUST_BIN"] = str(binary)
    if python_path is not None:
        environment["PYTHONPATH"] = str(python_path)
    return subprocess.run(
        ["/bin/sh", str(root / "tools/verify_rust_toolchain.sh")],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_shell_verifier_rejects_0775_tool_and_parent(tmp_path: Path) -> None:
    binary = fake_rust_toolchain(tmp_path / "toolchain")
    assert run_verifier(binary).returncode != 0

    (binary / "rustc").chmod(0o775)
    assert run_verifier(binary).returncode != 0
    (binary / "rustc").chmod(0o755)

    binary.chmod(0o775)
    assert run_verifier(binary).returncode != 0


def test_shell_verifier_does_not_execute_shadowed_helpers(tmp_path: Path) -> None:
    binary = fake_rust_toolchain(tmp_path / "toolchain")
    markers: list[Path] = []
    for name in ("python3", "awk", "grep", "dirname"):
        marker = tmp_path / f"{name}.executed"
        markers.append(marker)
        executable(binary / name).write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 99\n")
        (binary / name).chmod(0o755)
    assert run_verifier(binary).returncode != 0
    assert not any(marker.exists() for marker in markers)


def test_shell_verifier_ignores_python_environment_injection(tmp_path: Path) -> None:
    binary = fake_rust_toolchain(tmp_path / "toolchain")
    injected = tmp_path / "injected-python"
    injected.mkdir()
    marker = tmp_path / "pythonpath.executed"
    (injected / "argparse.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\nraise SystemExit(99)\n"
    )
    assert run_verifier(binary, python_path=injected).returncode != 0
    assert not marker.exists()


def test_build_script_uses_exact_rust_paths_without_path_prepend() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "tools/build_macos_package.sh").read_text()
    assert 'PATH="$AQ_RUST_BIN:$PATH"' not in script
    assert 'RUSTC="$AQ_RUST_BIN/rustc"' in script
    assert 'CARGO="$AQ_RUST_BIN/cargo"' in script
    assert 'rust_command_shim="$pyi_root/rust-command-shim"' in script
    assert '/bin/ln -s "$CARGO" "$rust_command_shim/cargo"' in script
    assert '/bin/ln -s "$RUSTC" "$rust_command_shim/rustc"' in script
    assert '/bin/ln -s "$PNPM" "$rust_command_shim/pnpm"' in script
    assert 'PATH="$rust_command_shim:$node_bin_dir:/usr/bin:/bin:/usr/sbin:/sbin"' in script
    assert '--runner "$CARGO"' in script
    assert "--features production" in script
    assert "target/aarch64-apple-darwin/release/bundle/macos/Agent Quota.app" in script
