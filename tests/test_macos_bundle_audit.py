import runpy
from pathlib import Path

deployment_target_supported = runpy.run_path(
    Path(__file__).parents[1] / "tools" / "audit_macos_bundle.py"
)["deployment_target_supported"]


def test_deployment_target_accepts_macos_13_and_older() -> None:
    assert deployment_target_supported("11.0")
    assert deployment_target_supported("13.0")


def test_deployment_target_rejects_newer_macos() -> None:
    assert not deployment_target_supported("13.0.1")
    assert not deployment_target_supported("13.1")
    assert not deployment_target_supported("26.0")
