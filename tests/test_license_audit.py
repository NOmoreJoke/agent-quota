from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


def _documents() -> tuple[dict[str, object], dict[str, object]]:
    components = []
    entries = []
    for name, version, license_name, text in (
        (
            "pyinstaller",
            "6.21.0",
            "GPLv2 with bootloader exception",
            "PyInstaller bootloader special exception\n",
        ),
        ("CPython", "3.11.15", "PSF-2.0", "PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2\n"),
    ):
        reference = f"pkg:test/{name}@{version}"
        components.append(
            {
                "bom-ref": reference,
                "name": name,
                "version": version,
                "licenses": [{"license": {"name": license_name}}],
                "properties": [
                    {"name": "agent-quota:distribution-scope", "value": "binary-runtime"}
                ],
            }
        )
        entries.append(
            {
                "bom_ref": reference,
                "name": name,
                "version": version,
                "scope": "binary-runtime",
                "declared_licenses": [license_name],
                "attribution": {"authors": [], "repository": None},
                "notices": [
                    {
                        "source": f"fixture:{name}",
                        "sha256": hashlib.sha256(text.encode()).hexdigest(),
                        "text": text,
                    }
                ],
            }
        )
    return (
        {"components": components},
        {
            "schema": "agent-quota-third-party-license-corpus-v1",
            "sbom_component_count": len(components),
            "entry_count": len(entries),
            "entries": entries,
        },
    )


def _run(
    tmp_path: Path, sbom: dict[str, object], corpus: dict[str, object]
) -> subprocess.CompletedProcess[str]:
    root = Path(__file__).resolve().parents[1]
    sbom_path = tmp_path / "sbom.json"
    corpus_path = tmp_path / "corpus.json"
    sbom_path.write_text(json.dumps(sbom), encoding="utf-8")
    corpus_path.write_text(json.dumps(corpus), encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(root / "tools" / "audit_sbom_licenses.py"),
            "--sbom",
            str(sbom_path),
            "--corpus",
            str(corpus_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_license_audit_accepts_closed_notice_corpus(tmp_path: Path) -> None:
    sbom, corpus = _documents()
    completed = _run(tmp_path, sbom, corpus)

    assert completed.returncode == 0, completed.stderr
    assert "license_status=ok" in completed.stdout


def test_license_audit_rejects_notice_digest_drift(tmp_path: Path) -> None:
    sbom, corpus = _documents()
    corpus["entries"][0]["notices"][0]["sha256"] = "0" * 64  # type: ignore[index]
    completed = _run(tmp_path, sbom, corpus)

    assert completed.returncode != 0
    assert "notice digest mismatch" in completed.stderr
