"""Typed purge planning; renderer receives no path or commit token."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from agent_quota.filesystem import open_directory_nofollow, same_identity


@dataclass(frozen=True)
class PurgeEntry:
    kind: str
    count: int


@dataclass(frozen=True)
class PurgeBinding:
    name: str
    device: int
    inode: int
    mode: int
    size: int
    links: int


@dataclass(frozen=True)
class PurgePlan:
    generation: int
    entries: tuple[PurgeEntry, ...]
    bindings: tuple[PurgeBinding, ...]
    digest: str

    def renderer_projection(self) -> dict[str, object]:
        return {
            "generation": self.generation,
            "entries": [{"kind": entry.kind, "count": entry.count} for entry in self.entries],
            "status": "confirmation-required",
        }


def plan_purge(data_root: Path, generation: int) -> PurgePlan:
    descriptor = _open_root(data_root)
    try:
        return _plan_from_descriptor(descriptor, generation)
    finally:
        os.close(descriptor)


def _plan_from_descriptor(descriptor: int, generation: int) -> PurgePlan:
    categories = {"database": 0, "database-sidecar": 0, "config": 0, "cache": 0, "unknown": 0}
    bindings = []
    for name in sorted(os.listdir(descriptor), key=lambda value: value.encode()):
        metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        bindings.append(
            PurgeBinding(
                name,
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_mode,
                metadata.st_size,
                metadata.st_nlink,
            )
        )
        if stat.S_ISLNK(metadata.st_mode):
            categories["unknown"] += 1
        elif name.endswith((".sqlite", ".db")) and stat.S_ISREG(metadata.st_mode):
            categories["database"] += 1
        elif name.endswith(("-wal", "-shm")) and stat.S_ISREG(metadata.st_mode):
            categories["database-sidecar"] += 1
        elif name.endswith(".toml") and stat.S_ISREG(metadata.st_mode):
            categories["config"] += 1
        elif name == "cache" and stat.S_ISDIR(metadata.st_mode):
            categories["cache"] += 1
        else:
            categories["unknown"] += 1
    entries = tuple(PurgeEntry(kind, count) for kind, count in categories.items() if count)
    payload = {
        "generation": generation,
        "entries": [{"kind": item.kind, "count": item.count} for item in entries],
        "bindings": [
            {
                "name": item.name,
                "device": item.device,
                "inode": item.inode,
                "mode": item.mode,
                "size": item.size,
                "links": item.links,
            }
            for item in bindings
        ],
    }
    digest = hashlib.sha256(
        b"agent-quota:purge-plan:v1\0"
        + json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return PurgePlan(generation, entries, tuple(bindings), digest)


def commit_purge(
    data_root: Path,
    plan: PurgePlan,
    *,
    expected_digest: str,
    expected_generation: int,
) -> None:
    if plan.digest != expected_digest or plan.generation != expected_generation:
        raise ValueError("purge plan drift")
    descriptor = _open_root(data_root)
    try:
        if _plan_from_descriptor(descriptor, expected_generation) != plan:
            raise ValueError("purge contents drift")
        if any(entry.kind == "unknown" for entry in plan.entries):
            raise ValueError("purge root contains unknown entries")
        bindings = {binding.name: binding for binding in plan.bindings}
        for name in sorted(os.listdir(descriptor), key=lambda value: value.encode()):
            binding = bindings[name]
            metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISREG(metadata.st_mode):
                file_descriptor = os.open(
                    name,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
                    dir_fd=descriptor,
                )
                try:
                    pinned = os.fstat(file_descriptor)
                    if not same_identity(metadata, pinned) or (
                        pinned.st_dev,
                        pinned.st_ino,
                        pinned.st_mode,
                        pinned.st_size,
                        pinned.st_nlink,
                    ) != (
                        binding.device,
                        binding.inode,
                        binding.mode,
                        binding.size,
                        binding.links,
                    ):
                        raise ValueError("purge file identity drift")
                finally:
                    os.close(file_descriptor)
                current = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                if not same_identity(pinned, current):
                    raise ValueError("purge file changed before unlink")
                if current.st_nlink != 1:
                    raise ValueError("purge file has unexpected hard links")
                os.unlink(name, dir_fd=descriptor)
            elif name == "cache" and stat.S_ISDIR(metadata.st_mode):
                child = os.open(
                    name,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=descriptor,
                )
                try:
                    pinned = os.fstat(child)
                    if not same_identity(metadata, pinned) or (
                        pinned.st_dev,
                        pinned.st_ino,
                        pinned.st_mode,
                        pinned.st_size,
                        pinned.st_nlink,
                    ) != (
                        binding.device,
                        binding.inode,
                        binding.mode,
                        binding.size,
                        binding.links,
                    ):
                        raise ValueError("purge cache identity drift")
                    if os.listdir(child):
                        raise ValueError("non-empty cache directory requires fenced manifest")
                finally:
                    os.close(child)
                current = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                if not same_identity(pinned, current):
                    raise ValueError("purge cache changed before removal")
                os.rmdir(name, dir_fd=descriptor)
            else:
                raise ValueError("purge entry changed after planning")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _validate_root(path: Path) -> None:
    absolute = path.absolute()
    if (
        not path.is_absolute()
        or path.is_symlink()
        or absolute in {Path("/"), Path.home()}
        or len(absolute.parts) < 4
    ):
        raise ValueError("unsafe purge root")
    metadata = os.lstat(absolute)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise ValueError("purge root ownership or mode mismatch")


def _open_root(path: Path) -> int:
    _validate_root(path)
    return open_directory_nofollow(
        path,
        require_owner=True,
        require_mode=0o700,
    )
