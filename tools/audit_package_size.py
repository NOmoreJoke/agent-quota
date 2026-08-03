#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import stat
import sys
from pathlib import Path

FORBIDDEN_PARTS = frozenset({"__pycache__", "tests", ".cache", "cache", "debug"})


def fail(message: str) -> int:
    print(f"package-audit: {message}", file=sys.stderr)
    return 1


def validate_root(root: Path) -> int | None:
    try:
        root_stat = root.lstat()
    except FileNotFoundError:
        return fail("root does not exist")
    if stat.S_ISLNK(root_stat.st_mode):
        return fail("root must not be symlink")
    if not stat.S_ISDIR(root_stat.st_mode):
        return fail("root must be directory")
    return None


def audit(root: Path, max_mib: float) -> int:
    if not math.isfinite(max_mib) or max_mib <= 0:
        return fail("max-mib must be finite and positive")
    invalid_root = validate_root(root)
    if invalid_root is not None:
        return invalid_root

    total = 0
    for entry in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = entry.relative_to(root)
        if any(part in FORBIDDEN_PARTS for part in relative.parts):
            return fail(f"forbidden path: {relative}")
        try:
            entry_stat = entry.lstat()
        except FileNotFoundError:
            return fail(f"entry disappeared: {relative}")
        mode = entry_stat.st_mode
        if stat.S_ISLNK(mode):
            return fail(f"symlink is not allowed: {relative}")
        if stat.S_ISREG(mode):
            total += entry_stat.st_size
        elif not stat.S_ISDIR(mode):
            return fail(f"unsupported file type: {relative}")

    limit = max_mib * 1024 * 1024
    if total > limit:
        return fail(f"size {total} exceeds {int(limit)}")
    print(f"package-audit: bytes={total} limit={int(limit)}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--max-mib", required=True, type=float)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return audit(Path(args.root), args.max_mib)


if __name__ == "__main__":
    raise SystemExit(main())
