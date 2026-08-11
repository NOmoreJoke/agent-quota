import hashlib
import json
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


def test_committed_license_corpus_has_hashed_psf_and_pyinstaller_notices() -> None:
    root = Path(__file__).resolve().parents[1]
    document = json.loads((root / "THIRD_PARTY_LICENSE_CORPUS.json").read_text(encoding="utf-8"))

    assert document["schema"] == "agent-quota-third-party-license-corpus-v1"
    assert document["entry_count"] == len(document["entries"]) == 245
    by_name = {entry["name"]: entry for entry in document["entries"]}
    for entry in document["entries"]:
        assert entry["notices"]
        for notice in entry["notices"]:
            assert hashlib.sha256(notice["text"].encode()).hexdigest() == notice["sha256"]
    pyinstaller = "\n".join(item["text"] for item in by_name["pyinstaller"]["notices"])
    cpython = "\n".join(item["text"] for item in by_name["CPython"]["notices"])
    assert "bootloader" in pyinstaller.casefold()
    assert "exception" in pyinstaller.casefold()
    assert "PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2" in cpython
