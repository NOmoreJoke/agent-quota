"""Durably publish one staged artifact directory without replacing a prior build."""

from __future__ import annotations

import argparse
import ctypes
import errno
import os
import stat
import sys
from pathlib import Path

RENAME_EXCL = 0x00000004
RENAME_NOREPLACE = 1


class PublicationOutcomeUnknown(OSError):
    """The rename succeeded but parent-directory durability is unknown."""


def _rename_noreplace(parent: int, source: str, target: str) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source)
    target_bytes = os.fsencode(target)
    if sys.platform == "darwin":
        result = libc.renameatx_np(
            parent,
            source_bytes,
            parent,
            target_bytes,
            RENAME_EXCL,
        )
    elif hasattr(libc, "renameat2"):
        result = libc.renameat2(
            parent,
            source_bytes,
            parent,
            target_bytes,
            RENAME_NOREPLACE,
        )
    else:
        raise OSError(errno.ENOTSUP, "no atomic no-replace rename primitive")
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), target)


def _open_directory_nofollow(path: Path) -> int:
    if not path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts[1:]):
        raise ValueError("invalid publication parent")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor = os.open("/", flags)
    try:
        for part in path.parts[1:]:
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
            metadata = os.fstat(descriptor)
            if metadata.st_uid not in {0, os.geteuid()} or stat.S_IMODE(metadata.st_mode) & 0o022:
                raise ValueError("unsafe publication parent ancestry")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _fsync_tree(parent: int, root: str) -> None:
    for _current, names, files, directory in os.fwalk(
        root,
        topdown=False,
        follow_symlinks=False,
        dir_fd=parent,
    ):
        for name in files:
            metadata = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode):
                raise ValueError(f"staged artifact contains symlink: {name}")
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) & 0o022
            ):
                raise ValueError(f"staged artifact contains unsafe file: {name}")
            descriptor = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
                dir_fd=directory,
            )
            try:
                opened = os.fstat(descriptor)
                if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                    raise ValueError(f"staged artifact file changed during fsync: {name}")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        for name in names:
            metadata = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) & 0o022
            ):
                raise ValueError(f"staged artifact contains symlink or unsafe directory: {name}")
        os.fsync(directory)


def _fsync_parent(parent: int) -> None:
    os.fsync(parent)


def publish(source: Path, target: Path) -> None:
    if not source.is_absolute() or not target.is_absolute() or source.parent != target.parent:
        raise ValueError("artifact stage and target must share one absolute parent")
    parent = _open_directory_nofollow(source.parent)
    try:
        parent_metadata = os.fstat(parent)
        metadata = os.stat(source.name, dir_fd=parent, follow_symlinks=False)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            raise ValueError("artifact stage must be a private real directory")
        try:
            os.stat(target.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError(errno.EEXIST, "artifact target already exists", target)
        if metadata.st_dev != parent_metadata.st_dev:
            raise ValueError("artifact stage must share the target filesystem")
        _fsync_tree(parent, source.name)
        current = os.stat(source.name, dir_fd=parent, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise ValueError("artifact stage changed before publication")
        _rename_noreplace(parent, source.name, target.name)
        try:
            _fsync_parent(parent)
            current_parent = _open_directory_nofollow(source.parent)
            try:
                rebound = os.fstat(current_parent)
            finally:
                os.close(current_parent)
            if (rebound.st_dev, rebound.st_ino) != (
                parent_metadata.st_dev,
                parent_metadata.st_ino,
            ):
                raise OSError(errno.ESTALE, "publication parent changed")
        except (OSError, ValueError) as error:
            error_number = error.errno if isinstance(error, OSError) else errno.ESTALE
            raise PublicationOutcomeUnknown(
                error_number,
                f"publication_outcome_unknown: inspect {target} before retrying",
                target,
            ) from error
    finally:
        os.close(parent)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    publish(args.stage, args.target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
