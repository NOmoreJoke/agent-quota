from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path


def test_launch_acceptance_matrix_is_closed_and_complete() -> None:
    root = Path(__file__).parent.parent
    document = json.loads((root / "docs/acceptance-matrix-v2.json").read_text())
    allowed = set(document["allowed_statuses"])
    products = document["products"]
    summary = document["scope_summary"]
    assert document["schema"] == "agent-quota-acceptance-matrix-v2"
    assert date.fromisoformat(document["decided_at"])
    assert document["completion_rule"] == (
        "complete iff every capability cell with claimed=true and release_denominator=true "
        "is PASS and every formal release gate is PASS"
    )
    assert summary == {
        "brand_count": 7,
        "product_card_count": 10,
        "target_actionable_candidate_count": 7,
        "current_creatable_count": 5,
        "implementation_blocked_candidate_count": 2,
        "disabled_information_card_count": 3,
    }
    assert len(products) == summary["product_card_count"]
    assert len({product["brand"] for product in products}) == summary["brand_count"]
    assert len({product["product_id"] for product in products}) == len(products)
    assert sum(product["target_actionable_candidate"] for product in products) == 7
    assert sum(product["current_creatable"] for product in products) == 5
    assert (
        sum(
            product["target_actionable_candidate"] and not product["current_creatable"]
            for product in products
        )
        == 2
    )
    assert (
        sum(product["release_status"] == "blocked-out-of-release-scope" for product in products)
        == 3
    )
    assert {product["adapter_id"] for product in products if product["current_creatable"]} == {
        "deepseek",
        "glm-cn",
        "kimi-cn",
        "kimi-code",
        "minimax-cn",
    }
    target_adapters = {
        product["adapter_id"] for product in products if product["target_actionable_candidate"]
    }
    assert target_adapters == {
        "deepseek",
        "glm-cn",
        "kimi-cn",
        "kimi-code",
        "minimax-cn",
        "volc-plan",
        "volc-wallet",
    }
    disabled = [product for product in products if not product["target_actionable_candidate"]]
    assert all(product["adapter_id"] is None for product in disabled)
    capabilities = [cell for product in products for cell in product["capabilities"]]
    assert all(cell["status"] in allowed for cell in capabilities)
    assert all(cell["official_evidence"] for cell in capabilities)
    assert all(
        url.startswith("https://") for cell in capabilities for url in cell["official_evidence"]
    )
    assert all(cell["release_denominator"] == cell["claimed"] for cell in capabilities)
    assert all(not cell["claimed"] for product in disabled for cell in product["capabilities"])
    wallet = next(product for product in products if product["adapter_id"] == "volc-wallet")
    assert wallet["current_creatable"] is False
    assert wallet["capabilities"][0]["claimed"] is False
    assert "official GET" in wallet["capabilities"][0]["promotion_gate"]
    assert document["disabled_information_card_policy"] == {
        "creatable": False,
        "credential_collection": False,
        "provider_request": False,
        "web_scraping": False,
        "release_denominator": False,
    }
    gates = document["formal_release_gates"]
    gate_statuses = set(document["formal_release_gate_allowed_statuses"])
    assert {gate["gate_id"] for gate in gates} == {
        "holder_live_lifecycle",
        "launch_scope_implementation",
        "developer_id_notarization",
        "final_package_evidence",
    }
    assert all(gate["required"] for gate in gates)
    assert all(gate["status"] in gate_statuses for gate in gates)
    assert all(gate["status"] != "PASS" for gate in gates)
    assert all(gate["commit_binding"] is None for gate in gates)
    assert all(gate["evidence"] == [] for gate in gates)
    assert all(
        not product["current_creatable"] or product["target_actionable_candidate"]
        for product in products
    )
    assert all(
        not cell["claimed"] or product["target_actionable_candidate"]
        for product in products
        for cell in product["capabilities"]
    )


def test_acceptance_matrix_schema_closes_every_object() -> None:
    root = Path(__file__).parent.parent
    schema = json.loads((root / "docs/acceptance-matrix-v2.schema.json").read_text())
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    assert schema["properties"]["scope_summary"]["additionalProperties"] is False
    assert schema["properties"]["disabled_information_card_policy"]["additionalProperties"] is False
    assert schema["$defs"]["formalReleaseGate"]["additionalProperties"] is False
    assert schema["$defs"]["product"]["additionalProperties"] is False
    assert schema["$defs"]["capability"]["additionalProperties"] is False


def test_acceptance_matrix_validator_accepts_current_blocked_contract() -> None:
    root = Path(__file__).parent.parent
    completed = subprocess.run(
        ["tools/validate_acceptance_matrix.sh"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout == "acceptance-matrix-v2 status=blocked\n"


def test_acceptance_matrix_validator_rejects_gate_bypass(tmp_path: Path) -> None:
    root = Path(__file__).parent.parent
    document = json.loads((root / "docs/acceptance-matrix-v2.json").read_text())
    document["formal_release_gates"][0]["status"] = "PASS"
    mutated = tmp_path / "matrix.json"
    mutated.write_text(json.dumps(document))
    completed = subprocess.run(
        ["tools/validate_acceptance_matrix.sh", str(mutated)],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "PASS gate lacks commit-bound evidence" in completed.stderr


def test_acceptance_matrix_validator_rejects_scope_and_gate_shrink(tmp_path: Path) -> None:
    root = Path(__file__).parent.parent
    document = json.loads((root / "docs/acceptance-matrix-v2.json").read_text())
    for product in document["products"]:
        for cell in product["capabilities"]:
            cell["claimed"] = False
            cell["release_denominator"] = False
    for gate in document["formal_release_gates"]:
        gate["required"] = False
    mutated = tmp_path / "matrix.json"
    mutated.write_text(json.dumps(document))
    completed = subprocess.run(
        ["tools/validate_acceptance_matrix.sh", str(mutated)],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "approved claimed capability set mismatch" in completed.stderr


def test_current_native_create_allowlist_matches_scope_record() -> None:
    root = Path(__file__).parent.parent
    document = json.loads((root / "docs/acceptance-matrix-v2.json").read_text())
    expected = {
        product["adapter_id"] for product in document["products"] if product["current_creatable"]
    }
    swift = (root / "native/AgentQuotaNative.swift").read_text()
    create_ids = swift.split("private let creatableProviderIDs = [", 1)[1].split("]", 1)[0]
    actual = {value.strip().strip('"') for value in create_ids.split(",") if value.strip()}
    assert actual == expected


def test_repository_contains_open_source_handoff_files() -> None:
    root = Path(__file__).parent.parent
    for relative in (
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
        "ACCEPTANCE_MATRIX.md",
        "KNOWN_ISSUES.md",
        "RELEASE_HANDOFF.md",
    ):
        assert (root / relative).is_file()
