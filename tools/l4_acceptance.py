#!/usr/bin/env python3
"""Interactive & fail-closed L4 holder live-lifecycle acceptance runner."""

from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
from pathlib import Path

EVIDENCE_SCHEMA = "agent-quota-l4-evidence-v1"
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_LIFECYCLE_STAGES = (
    "add_account",
    "keychain_label_and_acl",
    "initial_refresh",
    "restart_persistence_refresh",
    "reauth_401_recovery",
    "stale_lkg_preserved",
    "delete_and_purge_cleanup",
)
FORBIDDEN_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("api_key_prefix", re.compile(r"sk-[A-Za-z0-9_-]{8,}")),
    ("google_oauth_secret", re.compile(r"GOCSPX-[A-Za-z0-9_-]+")),
    ("bearer_token", re.compile(r"Bearer\s+\S+")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")),
    ("email_address", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    (
        "synthetic_or_mock_marker",
        re.compile(
            r"(?:\bmock\b|\bfixture\b|\bsynthetic\b|adhoc-test-only|test-only)",
            re.IGNORECASE,
        ),
    ),
)
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MATRIX_PATH = REPO_ROOT / "docs/acceptance-matrix-v2.json"
REQUIRED_PACKAGE_FILES = (
    "build-provenance.json",
    "signing-audit.json",
    "bundle-audit.json",
    "clean-install-audit.json",
    "sbom.cdx.json",
    "license-audit.txt",
    "artifact-sha256.txt",
)


def validate_commit_sha(commit: str) -> str:
    if COMMIT_RE.fullmatch(commit) is None:
        raise ValueError("Commit binding must be a lowercase 40-character Git SHA-1")
    return commit


def scan_forbidden_strings(value: object, *, path: str = "$") -> None:
    if isinstance(value, str):
        for label, pattern in FORBIDDEN_SECRET_PATTERNS:
            if pattern.search(value):
                raise ValueError(f"Redaction / anti-mock check rejected {path}: matched {label}")
        return
    if isinstance(value, list):
        for idx, item in enumerate(value):
            scan_forbidden_strings(item, path=f"{path}[{idx}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            scan_forbidden_strings(str(key), path=f"{path}.{key}(key)")
            scan_forbidden_strings(item, path=f"{path}.{key}")


def run_cmd(*command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True)


def parse_codesign_app(app: Path) -> dict[str, object]:
    if not app.is_dir():
        raise ValueError(f"Application bundle not found: {app}")
    run_cmd("/usr/bin/codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app))
    output = run_cmd("/usr/bin/codesign", "-dv", "--verbose=4", str(app))
    text = output.stdout + "\n" + output.stderr
    authorities: list[str] = []
    signature_kind = ""
    hardened_runtime = False
    team_id: str | None = None
    for line in text.splitlines():
        if line.startswith("Authority="):
            authorities.append(line.split("=", 1)[1].strip())
        elif line.startswith("Signature="):
            signature_kind = line.split("=", 1)[1].strip()
        elif line.startswith("CodeDirectory "):
            match = re.search(r"\bflags=0x[0-9a-fA-F]+\(([^)]*)\)", line)
            if match:
                flags = {flag.strip().lower() for flag in match.group(1).split(",") if flag.strip()}
                hardened_runtime = "runtime" in flags
        elif line.startswith("TeamIdentifier="):
            raw_team = line.split("=", 1)[1].strip()
            team_id = None if raw_team == "not set" else raw_team

    if any(auth.startswith("Developer ID Application:") for auth in authorities):
        authority_type = "developer-id"
    elif any(auth.startswith("Apple Development:") for auth in authorities):
        authority_type = "apple-development"
    elif signature_kind == "adhoc" or not authorities:
        authority_type = "adhoc"
    else:
        authority_type = "other"

    return {
        "authority_type": authority_type,
        "authorities": authorities,
        "hardened_runtime": hardened_runtime,
        "team_id": team_id,
    }


def _read_json_if_exists(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else None


def run_preflight(app: Path, artifact_dir: Path | None) -> dict[str, object]:
    resolved_artifact_dir = artifact_dir
    if resolved_artifact_dir is None and (app.parent / "signing-audit.json").is_file():
        resolved_artifact_dir = app.parent

    signature = parse_codesign_app(app)
    signing_audit = (
        _read_json_if_exists(resolved_artifact_dir / "signing-audit.json")
        if resolved_artifact_dir
        else None
    )
    bundle_audit = (
        _read_json_if_exists(resolved_artifact_dir / "bundle-audit.json")
        if resolved_artifact_dir
        else None
    )
    clean_install_audit = (
        _read_json_if_exists(resolved_artifact_dir / "clean-install-audit.json")
        if resolved_artifact_dir
        else None
    )
    provenance = (
        _read_json_if_exists(resolved_artifact_dir / "build-provenance.json")
        if resolved_artifact_dir
        else None
    )
    notarization_audit = (
        _read_json_if_exists(resolved_artifact_dir / "notarization-audit.json")
        if resolved_artifact_dir
        else None
    )

    signing_stable = bool(
        signing_audit
        and signing_audit.get("mode") == "apple-team"
        and signing_audit.get("keychain_identity_stable") is True
    )
    bundle_ok = bool(
        bundle_audit
        and bundle_audit.get("status") == "pass"
        and bundle_audit.get("errors") == []
        and bundle_audit.get("codesign_verify_exit") == 0
    )
    clean_install_ok = bool(
        clean_install_audit
        and clean_install_audit.get("status") == "pass"
        and clean_install_audit.get("accounts_count") == 0
    )
    provenance_commit = provenance.get("source_commit") if provenance else None
    notarized = bool(
        notarization_audit
        and notarization_audit.get("schema") == "agent-quota-notarization-audit-v1"
        and notarization_audit.get("status") == "Accepted"
        and notarization_audit.get("stapled_app") is True
        and notarization_audit.get("stapled_dmg") is True
        and notarization_audit.get("gatekeeper_assessed") is True
        and (provenance_commit is None or notarization_audit.get("commit") == provenance_commit)
    )
    ready_for_l4_holder_test = (
        signature["authority_type"] in {"apple-development", "developer-id"}
        and signing_stable
        and bundle_ok
        and clean_install_ok
    )
    ready_for_public_notarization = bool(
        signature["authority_type"] == "developer-id"
        and signature["hardened_runtime"] is True
        and signing_stable
    )

    next_steps: list[str] = []
    if ready_for_l4_holder_test:
        next_steps.append(
            "Launch Agent Quota.app and execute the 7 lifecycle checks for each creatable product."
        )
        next_steps.append(
            "Generate templates via tools/l4_acceptance.py template and record redacted results."
        )
    else:
        next_steps.append(
            "Build an apple-team package via ./tools/build_apple_signed_package.sh first."
        )
    if not ready_for_public_notarization:
        next_steps.append(
            "Public notarization still requires a Developer ID Application "
            "certificate with Hardened Runtime."
        )

    return {
        "schema": "agent-quota-l4-preflight-v1",
        "app": app.name,
        "commit": provenance_commit,
        "authority_type": signature["authority_type"],
        "hardened_runtime": signature["hardened_runtime"],
        "team_id": signature["team_id"],
        "signing_stable": signing_stable,
        "bundle_audit_pass": bundle_ok,
        "clean_install_pass": clean_install_ok,
        "notarized": notarized,
        "ready_for_l4_holder_test": ready_for_l4_holder_test,
        "ready_for_public_notarization": ready_for_public_notarization,
        "next_steps": next_steps,
    }


def load_matrix(matrix_path: Path) -> dict[str, object]:
    document = json.loads(matrix_path.read_text(encoding="utf-8"))
    if (
        not isinstance(document, dict)
        or document.get("schema") != "agent-quota-acceptance-matrix-v2"
    ):
        raise ValueError("Invalid acceptance matrix document")
    return document


def _products_by_id(matrix: dict[str, object]) -> dict[str, dict[str, object]]:
    products = matrix.get("products")
    if not isinstance(products, list):
        raise ValueError("Acceptance matrix missing products array")
    return {str(item["product_id"]): item for item in products if isinstance(item, dict)}


def _claimed_capabilities(product: dict[str, object]) -> list[str]:
    capabilities = product.get("capabilities", [])
    if not isinstance(capabilities, list):
        return []
    return [
        str(cell["capability_id"])
        for cell in capabilities
        if isinstance(cell, dict) and cell.get("claimed") and cell.get("release_denominator")
    ]


def build_checklist(matrix_path: Path, product_id: str | None = None) -> dict[str, object]:
    matrix = load_matrix(matrix_path)
    by_id = _products_by_id(matrix)
    if product_id is not None:
        product = by_id.get(product_id)
        if product is None or not product.get("target_actionable_candidate"):
            raise ValueError(f"Unknown or disabled target candidate product: {product_id}")
        selected = [product]
    else:
        selected = [
            item for item in by_id.values() if item.get("target_actionable_candidate") is True
        ]
    return {
        "schema": "agent-quota-l4-checklist-v1",
        "lifecycle_stages": list(REQUIRED_LIFECYCLE_STAGES),
        "products": [
            {
                "product_id": item["product_id"],
                "display_name": item["display_name"],
                "adapter_id": item["adapter_id"],
                "current_creatable": item["current_creatable"],
                "release_status": item["release_status"],
                "claimed_capabilities": _claimed_capabilities(item),
            }
            for item in selected
        ],
    }


def build_template(
    commit: str, product_id: str, matrix_path: Path, output: Path | None = None
) -> dict[str, object]:
    validate_commit_sha(commit)
    matrix = load_matrix(matrix_path)
    product = _products_by_id(matrix).get(product_id)
    if product is None or not product.get("target_actionable_candidate"):
        raise ValueError(f"Unknown or disabled target candidate product: {product_id}")
    template: dict[str, object] = {
        "schema": EVIDENCE_SCHEMA,
        "commit": commit,
        "product_id": product_id,
        "app_signing_mode": "apple-team",
        "macos_version": "",
        "lifecycle": dict.fromkeys(REQUIRED_LIFECYCLE_STAGES, False),
        "capabilities": dict.fromkeys(_claimed_capabilities(product), "BLOCKED_ACCOUNT"),
        "notes": "",
    }
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(template, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return template


def validate_evidence_payload(
    payload: object,
    *,
    expected_commit: str,
    product: dict[str, object],
    allowed_statuses: set[str],
) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("Evidence payload must be a JSON object")
    expected_keys = {
        "schema",
        "commit",
        "product_id",
        "app_signing_mode",
        "macos_version",
        "lifecycle",
        "capabilities",
        "notes",
    }
    if set(payload.keys()) != expected_keys:
        raise ValueError("Evidence payload has missing or unexpected fields")
    if payload["schema"] != EVIDENCE_SCHEMA:
        raise ValueError("Unsupported L4 evidence schema")
    if payload["commit"] != expected_commit:
        raise ValueError("Evidence commit does not match expected commit SHA-1")
    if payload["product_id"] != product["product_id"]:
        raise ValueError("Evidence product_id does not match target product")
    if payload["app_signing_mode"] != "apple-team":
        raise ValueError("L4 holder evidence requires app_signing_mode == 'apple-team'")

    macos_version = payload["macos_version"]
    notes = payload["notes"]
    if not isinstance(macos_version, str) or not isinstance(notes, str):
        raise ValueError("macos_version and notes must be strings")

    lifecycle = payload["lifecycle"]
    if (
        not isinstance(lifecycle, dict)
        or set(lifecycle.keys()) != set(REQUIRED_LIFECYCLE_STAGES)
        or any(not isinstance(value, bool) for value in lifecycle.values())
    ):
        raise ValueError("Evidence lifecycle must contain exact boolean stage keys")

    capabilities = payload["capabilities"]
    expected_caps = set(_claimed_capabilities(product))
    if not isinstance(capabilities, dict) or set(capabilities.keys()) != expected_caps:
        raise ValueError("Evidence capabilities must match claimed product capabilities")
    for cap_id, status in capabilities.items():
        if not isinstance(status, str) or status not in allowed_statuses:
            raise ValueError(f"Invalid capability status for {cap_id}: {status!r}")
        if status == "PASS":
            if not all(lifecycle.values()):
                raise ValueError(
                    f"Capability {cap_id} cannot be PASS unless all 7 lifecycle stages succeeded"
                )
            if not macos_version.strip():
                raise ValueError("macos_version is required when recording PASS evidence")

    scan_forbidden_strings(payload)
    return {
        "schema": EVIDENCE_SCHEMA,
        "commit": expected_commit,
        "product_id": product["product_id"],
        "app_signing_mode": "apple-team",
        "macos_version": macos_version.strip(),
        "lifecycle": {stage: bool(lifecycle[stage]) for stage in REQUIRED_LIFECYCLE_STAGES},
        "capabilities": {cap: str(capabilities[cap]) for cap in sorted(expected_caps)},
        "notes": notes.strip(),
    }


def record_evidence(
    *,
    commit: str,
    product_id: str,
    input_path: Path,
    evidence_dir: Path,
    matrix_path: Path,
) -> Path:
    validate_commit_sha(commit)
    matrix = load_matrix(matrix_path)
    allowed_statuses = {str(item) for item in matrix.get("allowed_statuses", [])}
    product = _products_by_id(matrix).get(product_id)
    if product is None or not product.get("target_actionable_candidate"):
        raise ValueError(f"Unknown or disabled target candidate product: {product_id}")
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    validated = validate_evidence_payload(
        raw,
        expected_commit=commit,
        product=product,
        allowed_statuses=allowed_statuses,
    )
    evidence_dir.mkdir(parents=True, exist_ok=True)
    destination = evidence_dir / f"{product_id}.json"
    destination.write_text(
        json.dumps(validated, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def _format_ref(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def _verify_package_evidence(artifact_dir: Path, commit: str) -> list[str] | None:
    if not artifact_dir.is_dir():
        return None
    for filename in REQUIRED_PACKAGE_FILES:
        if not (artifact_dir / filename).is_file():
            return None
    provenance = _read_json_if_exists(artifact_dir / "build-provenance.json")
    signing = _read_json_if_exists(artifact_dir / "signing-audit.json")
    bundle = _read_json_if_exists(artifact_dir / "bundle-audit.json")
    clean = _read_json_if_exists(artifact_dir / "clean-install-audit.json")
    if not (provenance and signing and bundle and clean):
        return None
    if (
        provenance.get("source_commit") != commit
        or provenance.get("source_dirty") is not False
        or provenance.get("signing_mode") != "apple-team"
        or provenance.get("keychain_identity_stable") is not True
    ):
        return None
    if signing.get("mode") != "apple-team" or signing.get("keychain_identity_stable") is not True:
        return None
    if bundle.get("status") != "pass" or bundle.get("errors") != []:
        return None
    if clean.get("status") != "pass" or clean.get("accounts_count") != 0:
        return None
    return [_format_ref(artifact_dir / filename) for filename in REQUIRED_PACKAGE_FILES]


def _verify_notarization_evidence(artifact_dir: Path, commit: str) -> str | None:
    audit_path = artifact_dir / "notarization-audit.json"
    audit = _read_json_if_exists(audit_path)
    if not audit:
        return None
    if (
        audit.get("schema") != "agent-quota-notarization-audit-v1"
        or audit.get("commit") != commit
        or audit.get("status") != "Accepted"
        or audit.get("stapled_app") is not True
        or audit.get("stapled_dmg") is not True
        or audit.get("gatekeeper_assessed") is not True
    ):
        return None
    return _format_ref(audit_path)


def apply_matrix(
    *,
    commit: str,
    evidence_dir: Path,
    artifact_dir: Path | None,
    matrix_path: Path,
    write: bool,
) -> dict[str, object]:
    validate_commit_sha(commit)
    if not evidence_dir.is_dir():
        raise ValueError(f"Evidence directory does not exist: {evidence_dir}")

    original_text = matrix_path.read_text(encoding="utf-8")
    matrix = copy.deepcopy(load_matrix(matrix_path))
    allowed_statuses = {str(item) for item in matrix.get("allowed_statuses", [])}
    by_id = _products_by_id(matrix)

    recorded_evidence: dict[str, tuple[Path, dict[str, object]]] = {}
    for file_path in sorted(evidence_dir.glob("*.json")):
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        product_id = payload.get("product_id") if isinstance(payload, dict) else None
        if not isinstance(product_id, str) or product_id not in by_id:
            raise ValueError(f"Unknown product in evidence file: {file_path.name}")
        product = by_id[product_id]
        if not product.get("target_actionable_candidate"):
            raise ValueError(f"Non-target product in evidence file: {product_id}")
        validated = validate_evidence_payload(
            payload,
            expected_commit=commit,
            product=product,
            allowed_statuses=allowed_statuses,
        )
        recorded_evidence[product_id] = (file_path, validated)

    updated_products: list[str] = []
    for product_id, (_path, evidence) in recorded_evidence.items():
        product = by_id[product_id]
        lifecycle = evidence["lifecycle"]
        assert isinstance(lifecycle, dict)
        if not all(lifecycle.values()):
            continue
        cap_statuses = evidence["capabilities"]
        assert isinstance(cap_statuses, dict)
        cells = product["capabilities"]
        assert isinstance(cells, list)
        claimed_cells = [
            cell
            for cell in cells
            if isinstance(cell, dict) and cell.get("claimed") and cell.get("release_denominator")
        ]
        for cell in claimed_cells:
            cell["status"] = cap_statuses[str(cell["capability_id"])]
        if claimed_cells and all(cell["status"] == "PASS" for cell in claimed_cells):
            product["release_status"] = "holder-live-accepted"
        updated_products.append(product_id)

    gates = {
        str(gate["gate_id"]): gate
        for gate in matrix["formal_release_gates"]  # type: ignore[index]
        if isinstance(gate, dict)
    }
    if artifact_dir is not None:
        package_refs = _verify_package_evidence(artifact_dir, commit)
        if package_refs is not None:
            gates["final_package_evidence"]["status"] = "PASS"
            gates["final_package_evidence"]["commit_binding"] = commit
            gates["final_package_evidence"]["evidence"] = package_refs
        notarization_ref = _verify_notarization_evidence(artifact_dir, commit)
        if notarization_ref is not None:
            gates["developer_id_notarization"]["status"] = "PASS"
            gates["developer_id_notarization"]["commit_binding"] = commit
            gates["developer_id_notarization"]["evidence"] = [notarization_ref]

    creatable_products = [item for item in by_id.values() if item.get("current_creatable") is True]
    if creatable_products and all(
        str(item["product_id"]) in updated_products
        and all(
            cell.get("status") == "PASS"
            for cell in item.get("capabilities", [])  # type: ignore[union-attr]
            if isinstance(cell, dict) and cell.get("claimed") and cell.get("release_denominator")
        )
        for item in creatable_products
    ):
        gates["holder_live_lifecycle"]["status"] = "PASS"
        gates["holder_live_lifecycle"]["commit_binding"] = commit
        gates["holder_live_lifecycle"]["evidence"] = [
            _format_ref(recorded_evidence[str(item["product_id"])][0])
            for item in creatable_products
        ]

    target_candidates = [
        item for item in by_id.values() if item.get("target_actionable_candidate") is True
    ]
    scope_summary = matrix["scope_summary"]
    assert isinstance(scope_summary, dict)
    if (
        scope_summary.get("implementation_blocked_candidate_count") == 0
        and target_candidates
        and all(item.get("current_creatable") is True for item in target_candidates)
    ):
        gates["launch_scope_implementation"]["status"] = "PASS"
        gates["launch_scope_implementation"]["commit_binding"] = commit
        gates["launch_scope_implementation"]["evidence"] = [
            "src/agent_quota/resources/launch_products_v1.json"
        ]

    summary = {
        "schema": "agent-quota-l4-apply-summary-v1",
        "commit": commit,
        "wrote": write,
        "updated_products": sorted(updated_products),
        "gates": {gate_id: gate["status"] for gate_id, gate in sorted(gates.items())},
    }

    if write:
        matrix_path.write_text(
            json.dumps(matrix, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        try:
            run_cmd(
                "/bin/sh",
                str(REPO_ROOT / "tools/validate_acceptance_matrix.sh"),
                str(matrix_path),
            )
        except Exception:
            matrix_path.write_text(original_text, encoding="utf-8")
            raise

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight_p = subparsers.add_parser("preflight")
    preflight_p.add_argument("--app", type=Path, required=True)
    preflight_p.add_argument("--artifact-dir", type=Path, default=None)

    checklist_p = subparsers.add_parser("checklist")
    checklist_p.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX_PATH)
    checklist_p.add_argument("--product", default=None)

    template_p = subparsers.add_parser("template")
    template_p.add_argument("--commit", required=True)
    template_p.add_argument("--product", required=True)
    template_p.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX_PATH)
    template_p.add_argument("--output", type=Path, default=None)

    record_p = subparsers.add_parser("record")
    record_p.add_argument("--commit", required=True)
    record_p.add_argument("--product", required=True)
    record_p.add_argument("--input", type=Path, required=True)
    record_p.add_argument("--evidence-dir", type=Path, required=True)
    record_p.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX_PATH)

    apply_p = subparsers.add_parser("apply-matrix")
    apply_p.add_argument("--commit", required=True)
    apply_p.add_argument("--evidence-dir", type=Path, required=True)
    apply_p.add_argument("--artifact-dir", type=Path, default=None)
    apply_p.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX_PATH)
    apply_p.add_argument("--write", action="store_true")

    args = parser.parse_args()
    if args.command == "preflight":
        result: object = run_preflight(args.app, args.artifact_dir)
    elif args.command == "checklist":
        result = build_checklist(args.matrix, args.product)
    elif args.command == "template":
        result = build_template(args.commit, args.product, args.matrix, args.output)
    elif args.command == "record":
        dest = record_evidence(
            commit=args.commit,
            product_id=args.product,
            input_path=args.input,
            evidence_dir=args.evidence_dir,
            matrix_path=args.matrix,
        )
        result = {"status": "recorded", "path": dest.name}
    else:
        result = apply_matrix(
            commit=args.commit,
            evidence_dir=args.evidence_dir,
            artifact_dir=args.artifact_dir,
            matrix_path=args.matrix,
            write=args.write,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        detail = (
            error.stderr.strip()
            if isinstance(error, subprocess.CalledProcessError) and error.stderr
            else str(error)
        )
        raise SystemExit(f"l4_acceptance failed: {detail}") from None
