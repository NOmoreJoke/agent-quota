"""Generate a deterministic bundle inventory."""

from __future__ import annotations

import argparse
import hashlib
import os
import stat
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest(root: Path) -> list[str]:
    rows = ["# path\ttype\tmode\tbytes\tsha256-or-target\txattr-names"]
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        metadata = path.lstat()
        mode = f"{stat.S_IMODE(metadata.st_mode):04o}"
        xattr_result = subprocess.run(
            ["/usr/bin/xattr", str(path)],
            check=False,
            capture_output=True,
            text=True,
        )
        xattrs = ",".join(sorted(xattr_result.stdout.splitlines())) or "-"
        if path.is_symlink():
            rows.append(f"{relative}\tsymlink\t{mode}\t0\t{os.readlink(path)}\t{xattrs}")
        elif path.is_file():
            rows.append(f"{relative}\tfile\t{mode}\t{metadata.st_size}\t{sha256(path)}\t{xattrs}")
        elif path.is_dir():
            rows.append(f"{relative}\tdirectory\t{mode}\t0\t-\t{xattrs}")
        else:
            rows.append(f"{relative}\tother\t{mode}\t0\t-\t{xattrs}")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    if not root.is_dir():
        raise SystemExit("bundle root must be a directory")
    args.output.write_text("\n".join(manifest(root)) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
