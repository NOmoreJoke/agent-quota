import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.generate_package_sbom import contract_validation_components


def test_contract_validation_dependencies_are_inventoried() -> None:
    components = contract_validation_components()
    by_name = {entry["name"]: entry for entry in components}

    assert set(by_name) == {
        "ajv",
        "fast-deep-equal",
        "fast-uri",
        "json-schema-traverse",
        "require-from-string",
    }
    assert by_name["fast-uri"]["licenses"] == [{"license": {"name": "BSD-3-Clause"}}]
    assert all(
        entry["properties"]
        == [{"name": "agent-quota:distribution-scope", "value": "source-validation-only"}]
        for entry in components
    )
