from __future__ import annotations

import json
from pathlib import Path

from agent_quota.providers import MANIFESTS


def load_catalog() -> dict[str, object]:
    path = Path(__file__).parents[1] / "src/agent_quota/resources/provider_catalog_v1.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_provider_catalog_has_exact_screenshot_and_agent_coverage() -> None:
    catalog = load_catalog()
    rows = catalog["rows"]
    assert isinstance(rows, list)
    assert len(rows) == 78
    assert len({row["row_id"] for row in rows}) == 78
    labels = {row["screenshot_label"] for row in rows}
    assert {
        "Custom Configuration",
        "Codex",
        "Claude Code",
        "WorkBuddy",
        "QoderWork/QwenWork",
        "Trae",
        "Cursor",
    } <= labels


def test_catalog_supported_rows_close_over_fixed_adapter_registry() -> None:
    rows = load_catalog()["rows"]
    adapter_ids = {adapter_id for row in rows for adapter_id in row["adapter_ids"]}
    assert adapter_ids == set(MANIFESTS)
    assert all(row["adapter_ids"] for row in rows if row["support_tier"] == "Supported")
    assert all(not row["adapter_ids"] for row in rows if row["support_tier"] != "Supported")


def test_custom_configuration_and_mainstream_agents_fail_closed() -> None:
    rows = {row["screenshot_label"]: row for row in load_catalog()["rows"]}
    assert rows["Custom Configuration"]["support_tier"] == "Unsupported"
    for label in ("Codex", "Claude Code", "WorkBuddy", "Trae", "Cursor"):
        assert rows[label]["support_tier"] == "Experimental"
        assert rows[label]["window"]["status"] != "supported"
        assert rows[label]["wallet"]["status"] != "supported"
