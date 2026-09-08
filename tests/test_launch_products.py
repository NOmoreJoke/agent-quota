from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from agent_quota.providers import MANIFESTS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.generate_launch_products import outputs, project

ROOT = Path(__file__).parents[1]


def test_generated_launch_policy_is_current() -> None:
    for path, expected in outputs(ROOT).items():
        assert path.read_text() == expected
    subprocess.run(
        [str(ROOT / ".venv/bin/python"), "tools/generate_launch_products.py", "--check"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )


def test_native_python_endpoints_remain_aligned() -> None:
    swift = (ROOT / "native/AgentQuotaNative.swift").read_text()
    native = dict(
        (provider, (host, path))
        for provider, host, path in re.findall(
            r'ProviderDefinition\(id: "([^"]+)", label: "[^"]+", host: "([^"]+)", path: "([^"]+)"',
            swift,
        )
    )
    assert set(native) == set(MANIFESTS)
    for provider, definition in MANIFESTS.items():
        endpoint = urlsplit(definition.endpoint)
        assert native[provider] == (endpoint.hostname, endpoint.path)


@pytest.mark.parametrize("field", ["adapter_id", "current_creatable", "claimed"])
def test_information_products_cannot_gain_execution_mapping(field: str) -> None:
    document = json.loads((ROOT / "docs/acceptance-matrix-v2.json").read_text())
    product = next(p for p in document["products"] if not p["target_actionable_candidate"])
    if field == "claimed":
        product["capabilities"][0]["claimed"] = True
    else:
        product[field] = "deepseek" if field == "adapter_id" else True
    with pytest.raises(ValueError, match="information card"):
        project(document)


def test_policy_rejects_unknown_adapter_and_duplicate_product() -> None:
    document = json.loads((ROOT / "docs/acceptance-matrix-v2.json").read_text())
    invalid = copy.deepcopy(document)
    invalid["products"][0]["adapter_id"] = "unreviewed-adapter"
    with pytest.raises(ValueError, match="no fixed Python adapter"):
        project(invalid)
    invalid = copy.deepcopy(document)
    invalid["products"][1]["product_id"] = invalid["products"][0]["product_id"]
    with pytest.raises(ValueError, match="identities"):
        project(invalid)


def test_policy_rejects_count_change_and_non_boolean_flags() -> None:
    document = json.loads((ROOT / "docs/acceptance-matrix-v2.json").read_text())
    invalid = copy.deepcopy(document)
    invalid["products"][0]["current_creatable"] = False
    with pytest.raises(ValueError, match="count"):
        project(invalid)
    invalid["products"][0]["current_creatable"] = 1
    with pytest.raises(ValueError, match="booleans"):
        project(invalid)


def test_launch_policy_rejects_duplicate_adapter_mapping() -> None:
    document = json.loads((ROOT / "docs/acceptance-matrix-v2.json").read_text())
    document["products"][1]["adapter_id"] = document["products"][0]["adapter_id"]
    with pytest.raises(ValueError, match="duplicate launch adapter"):
        project(document)
