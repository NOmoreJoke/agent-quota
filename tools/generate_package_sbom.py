"""Generate a CycloneDX inventory from the authoritative lock files."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import subprocess
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LOCKED_PYTHON_LICENSES = {
    # Target-conditional Windows dependencies are present in uv.lock/CycloneDX
    # but are not installed on the macOS build host, so importlib.metadata
    # cannot report them. Values are pinned to their exact PyPI release metadata.
    ("pefile", "2024.8.26"): "MIT",
    ("pywin32-ctypes", "0.2.3"): "BSD-3-Clause",
}


def command(*arguments: str) -> str:
    return subprocess.run(
        arguments,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def license_entry(value: str) -> dict[str, Any]:
    value = value.strip()
    if not value:
        raise ValueError("empty license")
    if "\n" not in value and len(value) <= 128:
        return {"license": {"name": value}}
    return {"license": {"name": "License text declared in package metadata"}}


def component(
    kind: str,
    name: str,
    version: str,
    purl: str,
    license_name: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": kind,
        "bom-ref": purl,
        "name": name,
        "version": version,
        "purl": purl,
    }
    if license_name:
        result["licenses"] = [license_entry(license_name)]
    return result


def installed_python_licenses() -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name")
        if not name:
            continue
        declared = distribution.metadata.get("License-Expression")
        if not declared:
            declared = distribution.metadata.get("License")
        if not declared:
            classifiers = distribution.metadata.get_all("Classifier", [])
            declared = next(
                (item.rsplit(" :: ", 1)[-1] for item in classifiers if "License ::" in item),
                None,
            )
        if declared:
            result[(name.casefold().replace("_", "-"), distribution.version)] = declared
    return result


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
    python_licenses = installed_python_licenses()
    python_licenses.update(LOCKED_PYTHON_LICENSES)
    for entry in components:
        key = (str(entry.get("name", "")).casefold().replace("_", "-"), str(entry.get("version", "")))
        if declared := python_licenses.get(key):
            entry["licenses"] = [license_entry(declared)]
    components.extend(
        [
            component(
                "application",
                "agent-quota-desktop",
                "0.1.0",
                "pkg:generic/agent-quota-desktop@0.1.0",
                "MIT",
            ),
            component(
                "application",
                "AgentQuotaNative",
                "0.1.0",
                "pkg:generic/agent-quota-native@0.1.0",
                "MIT",
            ),
            component(
                "framework", "CPython", "3.11.15", "pkg:generic/cpython@3.11.15", "PSF-2.0"
            ),
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
    cargo_metadata = json.loads(
        command(
            os.environ.get("CARGO", "cargo"),
            "metadata",
            "--locked",
            "--format-version=1",
            "--manifest-path",
            str(ROOT / "src-tauri" / "Cargo.toml"),
        )
    )
    cargo_licenses = {
        (str(package["name"]), str(package["version"])): package.get("license")
        for package in cargo_metadata["packages"]
    }
    for package in cargo_lock["package"]:
        name = str(package["name"])
        version = str(package["version"])
        components.append(
            component(
                "library",
                name,
                version,
                f"pkg:cargo/{name}@{version}",
                cargo_licenses.get((name, version)),
            )
        )

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
                "MIT",
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
