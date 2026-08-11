"""Fail closed when a shipped SBOM component lacks usable license metadata."""

from __future__ import annotations

import argparse
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
    args = parser.parse_args()
    document = json.loads(args.sbom.read_text(encoding="utf-8"))
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
    print(f"license_component_count={len(components)}")
    print("license_status=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
