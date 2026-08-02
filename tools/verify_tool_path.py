#!/usr/bin/env python3
"""Fail-closed executable ownership, mode, ancestor, and identity verifier."""

from __future__ import annotations

import argparse
import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path


class UnsafeToolPath(ValueError):
    pass


@dataclass(frozen=True)
class ToolIdentity:
    device: int
    inode: int
    size: int
    mtime_ns: int
    uid: int
    mode: int

    def serialize(self) -> str:
        return ":".join(str(value) for value in self.__dict__.values())

    @classmethod
    def parse(cls, value: str) -> ToolIdentity:
        parts = value.split(":")
        if len(parts) != 6 or any(not part.isdigit() for part in parts):
            raise UnsafeToolPath("invalid executable identity")
        return cls(*(int(part) for part in parts))


def inspect_trusted_executable(path: Path) -> tuple[Path, ToolIdentity]:
    if not path.is_absolute() or "|" in str(path) or "\n" in str(path):
        raise UnsafeToolPath("executable path is not canonical")
    absolute = Path(os.path.abspath(path))
    canonical = Path(os.path.realpath(absolute))
    if canonical != absolute or str(canonical).startswith("/private/var/tmp/"):
        raise UnsafeToolPath("symlinked or ephemeral executable path")

    allowed_owners = {0, os.geteuid()}
    current = canonical.parent
    while True:
        metadata = os.lstat(current)
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid not in allowed_owners
            or metadata.st_mode & 0o022
        ):
            raise UnsafeToolPath(f"unsafe executable ancestor: {current}")
        if current == current.parent:
            break
        current = current.parent

    descriptor = os.open(canonical, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(descriptor)
        path_metadata = os.lstat(canonical)
        if (metadata.st_dev, metadata.st_ino) != (
            path_metadata.st_dev,
            path_metadata.st_ino,
        ):
            raise UnsafeToolPath("executable changed during validation")
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid not in allowed_owners
            or metadata.st_mode & 0o022
            or not metadata.st_mode & 0o111
            or metadata.st_nlink != 1
        ):
            raise UnsafeToolPath("unsafe executable metadata")
        identity = ToolIdentity(
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_uid,
            stat.S_IMODE(metadata.st_mode),
        )
    finally:
        os.close(descriptor)
    return canonical, identity


def digest_trusted_tree(root: Path) -> str:
    if not root.is_absolute() or "\n" in str(root):
        raise UnsafeToolPath("toolchain root is not canonical")
    absolute = Path(os.path.abspath(root))
    canonical = Path(os.path.realpath(absolute))
    if canonical != absolute or str(canonical).startswith("/private/var/tmp/"):
        raise UnsafeToolPath("symlinked or ephemeral toolchain root")

    allowed_owners = {0, os.geteuid()}
    digest = hashlib.sha256()
    paths = [
        canonical,
        *sorted(
            canonical.rglob("*"),
            key=lambda item: item.relative_to(canonical).as_posix(),
        ),
    ]
    if not 1 <= len(paths) <= 4096:
        raise UnsafeToolPath("toolchain tree has invalid cardinality")
    for path in paths:
        metadata = os.lstat(path)
        relative = "." if path == canonical else path.relative_to(canonical).as_posix()
        if "\n" in relative or "\0" in relative or metadata.st_uid not in allowed_owners:
            raise UnsafeToolPath("unsafe toolchain entry")
        mode = stat.S_IMODE(metadata.st_mode)
        if mode & 0o022 or stat.S_ISLNK(metadata.st_mode):
            raise UnsafeToolPath("unsafe toolchain entry metadata")
        if stat.S_ISDIR(metadata.st_mode):
            record = f"D\0{relative}\0{mode:o}\0{metadata.st_uid}\0".encode()
        elif stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1:
            file_digest = hashlib.sha256()
            descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
            try:
                opened = os.fstat(descriptor)
                if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
                    metadata.st_dev,
                    metadata.st_ino,
                    metadata.st_size,
                    metadata.st_mtime_ns,
                ):
                    raise UnsafeToolPath("toolchain entry changed during validation")
                while chunk := os.read(descriptor, 1024 * 1024):
                    file_digest.update(chunk)
            finally:
                os.close(descriptor)
            final = os.lstat(path)
            if (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns) != (
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_size,
                metadata.st_mtime_ns,
            ):
                raise UnsafeToolPath("toolchain entry changed during validation")
            record = (
                f"F\0{relative}\0{mode:o}\0{metadata.st_uid}\0{metadata.st_size}\0"
                f"{file_digest.hexdigest()}\0"
            ).encode()
        else:
            raise UnsafeToolPath("unsupported toolchain entry")
        digest.update(record)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", type=Path)
    parser.add_argument("--expect")
    parser.add_argument("--tree", type=Path)
    arguments = parser.parse_args()
    if arguments.tree is not None:
        if arguments.path is not None or arguments.expect is not None:
            raise UnsafeToolPath("tree validation arguments are invalid")
        print(digest_trusted_tree(arguments.tree))
        return 0
    if arguments.path is None:
        raise UnsafeToolPath("executable path is required")
    canonical, identity = inspect_trusted_executable(arguments.path)
    if arguments.expect is not None and identity != ToolIdentity.parse(arguments.expect):
        raise UnsafeToolPath("executable identity changed after validation")
    print(f"{canonical}|{identity.serialize()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
