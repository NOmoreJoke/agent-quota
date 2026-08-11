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
FALLBACK_IDS = ("Apache-2.0", "BSD-3-Clause", "MIT", "MPL-2.0")
MIT_TERMS = """Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the \"Software\"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
BSD3_TERMS = """Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice,
   this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.
3. Neither the name of the copyright holder nor the names of its contributors
   may be used to endorse or promote products derived from this software
   without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS \"AS IS\"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""


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


def fallback_texts(
    license_values: list[str],
    authors: list[str],
    cargo: dict[tuple[str, str], dict[str, Any]],
) -> list[tuple[str, str]]:
    rendered = " ".join(license_values)
    identifiers = [identifier for identifier in FALLBACK_IDS if identifier in rendered]
    if not identifiers:
        raise ValueError(f"no approved fallback license template for {rendered}")
    holders = ", ".join(authors) if authors else "the upstream contributors"
    result: list[tuple[str, str]] = []
    for identifier in identifiers:
        if identifier == "MIT":
            text = f"Copyright holders reported by package metadata: {holders}\n\n{MIT_TERMS}"
        elif identifier == "BSD-3-Clause":
            text = f"Copyright holders reported by package metadata: {holders}\n\n{BSD3_TERMS}"
        else:
            template_name = "bit-vec" if identifier == "Apache-2.0" else "cssparser"
            package = next(item for key, item in cargo.items() if key[0] == template_name)
            candidates = license_files(Path(package["manifest_path"]).parent)
            selected = next(
                (
                    path
                    for path in candidates
                    if identifier.split("-", 1)[0].casefold() in path.name.casefold()
                    or (identifier == "MPL-2.0" and path.name.casefold() == "license")
                ),
                None,
            )
            if selected is None:
                raise ValueError(f"canonical fallback source is missing: {identifier}")
            text = selected.read_text(encoding="utf-8")
        result.append((f"canonical-template:{identifier}", text))
    return result


def normalized_notice(source: str, text: str) -> dict[str, str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.endswith("\n"):
        normalized += "\n"
    if not normalized.strip() or len(normalized.encode("utf-8")) > 512 * 1024:
        raise ValueError(f"license text is empty or oversized: {source}")
    return {
        "source": source,
        "sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        "text": normalized,
    }


def build_corpus(sbom: dict[str, Any]) -> dict[str, Any]:
    cargo = cargo_packages()
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
        sources: list[tuple[str, str]] = []
        if purl.startswith("pkg:cargo/"):
            package = cargo[(name, version)]
            directory = Path(package["manifest_path"]).parent
            authors = [str(value) for value in package.get("authors", [])]
            repository = package.get("repository")
            sources = [
                (f"cargo:{name}@{version}/{path.name}", path.read_text(encoding="utf-8"))
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
                (f"npm:{name}@{version}/{path.name}", path.read_text(encoding="utf-8"))
                for path in license_files(directory)
            ]
        elif purl.startswith("pkg:pypi/"):
            files, authors, repository = python_files(name, version)
            sources = [
                (f"pypi:{name}@{version}/{path.name}", path.read_text(encoding="utf-8"))
                for path in files
            ]
        elif purl.startswith("pkg:generic/cpython@"):
            path = Path(sys.base_prefix) / "lib" / "python3.11" / "LICENSE.txt"
            sources = [(f"cpython:{version}/LICENSE.txt", path.read_text(encoding="utf-8"))]
            authors = ["Python Software Foundation"]
            repository = "https://github.com/python/cpython"
        else:
            raise ValueError(f"unsupported distributed component: {purl}")
        licenses = declared_licenses(component)
        if not sources:
            sources = fallback_texts(licenses, authors, cargo)
        notices = []
        seen: set[str] = set()
        for source, text in sources:
            notice = normalized_notice(source, text)
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
                "notices": notices,
            }
        )
    return {
        "schema": "agent-quota-third-party-license-corpus-v1",
        "sbom_component_count": len(sbom.get("components", [])),
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
