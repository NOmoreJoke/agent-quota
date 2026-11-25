"""Fail-closed unit tests for Apple Developer ID notarization & stapling tool."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "notarize_macos_package",
    Path(__file__).parents[1] / "tools/notarize_macos_package.py",
)
assert SPEC is not None and SPEC.loader is not None
notarize = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(notarize)

COMMIT = "a" * 40


def _make_fake_artifact_dir(tmp_path: Path, *, mode: str = "apple-team") -> Path:
    artifact_dir = tmp_path / f"iteration-4-{COMMIT}-{mode}"
    app = artifact_dir / "Agent Quota.app"
    exe = app / "Contents/MacOS/agent-quota-desktop"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"desktop-exe-bytes")
    dmg = artifact_dir / "Agent-Quota-0.1.0-arm64-local-development.dmg"
    dmg.write_bytes(b"dmg-bytes")
    (artifact_dir / "signing-audit.json").write_text(
        json.dumps(
            {
                "schema": "agent-quota-signing-audit-v1",
                "mode": mode,
                "keychain_identity_stable": mode == "apple-team",
                "notarized": False,
                "components": {},
            }
        ),
        encoding="utf-8",
    )
    (artifact_dir / "build-provenance.json").write_text(
        json.dumps(
            {
                "schema": "agent-quota-build-provenance-v1",
                "source_commit": COMMIT,
                "source_dirty": False,
                "signing_mode": mode,
                "keychain_identity_stable": mode == "apple-team",
            }
        ),
        encoding="utf-8",
    )
    return artifact_dir


def test_rejects_adhoc_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    artifact_dir = _make_fake_artifact_dir(tmp_path, mode="adhoc-test-only")
    monkeypatch.setenv("AQ_NOTARY_KEYCHAIN_PROFILE", "agent-quota-notary")
    with pytest.raises(ValueError, match="apple-team"):
        notarize.notarize_artifact_dir(artifact_dir)


def test_rejects_apple_development_and_missing_hardened_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_dir = _make_fake_artifact_dir(tmp_path)
    monkeypatch.setenv("AQ_NOTARY_KEYCHAIN_PROFILE", "agent-quota-notary")

    def fake_dev_cert(*command: str) -> subprocess.CompletedProcess[str]:
        if "-dv" in command:
            stderr = (
                "CodeDirectory v=20400 size=100 flags=0x0(none)\n"
                "Authority=Apple Development: Example (TEAM)\n"
                "TeamIdentifier=ABCDE12345\n"
            )
            return subprocess.CompletedProcess(command, 0, stdout="", stderr=stderr)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(notarize, "run_cmd", fake_dev_cert)
    with pytest.raises(ValueError, match="Developer ID Application"):
        notarize.notarize_artifact_dir(artifact_dir)

    def fake_no_runtime(*command: str) -> subprocess.CompletedProcess[str]:
        if "-dv" in command:
            stderr = (
                "CodeDirectory v=20500 size=100 flags=0x0(none)\n"
                "Authority=Developer ID Application: Example Corp (ABCDE12345)\n"
                "TeamIdentifier=ABCDE12345\n"
            )
            return subprocess.CompletedProcess(command, 0, stdout="", stderr=stderr)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(notarize, "run_cmd", fake_no_runtime)
    with pytest.raises(ValueError, match="Hardened Runtime"):
        notarize.notarize_artifact_dir(artifact_dir)


def test_rejects_missing_profile_and_rejected_submission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_dir = _make_fake_artifact_dir(tmp_path)
    monkeypatch.delenv("AQ_NOTARY_KEYCHAIN_PROFILE", raising=False)

    def fake_valid_dev_id(*command: str) -> subprocess.CompletedProcess[str]:
        if "-dv" in command:
            stderr = (
                "CodeDirectory v=20500 size=100 flags=0x10000(runtime)\n"
                "Authority=Developer ID Application: Example Corp (ABCDE12345)\n"
                "TeamIdentifier=ABCDE12345\n"
            )
            return subprocess.CompletedProcess(command, 0, stdout="", stderr=stderr)
        if "notarytool" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"id": "sub-123", "status": "Invalid"}),
                stderr="",
            )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(notarize, "run_cmd", fake_valid_dev_id)
    with pytest.raises(ValueError, match="keychain profile"):
        notarize.notarize_artifact_dir(artifact_dir)

    with pytest.raises(ValueError, match="did not accept DMG"):
        notarize.notarize_artifact_dir(artifact_dir, profile="notary-prof")


def test_dry_run_and_happy_path_notarization_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_dir = _make_fake_artifact_dir(tmp_path)
    calls: list[tuple[str, ...]] = []

    def fake_success(*command: str) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if "-dv" in command:
            stderr = (
                "CodeDirectory v=20500 size=100 flags=0x10000(runtime)\n"
                "Authority=Developer ID Application: Example Corp (ABCDE12345)\n"
                "TeamIdentifier=ABCDE12345\n"
            )
            return subprocess.CompletedProcess(command, 0, stdout="", stderr=stderr)
        if "notarytool" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"id": "sub-accepted-001", "status": "Accepted"}),
                stderr="",
            )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(notarize, "run_cmd", fake_success)
    dry = notarize.notarize_artifact_dir(artifact_dir, profile="notary-prof", dry_run=True)
    assert dry["status"] == "ready"
    assert dry["hardened_runtime"] is True
    assert not any("notarytool" in cmd for cmd in calls)

    report = notarize.notarize_artifact_dir(artifact_dir, profile="notary-prof", dry_run=False)
    audit_path = artifact_dir / "notarization-audit.json"
    assert audit_path.is_file()
    assert report == json.loads(audit_path.read_text(encoding="utf-8"))
    assert report["schema"] == "agent-quota-notarization-audit-v1"
    assert report["commit"] == COMMIT
    assert report["submission_id"] == "sub-accepted-001"
    assert report["status"] == "Accepted"
    assert report["stapled_app"] is True
    assert report["stapled_dmg"] is True
    assert report["gatekeeper_assessed"] is True
    assert report["dmg_sha256"] == hashlib.sha256(b"dmg-bytes").hexdigest()
    assert report["app_executable_sha256"] == hashlib.sha256(b"desktop-exe-bytes").hexdigest()
    assert any("stapler" in cmd and "staple" in cmd for cmd in calls)
    assert any("/usr/sbin/spctl" in cmd for cmd in calls)
