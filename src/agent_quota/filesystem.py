"""Descriptor-anchored filesystem helpers for private application roots."""

from __future__ import annotations

import os
import stat
from pathlib import Path


def open_directory_nofollow(
    path: Path,
    *,
    require_owner: bool = False,
    require_mode: int | None = None,
) -> int:
    if not path.is_absolute():
        raise ValueError("directory path must be absolute")
    parts = path.parts
    if not parts or parts[0] != "/" or any(part in {"", ".", ".."} for part in parts[1:]):
        raise ValueError("invalid directory path")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor = os.open("/", flags)
    try:
        for part in parts[1:]:
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("path is not a directory")
        if require_owner and metadata.st_uid != os.getuid():
            raise ValueError("directory owner mismatch")
        if require_mode is not None and stat.S_IMODE(metadata.st_mode) != require_mode:
            raise ValueError("directory mode mismatch")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def read_regular_at(directory: int, name: str) -> tuple[bytes, os.stat_result]:
    descriptor = os.open(
        name,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        dir_fd=directory,
    )
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_nlink != 1
        ):
            raise ValueError("private file identity mismatch")
        chunks = []
        while chunk := os.read(descriptor, 65_536):
            chunks.append(chunk)
        return b"".join(chunks), metadata
    finally:
        os.close(descriptor)


def same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        stat.S_IFMT(left.st_mode),
    ) == (
        right.st_dev,
        right.st_ino,
        stat.S_IFMT(right.st_mode),
    )
