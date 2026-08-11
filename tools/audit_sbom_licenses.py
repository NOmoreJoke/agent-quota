"""Fail closed when a shipped SBOM component lacks usable license metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

DENIED_MARKERS = (
    "AGPL",
    "BUSL",
    "BUSINESS SOURCE",
    "COMMONS CLAUSE",
    "LICENSE TEXT DECLARED IN PACKAGE METADATA",
    "SSPL",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sbom", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    args = parser.parse_args()
    document = json.loads(args.sbom.read_text(encoding="utf-8"))
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    components = document.get("components")
    if not isinstance(components, list) or not components:
        raise SystemExit("SBOM components are missing")
    missing: list[str] = []
    denied: list[str] = []
    for component in components:
        reference = str(component.get("bom-ref", "<missing-ref>"))
        licenses = component.get("licenses")
        if not isinstance(licenses, list) or not licenses:
            missing.append(reference)
            continue
        rendered = json.dumps(licenses, sort_keys=True).upper()
        if any(marker in rendered for marker in DENIED_MARKERS):
            denied.append(reference)
    if missing or denied:
        raise SystemExit(
            f"license audit failed: missing={sorted(missing)!r} denied={sorted(denied)!r}"
        )
    entries = corpus.get("entries")
    if corpus.get("schema") != "agent-quota-third-party-license-corpus-v1" or not isinstance(
        entries, list
    ):
        raise SystemExit("third-party license corpus is invalid")
    if corpus.get("entry_count") != len(entries) or corpus.get("sbom_component_count") != len(
        components
    ):
        raise SystemExit("third-party license corpus counts do not match the SBOM")
    by_reference = {entry.get("bom_ref"): entry for entry in entries}
    if len(by_reference) != len(entries):
        raise SystemExit("third-party license corpus has duplicate component references")
    required: set[str] = set()
    notice_count = 0
    notice_bytes = 0
    for component in components:
        properties = component.get("properties", [])
        scopes = [
            item.get("value")
            for item in properties
            if item.get("name") == "agent-quota:distribution-scope"
        ]
        if len(scopes) != 1:
            raise SystemExit(f"component distribution scope is invalid: {component.get('bom-ref')}")
        if scopes[0] in {"project", "lockfile-non-target"}:
            continue
        reference = str(component["bom-ref"])
        required.add(reference)
        entry = by_reference.get(reference)
        if not isinstance(entry, dict) or entry.get("scope") != scopes[0]:
            raise SystemExit(f"license corpus component binding is missing: {reference}")
        if entry.get("name") != component.get("name") or entry.get("version") != component.get(
            "version"
        ):
            raise SystemExit(f"license corpus component identity drift: {reference}")
        expected_licenses = [
            item["license"].get("id") or item["license"].get("name")
            for item in component["licenses"]
        ]
        if entry.get("declared_licenses") != expected_licenses:
            raise SystemExit(f"license corpus declaration drift: {reference}")
        notices = entry.get("notices")
        if not isinstance(notices, list) or not notices:
            raise SystemExit(f"license corpus notices are missing: {reference}")
        for notice in notices:
            text = notice.get("text")
            digest = notice.get("sha256")
            source = notice.get("source")
            if (
                not isinstance(text, str)
                or not isinstance(digest, str)
                or not isinstance(source, str)
                or not source
            ):
                raise SystemExit(f"license corpus notice is malformed: {reference}")
            encoded = text.encode("utf-8")
            if hashlib.sha256(encoded).hexdigest() != digest:
                raise SystemExit(f"license corpus notice digest mismatch: {reference}")
            notice_count += 1
            notice_bytes += len(encoded)
    if set(by_reference) != required:
        raise SystemExit("license corpus component set does not match distributed SBOM scope")
    pyinstaller = next(
        (entry for entry in entries if entry.get("name") == "pyinstaller"),
        None,
    )
    pyinstaller_text = (
        "\n".join(notice["text"] for notice in pyinstaller.get("notices", []))
        if isinstance(pyinstaller, dict)
        else ""
    )
    if (
        "exception" not in pyinstaller_text.casefold()
        or "bootloader" not in pyinstaller_text.casefold()
    ):
        raise SystemExit("PyInstaller bootloader license exception is missing")
    cpython = next((entry for entry in entries if entry.get("name") == "CPython"), None)
    cpython_text = (
        "\n".join(notice["text"] for notice in cpython.get("notices", []))
        if isinstance(cpython, dict)
        else ""
    )
    if "PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2" not in cpython_text:
        raise SystemExit("CPython PSF license text is missing")
    print(f"license_component_count={len(components)}")
    print(f"license_corpus_component_count={len(entries)}")
    print(f"license_notice_count={notice_count}")
    print(f"license_notice_bytes={notice_bytes}")
    print("license_status=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
