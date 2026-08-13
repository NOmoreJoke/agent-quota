import runpy
from pathlib import Path

deployment_target_supported = runpy.run_path(
    Path(__file__).parents[1] / "tools" / "audit_macos_bundle.py"
)["deployment_target_supported"]
contains_local_build_path = runpy.run_path(
    Path(__file__).parents[1] / "tools" / "audit_macos_bundle.py"
)["contains_local_build_path"]
is_runtime_state_path = runpy.run_path(
    Path(__file__).parents[1] / "tools" / "audit_macos_bundle.py"
)["is_runtime_state_path"]


def test_deployment_target_accepts_macos_13_and_older() -> None:
    assert deployment_target_supported("11.0")
    assert deployment_target_supported("13.0")


def test_deployment_target_rejects_newer_macos() -> None:
    assert not deployment_target_supported("13.0.1")
    assert not deployment_target_supported("13.1")
    assert not deployment_target_supported("26.0")


def test_runtime_account_state_paths_are_rejected_from_bundle() -> None:
    from pathlib import PurePosixPath

    for relative in (
        "Contents/Resources/native-accounts-v1.json",
        "Contents/Resources/agent-quota.sqlite-wal",
        "Contents/Resources/Application Support/com.agentquota.desktop/state.json",
        "Contents/Resources/Local Storage/leveldb/000001.log",
    ):
        assert is_runtime_state_path(PurePosixPath(relative))
    assert not is_runtime_state_path(
        PurePosixPath("Contents/Resources/_internal/agent_quota/resources/provider_catalog_v1.json")
    )


def test_local_build_paths_are_rejected(tmp_path: Path) -> None:
    binary = tmp_path / "binary"
    binary.write_bytes(b"prefix/Users/example/.cargo/registry/src/suffix")
    assert contains_local_build_path(binary)
    binary.write_bytes(b"/build/home/.cargo/registry/src")
    assert not contains_local_build_path(binary)
