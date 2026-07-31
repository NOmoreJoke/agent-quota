"""Generate a CycloneDX inventory from the authoritative lock files."""

from __future__ import annotations

import argparse
import json
import subprocess
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def command(*arguments: str) -> str:
    return subprocess.run(
        arguments,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def component(kind: str, name: str, version: str, purl: str) -> dict[str, Any]:
    return {
        "type": kind,
        "bom-ref": purl,
        "name": name,
        "version": version,
        "purl": purl,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    python_bom: dict[str, Any] = json.loads(
        command(
            "uv",
            "export",
            "--frozen",
            "--no-default-groups",
            "--group",
            "package",
            "--format",
            "cyclonedx1.5",
        )
    )
    components: list[dict[str, Any]] = list(python_bom.get("components", []))
    components.extend(
        [
            component(
                "application",
                "agent-quota-desktop",
                "0.1.0",
                "pkg:generic/agent-quota-desktop@0.1.0",
            ),
            component(
                "application",
                "AgentQuotaNative",
                "0.1.0",
                "pkg:generic/agent-quota-native@0.1.0",
            ),
            component("framework", "CPython", "3.11.15", "pkg:generic/cpython@3.11.15"),
        ]
    )

    license_groups: dict[str, list[dict[str, Any]]] = json.loads(
        command("pnpm", "licenses", "list", "--prod", "--json")
    )
    for license_name, packages in license_groups.items():
        for package in packages:
            for version in package["versions"]:
                entry = component(
                    "library",
                    package["name"],
                    version,
                    f"pkg:npm/{package['name']}@{version}",
                )
                entry["licenses"] = [{"license": {"id": license_name}}]
                components.append(entry)

    cargo_lock = tomllib.loads((ROOT / "src-tauri" / "Cargo.lock").read_text(encoding="utf-8"))
    for package in cargo_lock["package"]:
        name = str(package["name"])
        version = str(package["version"])
        components.append(component("library", name, version, f"pkg:cargo/{name}@{version}"))

    unique: dict[str, dict[str, Any]] = {}
    for entry in components:
        unique[str(entry["bom-ref"])] = entry
    ordered = sorted(
        unique.values(),
        key=lambda entry: (
            str(entry["type"]),
            str(entry["name"]).casefold(),
            str(entry["version"]),
        ),
    )
    bom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "component": component(
                "application",
                "agent-quota-desktop",
                "0.1.0",
                "pkg:generic/agent-quota-desktop@0.1.0",
            ),
            "properties": [
                {
                    "name": "agent-quota:artifact-class",
                    "value": "local unsigned development package",
                },
                {"name": "agent-quota:target", "value": "aarch64-apple-darwin"},
            ],
        },
        "components": ordered,
    }
    args.output.write_text(
        json.dumps(bom, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
