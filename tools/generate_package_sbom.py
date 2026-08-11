"""Generate a CycloneDX inventory from the authoritative lock files."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import re
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
    if len(value.encode("utf-8")) > 128 * 1024:
        raise ValueError("license metadata is oversized")
    return {"license": {"name": value}}


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


def set_scope(entry: dict[str, Any], value: str) -> None:
    properties = [
        item
        for item in entry.get("properties", [])
        if item.get("name") != "agent-quota:distribution-scope"
    ]
    properties.append({"name": "agent-quota:distribution-scope", "value": value})
    entry["properties"] = properties


def cargo_target_packages() -> set[tuple[str, str]]:
    output = command(
        os.environ.get("CARGO", "cargo"),
        "tree",
        "--manifest-path",
        str(ROOT / "src-tauri" / "Cargo.toml"),
        "--locked",
        "--target",
        "aarch64-apple-darwin",
        "--edges",
        "normal,build",
        "--prefix",
        "none",
        "--format",
        "{p}",
    )
    result: set[tuple[str, str]] = set()
    for line in output.splitlines():
        match = re.match(r"^(\S+) v(\S+)", line)
        if match:
            result.add((match.group(1), match.group(2)))
    if not result:
        raise ValueError("target Cargo dependency closure is empty")
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


def contract_validation_components() -> list[dict[str, Any]]:
    lock = json.loads(
        (ROOT / "docs" / "contracts" / "package-lock.json").read_text(encoding="utf-8")
    )
    packages = lock.get("packages")
    if not isinstance(packages, dict):
        raise ValueError("contract package lock is missing packages")
    result: list[dict[str, Any]] = []
    for package_path, package in packages.items():
        if not isinstance(package_path, str) or not package_path.startswith("node_modules/"):
            continue
        if not isinstance(package, dict):
            raise ValueError(f"invalid contract package entry: {package_path}")
        name = package_path.removeprefix("node_modules/")
        version = package.get("version")
        license_name = package.get("license")
        if not isinstance(version, str) or not isinstance(license_name, str):
            raise ValueError(f"contract package metadata is incomplete: {name}")
        entry = component("library", name, version, f"pkg:npm/{name}@{version}", license_name)
        entry["properties"] = [
            {"name": "agent-quota:distribution-scope", "value": "source-validation-only"}
        ]
        result.append(entry)
    if not result:
        raise ValueError("contract package lock has no dependencies")
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
        key = (
            str(entry.get("name", "")).casefold().replace("_", "-"),
            str(entry.get("version", "")),
        )
        if declared := python_licenses.get(key):
            entry["licenses"] = [license_entry(declared)]
        marker = next(
            (
                item.get("value")
                for item in entry.get("properties", [])
                if item.get("name") == "uv:package:marker"
            ),
            "",
        )
        set_scope(
            entry,
            "lockfile-non-target" if "sys_platform == 'win32'" in marker else "binary-build-tool",
        )
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
            component("framework", "CPython", "3.11.15", "pkg:generic/cpython@3.11.15", "PSF-2.0"),
        ]
    )
    for entry in components[-3:-1]:
        set_scope(entry, "project")
    set_scope(components[-1], "binary-runtime")
    components.extend(contract_validation_components())

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
                set_scope(entry, "binary-runtime")
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
    target_packages = cargo_target_packages()
    for package in cargo_lock["package"]:
        name = str(package["name"])
        version = str(package["version"])
        entry = component(
            "library",
            name,
            version,
            f"pkg:cargo/{name}@{version}",
            cargo_licenses.get((name, version)),
        )
        set_scope(
            entry,
            "project"
            if name == "agent-quota-desktop"
            else (
                "binary-runtime" if (name, version) in target_packages else "lockfile-non-target"
            ),
        )
        components.append(entry)

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
