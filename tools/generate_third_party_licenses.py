"""Generate a source-bound third-party license and attribution corpus."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LICENSE_NAME = re.compile(r"(?i)^(license|licence|copying|notice|copyright)([._-].*)?$")
LICENSE_IDS = ("Apache-2.0", "BSD-3-Clause", "MIT", "MPL-2.0")
UPSTREAM_SOURCES = ROOT / "THIRD_PARTY_UPSTREAM_LICENSE_SOURCES.json"


def command(*arguments: str) -> str:
    return subprocess.run(
        arguments,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def scope(component: dict[str, Any]) -> str:
    values = [
        item.get("value")
        for item in component.get("properties", [])
        if item.get("name") == "agent-quota:distribution-scope"
    ]
    if len(values) != 1 or not isinstance(values[0], str):
        raise ValueError(f"component scope is not singular: {component.get('bom-ref')}")
    return values[0]


def declared_licenses(component: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for item in component.get("licenses", []):
        license_data = item.get("license", {})
        value = license_data.get("id") or license_data.get("name")
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"component license metadata is invalid: {component.get('bom-ref')}")
        result.append(value.strip())
    if not result:
        raise ValueError(f"component license metadata is missing: {component.get('bom-ref')}")
    return result


def license_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        (path for path in directory.iterdir() if path.is_file() and LICENSE_NAME.match(path.name)),
        key=lambda path: path.name.casefold(),
    )


def cargo_packages() -> dict[tuple[str, str], dict[str, Any]]:
    metadata = json.loads(
        command(
            os.environ.get("CARGO", "cargo"),
            "metadata",
            "--locked",
            "--format-version=1",
            "--manifest-path",
            str(ROOT / "src-tauri" / "Cargo.toml"),
        )
    )
    return {(str(item["name"]), str(item["version"])): item for item in metadata["packages"]}


def npm_directory(name: str, version: str, component_scope: str) -> Path:
    if component_scope == "source-validation-only":
        candidate = ROOT / "docs" / "contracts" / "node_modules" / name
        candidates = [candidate] if candidate.is_dir() else []
    else:
        candidates = []
        direct = ROOT / "node_modules" / name
        if direct.is_dir():
            candidates.append(direct)
        candidates.extend(
            path
            for path in (ROOT / "node_modules" / ".pnpm").glob(f"*/node_modules/{name}")
            if path.is_dir()
        )
    matches = []
    for candidate in candidates:
        package_json = candidate / "package.json"
        if (
            package_json.is_file()
            and json.loads(package_json.read_text(encoding="utf-8")).get("version") == version
        ):
            matches.append(candidate)
    unique = {path.resolve() for path in matches}
    if len(unique) != 1:
        raise ValueError(f"npm license source is not singular: {name}@{version}")
    return unique.pop()


def python_files(name: str, version: str) -> tuple[list[Path], list[str], str | None]:
    distribution = importlib.metadata.distribution(name)
    if distribution.version != version:
        raise ValueError(f"Python distribution version mismatch: {name}@{version}")
    files = []
    for item in distribution.files or []:
        if LICENSE_NAME.match(Path(str(item)).name):
            path = Path(distribution.locate_file(item))
            if path.is_file():
                files.append(path)
    authors = [
        value
        for key in ("Author", "Author-email")
        if isinstance((value := distribution.metadata.get(key)), str) and value.strip()
    ]
    repository = distribution.metadata.get("Home-page")
    return sorted(set(files)), authors, repository if isinstance(repository, str) else None


def upstream_sources() -> dict[tuple[str, str], dict[str, Any]]:
    document = json.loads(UPSTREAM_SOURCES.read_text(encoding="utf-8"))
    entries = document.get("entries")
    if (
        document.get("schema") != "agent-quota-upstream-license-sources-v1"
        or not isinstance(entries, list)
        or document.get("entry_count") != len(entries)
    ):
        raise ValueError("upstream license source manifest is invalid")
    result = {(str(item["name"]), str(item["version"])): item for item in entries}
    if len(result) != len(entries):
        raise ValueError("upstream license source manifest has duplicate components")
    return result


def normalized_notice(
    source: str,
    source_uri: str,
    source_revision: str,
    text: str,
) -> dict[str, str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.endswith("\n"):
        normalized += "\n"
    if not normalized.strip() or len(normalized.encode("utf-8")) > 512 * 1024:
        raise ValueError(f"license text is empty or oversized: {source}")
    return {
        "source": source,
        "source_uri": source_uri,
        "source_revision": source_revision,
        "sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        "text": normalized,
    }


def build_corpus(sbom: dict[str, Any]) -> dict[str, Any]:
    cargo = cargo_packages()
    vendored = upstream_sources()
    entries: list[dict[str, Any]] = []
    for component in sbom.get("components", []):
        component_scope = scope(component)
        if component_scope in {"project", "lockfile-non-target"}:
            continue
        name = str(component["name"])
        version = str(component["version"])
        purl = str(component["purl"])
        authors: list[str] = []
        repository: str | None = None
        sources: list[tuple[str, str, str, str]] = []
        upstream_binding: dict[str, Any] | None = None
        cargo_package: dict[str, Any] | None = None
        if purl.startswith("pkg:cargo/"):
            cargo_package = cargo[(name, version)]
            directory = Path(cargo_package["manifest_path"]).parent
            authors = [str(value) for value in cargo_package.get("authors", [])]
            repository = cargo_package.get("repository")
            sources = [
                (
                    f"cargo:{name}@{version}/{path.name}",
                    f"{purl}#{path.name}",
                    f"{name}@{version}",
                    path.read_text(encoding="utf-8"),
                )
                for path in license_files(directory)
            ]
        elif purl.startswith("pkg:npm/"):
            directory = npm_directory(name, version, component_scope)
            package = json.loads((directory / "package.json").read_text(encoding="utf-8"))
            author = package.get("author")
            if isinstance(author, str):
                authors = [author]
            elif isinstance(author, dict) and isinstance(author.get("name"), str):
                authors = [author["name"]]
            repository_data = package.get("repository")
            repository = (
                repository_data.get("url") if isinstance(repository_data, dict) else repository_data
            )
            sources = [
                (
                    f"npm:{name}@{version}/{path.name}",
                    f"{purl}#{path.name}",
                    f"{name}@{version}",
                    path.read_text(encoding="utf-8"),
                )
                for path in license_files(directory)
            ]
        elif purl.startswith("pkg:pypi/"):
            files, authors, repository = python_files(name, version)
            sources = [
                (
                    f"pypi:{name}@{version}/{path.name}",
                    f"{purl}#{path.name}",
                    f"{name}@{version}",
                    path.read_text(encoding="utf-8"),
                )
                for path in files
            ]
        elif purl.startswith("pkg:generic/cpython@"):
            path = Path(sys.base_prefix) / "lib" / "python3.11" / "LICENSE.txt"
            sources = [
                (
                    f"cpython:{version}/LICENSE.txt",
                    f"https://github.com/python/cpython/blob/v{version}/LICENSE",
                    f"v{version}",
                    path.read_text(encoding="utf-8"),
                )
            ]
            authors = ["Python Software Foundation"]
            repository = "https://github.com/python/cpython"
        else:
            raise ValueError(f"unsupported distributed component: {purl}")
        licenses = declared_licenses(component)
        if not sources:
            if cargo_package is None:
                raise ValueError(f"packaged license files are missing: {name}@{version}")
            evidence = vendored.get((name, version))
            if not isinstance(evidence, dict):
                raise ValueError(
                    f"source-bound upstream license evidence is missing: {name}@{version}"
                )
            vcs_path = Path(cargo_package["manifest_path"]).parent / ".cargo_vcs_info.json"
            vcs = json.loads(vcs_path.read_text(encoding="utf-8"))
            if vcs.get("git", {}).get("sha1") != evidence.get("vcs_commit"):
                raise ValueError(f"upstream VCS commit mismatch: {name}@{version}")
            if vcs.get("path_in_vcs") not in {None, evidence.get("path_in_vcs")}:
                raise ValueError(f"upstream VCS path mismatch: {name}@{version}")
            normalized_repository = str(repository).rstrip("/")
            if normalized_repository != str(evidence.get("repository", "")).rstrip("/"):
                raise ValueError(f"upstream repository mismatch: {name}@{version}")
            identifiers = [item for item in LICENSE_IDS if item in " ".join(licenses)]
            if sorted(identifiers) != sorted(evidence.get("license_ids", [])):
                raise ValueError(f"upstream declared license mismatch: {name}@{version}")
            metadata = evidence.get("metadata")
            if not isinstance(metadata, dict):
                raise ValueError(f"upstream metadata evidence is missing: {name}@{version}")
            metadata_text = metadata.get("text")
            if not isinstance(metadata_text, str) or hashlib.sha256(
                metadata_text.encode()
            ).hexdigest() != metadata.get("sha256"):
                raise ValueError(f"upstream metadata digest mismatch: {name}@{version}")
            upstream_binding = {
                "repository": evidence["repository"],
                "vcs_commit": evidence["vcs_commit"],
                "path_in_vcs": evidence["path_in_vcs"],
                "license_ids": evidence["license_ids"],
                "metadata": metadata,
            }
            sources = [
                (
                    f"upstream:{name}@{version}/{Path(item['source_uri']).name}",
                    str(item["source_uri"]),
                    str(item["source_revision"]),
                    str(item["text"]),
                )
                for item in evidence.get("notices", [])
            ]
        notices = []
        seen: set[str] = set()
        for source, source_uri, source_revision, text in sources:
            notice = normalized_notice(source, source_uri, source_revision, text)
            if notice["sha256"] not in seen:
                notices.append(notice)
                seen.add(notice["sha256"])
        entries.append(
            {
                "bom_ref": component["bom-ref"],
                "name": name,
                "version": version,
                "scope": component_scope,
                "declared_licenses": licenses,
                "attribution": {"authors": authors, "repository": repository},
                "upstream_binding": upstream_binding,
                "notices": notices,
            }
        )
    return {
        "schema": "agent-quota-third-party-license-corpus-v1",
        "sbom_component_count": len(sbom.get("components", [])),
        "upstream_source_manifest_sha256": hashlib.sha256(
            UPSTREAM_SOURCES.read_bytes()
        ).hexdigest(),
        "entry_count": len(entries),
        "entries": sorted(entries, key=lambda item: str(item["bom_ref"])),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sbom", type=Path, required=True)
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument("--output", type=Path)
    output.add_argument("--check", type=Path)
    args = parser.parse_args()
    sbom = json.loads(args.sbom.read_text(encoding="utf-8"))
    document = build_corpus(sbom)
    rendered = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        if args.check is None or args.check.read_text(encoding="utf-8") != rendered:
            raise SystemExit("third-party license corpus drift")
        print(f"license_corpus_entries={document['entry_count']}")
        print("license_corpus_status=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
