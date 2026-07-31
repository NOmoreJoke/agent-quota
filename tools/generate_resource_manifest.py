"""Pin every executable resource byte before the Rust release build."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect(root: Path, source: Path, destination: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for path in sorted(source.rglob("*"), key=lambda item: item.relative_to(source).as_posix()):
        if path.is_symlink():
            raise ValueError(f"resource symlink is forbidden: {path}")
        if not path.is_file():
            continue
        relative = destination / path.relative_to(source)
        metadata = path.stat()
        entries.append(
            {
                "bytes": metadata.st_size,
                "mode": stat.S_IMODE(metadata.st_mode),
                "path": relative.as_posix(),
                "sha256": sha256(path),
            }
        )
    if not entries:
        raise ValueError(f"empty resource tree: {source.relative_to(root)}")
    return entries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generated", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generated = args.generated.resolve(strict=True)
    entries = collect(
        generated,
        generated / "AgentQuotaNative.app",
        Path("native-helper/AgentQuotaNative.app"),
    )
    entries.extend(
        collect(
            generated,
            generated / "agent-quota-sidecar",
            Path("sidecar"),
        )
    )
    document = {
        "artifact_class": "local unsigned development package",
        "entries": sorted(entries, key=lambda entry: str(entry["path"])),
        "schema": "agent-quota-resource-manifest-v1",
    }
    args.output.write_text(
        json.dumps(document, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
