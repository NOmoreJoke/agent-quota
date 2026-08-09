#!/usr/bin/env python3
"""Emit closed source-to-artifact provenance for a local macOS RC."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--dmg", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if re.fullmatch(r"[0-9a-f]{40}", args.commit) is None:
        raise SystemExit("invalid source commit")
    executable = args.app / "Contents/MacOS/agent-quota-desktop"
    if not executable.is_file() or not args.dmg.is_file():
        raise SystemExit("artifact is incomplete")

    document = {
        "app_executable_sha256": sha256(executable),
        "artifact_class": "local unsigned development package",
        "dmg_sha256": sha256(args.dmg),
        "schema": "agent-quota-build-provenance-v1",
        "source_commit": args.commit,
        "source_dirty": False,
    }
    args.output.write_text(
        json.dumps(document, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
