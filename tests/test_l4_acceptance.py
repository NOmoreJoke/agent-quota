"""Fail-closed tests for L4 holder live-lifecycle acceptance runner."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "l4_acceptance",
    Path(__file__).parents[1] / "tools/l4_acceptance.py",
)
assert SPEC is not None and SPEC.loader is not None
l4 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(l4)

REPO_ROOT = Path(__file__).parents[1]
MATRIX_PATH = REPO_ROOT / "docs/acceptance-matrix-v2.json"
COMMIT = "b" * 40


def _pass_evidence(commit: str, product_id: str, capabilities: dict[str, str]) -> dict[str, object]:
    return {
        "schema": l4.EVIDENCE_SCHEMA,
        "commit": commit,
        "product_id": product_id,
        "app_signing_mode": "apple-team",
        "macos_version": "15.4 arm64",
        "lifecycle": dict.fromkeys(l4.REQUIRED_LIFECYCLE_STAGES, True),
        "capabilities": capabilities,
        "notes": "Verified on holder Mac with redacted diagnostics.",
    }


def test_checklist_and_template_generation(tmp_path: Path) -> None:
    checklist = l4.build_checklist(MATRIX_PATH)
    assert len(checklist["products"]) == 9
    assert checklist["lifecycle_stages"] == list(l4.REQUIRED_LIFECYCLE_STAGES)

    out_path = tmp_path / "tpl.json"
    tpl = l4.build_template(COMMIT, "google-antigravity", MATRIX_PATH, out_path)
    assert out_path.is_file()
    assert tpl["commit"] == COMMIT
    assert tpl["product_id"] == "google-antigravity"
    assert tpl["app_signing_mode"] == "apple-team"
    assert tpl["lifecycle"] == dict.fromkeys(l4.REQUIRED_LIFECYCLE_STAGES, False)
    assert tpl["capabilities"] == {
        "window_5h": "BLOCKED_ACCOUNT",
        "window_week": "BLOCKED_ACCOUNT",
        "ai_credits_balance": "BLOCKED_ACCOUNT",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("notes", "leaked key sk-1234567890abcdef"),
        ("notes", "leaked oauth GOCSPX-secret_value_here"),
        ("notes", "Authorization: Bearer abcdef123456"),
        ("notes", "jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ"),
        ("notes", "holder email alice@example.com"),
        ("notes", "captured from mock server"),
        ("notes", "loaded test fixture payload"),
        ("notes", "synthetic run"),
        ("app_signing_mode", "adhoc-test-only"),
    ],
)
def test_record_rejects_secrets_emails_and_mock_markers(
    tmp_path: Path, field: str, value: str
) -> None:
    payload = _pass_evidence(COMMIT, "deepseek-api-balance-cn", {"wallet_balance": "PASS"})
    payload[field] = value
    input_path = tmp_path / "bad.json"
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        l4.record_evidence(
            commit=COMMIT,
            product_id="deepseek-api-balance-cn",
            input_path=input_path,
            evidence_dir=tmp_path / "evidence",
            matrix_path=MATRIX_PATH,
        )


def test_record_rejects_incomplete_lifecycle_or_bad_commit(tmp_path: Path) -> None:
    payload = _pass_evidence(COMMIT, "deepseek-api-balance-cn", {"wallet_balance": "PASS"})
    payload["lifecycle"]["reauth_401_recovery"] = False  # type: ignore[index]
    input_path = tmp_path / "incomplete.json"
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="all 7 lifecycle stages"):
        l4.record_evidence(
            commit=COMMIT,
            product_id="deepseek-api-balance-cn",
            input_path=input_path,
            evidence_dir=tmp_path / "evidence",
            matrix_path=MATRIX_PATH,
        )
    with pytest.raises(ValueError, match="40-character Git SHA-1"):
        l4.record_evidence(
            commit="not-a-sha",
            product_id="deepseek-api-balance-cn",
            input_path=input_path,
            evidence_dir=tmp_path / "evidence",
            matrix_path=MATRIX_PATH,
        )


def test_preflight_distinguishes_apple_dev_developer_id_and_adhoc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_dir = tmp_path / f"iteration-4-{COMMIT}-apple-team"
    app = artifact_dir / "Agent Quota.app"
    app.mkdir(parents=True)
    (artifact_dir / "signing-audit.json").write_text(
        json.dumps({"mode": "apple-team", "keychain_identity_stable": True}),
        encoding="utf-8",
    )
    (artifact_dir / "bundle-audit.json").write_text(
        json.dumps({"status": "pass", "errors": [], "codesign_verify_exit": 0}),
        encoding="utf-8",
    )
    (artifact_dir / "clean-install-audit.json").write_text(
        json.dumps({"status": "pass", "accounts_count": 0}),
        encoding="utf-8",
    )
    (artifact_dir / "build-provenance.json").write_text(
        json.dumps({"source_commit": COMMIT}),
        encoding="utf-8",
    )

    def mock_apple_dev(*command: str) -> subprocess.CompletedProcess[str]:
        if "-dv" in command:
            stderr = (
                "CodeDirectory v=20400 size=100 flags=0x0(none)\n"
                "Authority=Apple Development: Example (34Y68VQZ4R)\n"
                "TeamIdentifier=34Y68VQZ4R\n"
            )
            return subprocess.CompletedProcess(command, 0, stdout="", stderr=stderr)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(l4, "run_cmd", mock_apple_dev)
    res_dev = l4.run_preflight(app, artifact_dir)
    assert res_dev["authority_type"] == "apple-development"
    assert res_dev["ready_for_l4_holder_test"] is True
    assert res_dev["ready_for_public_notarization"] is False
    assert res_dev["notarized"] is False

    (artifact_dir / "notarization-audit.json").write_text(
        json.dumps(
            {
                "schema": "agent-quota-notarization-audit-v1",
                "commit": COMMIT,
                "status": "Accepted",
                "stapled_app": True,
                "stapled_dmg": True,
                "gatekeeper_assessed": True,
            }
        ),
        encoding="utf-8",
    )

    def mock_dev_id(*command: str) -> subprocess.CompletedProcess[str]:
        if "-dv" in command:
            stderr = (
                "CodeDirectory v=20500 size=100 flags=0x10000(runtime)\n"
                "Authority=Developer ID Application: Example Corp (34Y68VQZ4R)\n"
                "TeamIdentifier=34Y68VQZ4R\n"
            )
            return subprocess.CompletedProcess(command, 0, stdout="", stderr=stderr)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(l4, "run_cmd", mock_dev_id)
    res_prod = l4.run_preflight(app, artifact_dir)
    assert res_prod["authority_type"] == "developer-id"
    assert res_prod["hardened_runtime"] is True
    assert res_prod["ready_for_l4_holder_test"] is True
    assert res_prod["ready_for_public_notarization"] is True
    assert res_prod["notarized"] is True


def test_apply_matrix_dry_run_and_write_validates_against_schema(tmp_path: Path) -> None:
    tmp_matrix = tmp_path / "acceptance-matrix-v2.json"
    matrix_data = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    tmp_matrix.write_text(json.dumps(matrix_data, ensure_ascii=False, indent=2), encoding="utf-8")

    evidence_dir = tmp_path / f"l4-{COMMIT}"
    for product in matrix_data["products"]:
        if not product["current_creatable"]:
            continue
        caps = {
            cell["capability_id"]: "PASS"
            for cell in product["capabilities"]
            if cell["claimed"] and cell["release_denominator"]
        }
        src = tmp_path / f"in-{product['product_id']}.json"
        src.write_text(
            json.dumps(_pass_evidence(COMMIT, product["product_id"], caps)),
            encoding="utf-8",
        )
        l4.record_evidence(
            commit=COMMIT,
            product_id=product["product_id"],
            input_path=src,
            evidence_dir=evidence_dir,
            matrix_path=tmp_matrix,
        )

    artifact_dir = tmp_path / f"iteration-4-{COMMIT}-apple-team"
    artifact_dir.mkdir(parents=True)
    for name in l4.REQUIRED_PACKAGE_FILES:
        if name == "build-provenance.json":
            content = json.dumps(
                {
                    "source_commit": COMMIT,
                    "source_dirty": False,
                    "signing_mode": "apple-team",
                    "keychain_identity_stable": True,
                }
            )
        elif name == "signing-audit.json":
            content = json.dumps({"mode": "apple-team", "keychain_identity_stable": True})
        elif name == "bundle-audit.json":
            content = json.dumps({"status": "pass", "errors": []})
        elif name == "clean-install-audit.json":
            content = json.dumps({"status": "pass", "accounts_count": 0})
        else:
            content = "ok\n"
        (artifact_dir / name).write_text(content, encoding="utf-8")

    dry = l4.apply_matrix(
        commit=COMMIT,
        evidence_dir=evidence_dir,
        artifact_dir=artifact_dir,
        matrix_path=tmp_matrix,
        write=False,
    )
    assert dry["wrote"] is False
    assert len(dry["updated_products"]) == 7
    assert dry["gates"]["final_package_evidence"] == "PASS"
    assert dry["gates"]["holder_live_lifecycle"] == "PASS"
    assert dry["gates"]["developer_id_notarization"] == "BLOCKED_IMPLEMENTATION"
    # Dry-run must leave file untouched
    assert (
        json.loads(tmp_matrix.read_text(encoding="utf-8"))["formal_release_gates"][0]["status"]
        == "BLOCKED_ACCOUNT"
    )

    written = l4.apply_matrix(
        commit=COMMIT,
        evidence_dir=evidence_dir,
        artifact_dir=artifact_dir,
        matrix_path=tmp_matrix,
        write=True,
    )
    assert written["wrote"] is True
    updated_matrix = json.loads(tmp_matrix.read_text(encoding="utf-8"))
    gates = {g["gate_id"]: g for g in updated_matrix["formal_release_gates"]}
    assert gates["holder_live_lifecycle"]["status"] == "PASS"
    assert gates["holder_live_lifecycle"]["commit_binding"] == COMMIT
    assert gates["final_package_evidence"]["status"] == "PASS"
    assert gates["developer_id_notarization"]["status"] == "BLOCKED_IMPLEMENTATION"
