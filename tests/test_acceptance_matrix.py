from __future__ import annotations

import json
from pathlib import Path


def test_hard_acceptance_matrix_is_closed_and_complete() -> None:
    root = Path(__file__).parent.parent
    document = json.loads((root / "docs/acceptance-matrix-v1.json").read_text())
    allowed = set(document["allowed_statuses"])
    cells = document["cells"]
    assert len(cells) == 21
    assert {(cell["provider"], cell["capability"]) for cell in cells} == {
        (provider, capability)
        for provider in (
            "DeepSeek",
            "Alibaba Bailian",
            "Volcengine",
            "MiniMax",
            "Zhipu GLM",
            "Kimi",
            "Xiaomi MiMo",
        )
        for capability in ("wallet_balance", "token_plan_5h", "token_plan_week")
    }
    assert all(cell["status"] in allowed for cell in cells)
    assert all(cell["official_evidence"] for cell in cells)
    assert all(url.startswith("https://") for cell in cells for url in cell["official_evidence"])
    assert all(cell["implementation"] != "present" or cell["machine_contract"] for cell in cells)


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
