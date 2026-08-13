"""Fail closed on incomplete or non-relocatable macOS application bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import stat
import subprocess
from pathlib import Path, PurePosixPath

ALLOWED_DYLIB_PREFIXES = (
    "/System/Library/",
    "/usr/lib/",
    "@executable_path/",
    "@loader_path/",
    "@rpath/",
)
REQUIRED_RESOURCES = (
    "native-helper/AgentQuotaNative.app/Contents/MacOS/AgentQuotaNative",
    "sidecar/agent-quota-sidecar",
)
FORBIDDEN_RUNTIME_STATE_NAMES = {
    ".agent-quota-host-instance.lock",
    "Cookies",
    "Cookies-journal",
    "Login Data",
    "Web Data",
    "agent-quota.sqlite",
    "agent-quota.sqlite-shm",
    "agent-quota.sqlite-wal",
    "native-accounts-v1.json",
}
FORBIDDEN_RUNTIME_STATE_DIRECTORIES = {
    "Application Support",
    "Keychains",
    "Local Storage",
    "Session Storage",
}
MAXIMUM_DEPLOYMENT_TARGET = (13, 0, 0)
REQUIRED_MINIMUM_SYSTEM_VERSION = "13.0"
FORBIDDEN_BUILD_PATH_FRAGMENTS = (
    b"/Users/",
    b"/private/var/folders/",
    b"/private/var/tmp/",
)


def output(*command: str) -> str:
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_resource_manifest(resources: Path, errors: list[str]) -> tuple[str, int]:
    manifest_path = resources / "resource-manifest.json"
    try:
        raw = manifest_path.read_bytes()
        manifest = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        errors.append("resource manifest is unreadable")
        return "", 0
    digest = hashlib.sha256(raw).hexdigest()
    if (
        set(manifest) != {"artifact_class", "entries", "schema"}
        or manifest["artifact_class"] != "local unsigned development package"
        or manifest["schema"] != "agent-quota-resource-manifest-v1"
        or not isinstance(manifest["entries"], list)
    ):
        errors.append("resource manifest contract mismatch")
        return digest, 0
    expected: set[str] = set()
    for entry in manifest["entries"]:
        if not isinstance(entry, dict) or set(entry) != {"bytes", "mode", "path", "sha256"}:
            errors.append("resource manifest entry contract mismatch")
            continue
        relative = entry["path"]
        pure = PurePosixPath(relative) if isinstance(relative, str) else PurePosixPath(".")
        if (
            not isinstance(relative, str)
            or pure.is_absolute()
            or not pure.parts
            or any(part in {"", ".", ".."} for part in pure.parts)
            or relative in expected
        ):
            errors.append("unsafe or duplicate resource manifest path")
            continue
        expected.add(relative)
        path = resources / relative
        try:
            metadata = path.lstat()
        except OSError:
            errors.append(f"missing manifest resource: {relative}")
            continue
        mode = stat.S_IMODE(metadata.st_mode)
        if (
            path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid not in {0, os.geteuid()}
            or mode & 0o022
            or metadata.st_size != entry["bytes"]
            or mode != entry["mode"]
            or sha256(path) != entry["sha256"]
        ):
            errors.append(f"resource metadata/digest mismatch: {relative}")
    actual = {
        path.relative_to(resources).as_posix()
        for parent in (resources / "native-helper", resources / "sidecar")
        for path in parent.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    for parent in (resources / "native-helper", resources / "sidecar"):
        for path in parent.rglob("*"):
            if path.is_symlink() or not (path.is_file() or path.is_dir()):
                errors.append(f"unsafe resource node: {path.relative_to(resources).as_posix()}")
    if actual != expected:
        errors.append("resource file closure mismatch")
    if not set(REQUIRED_RESOURCES).issubset(expected):
        errors.append("required executable missing from resource manifest")
    return digest, len(expected)


def mach_o_files(app: Path) -> list[Path]:
    results: list[Path] = []
    for path in sorted(app.rglob("*")):
        if path.is_file() and not path.is_symlink():
            description = output("/usr/bin/file", "-b", str(path))
            if "Mach-O" in description:
                results.append(path)
    return results


def dylibs(path: Path) -> list[str]:
    lines = output("/usr/bin/otool", "-L", str(path)).splitlines()[1:]
    return [line.strip().split(" (", 1)[0] for line in lines if line.strip()]


def deployment_targets(path: Path) -> list[str]:
    details = output("/usr/bin/xcrun", "vtool", "-show-build", str(path))
    return re.findall(r"^\s+minos (\d+(?:\.\d+){1,2})$", details, re.MULTILINE)


def deployment_target_supported(value: str) -> bool:
    parts = tuple(int(part) for part in value.split("."))
    normalized = (*parts, 0, 0)[:3]
    return normalized <= MAXIMUM_DEPLOYMENT_TARGET


def contains_local_build_path(path: Path) -> bool:
    data = path.read_bytes()
    return any(fragment in data for fragment in FORBIDDEN_BUILD_PATH_FRAGMENTS)


def is_runtime_state_path(relative: PurePosixPath) -> bool:
    return relative.name in FORBIDDEN_RUNTIME_STATE_NAMES or any(
        part in FORBIDDEN_RUNTIME_STATE_DIRECTORIES for part in relative.parts
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    app = args.app.resolve(strict=True)
    contents = app / "Contents"
    with (contents / "Info.plist").open("rb") as stream:
        plist = plistlib.load(stream)
    executable = contents / "MacOS" / str(plist["CFBundleExecutable"])
    resources = contents / "Resources"
    errors: list[str] = []
    minimum_system_version = plist.get("LSMinimumSystemVersion")
    if minimum_system_version != REQUIRED_MINIMUM_SYSTEM_VERSION:
        errors.append(
            "LSMinimumSystemVersion must be "
            f"{REQUIRED_MINIMUM_SYSTEM_VERSION}: {minimum_system_version!r}"
        )
    manifest_digest, manifest_entries = verify_resource_manifest(resources, errors)
    runtime_state_files = sorted(
        path.relative_to(app).as_posix()
        for path in app.rglob("*")
        if path.is_file() and is_runtime_state_path(PurePosixPath(path.relative_to(app).as_posix()))
    )
    if runtime_state_files:
        errors.append("packaged runtime/account state is forbidden")

    for path in (executable, *(resources / name for name in REQUIRED_RESOURCES)):
        metadata = path.lstat() if path.exists() else None
        if (
            metadata is None
            or path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) & 0o100 == 0
            or stat.S_IMODE(metadata.st_mode) & 0o022 != 0
            or metadata.st_uid not in {0, os.geteuid()}
        ):
            errors.append(f"unsafe executable: {path.relative_to(app)}")

    for path in app.rglob("*"):
        metadata = path.lstat()
        if stat.S_IMODE(metadata.st_mode) & 0o022:
            errors.append(f"group/world writable bundle path: {path.relative_to(app)}")
        if path.is_symlink():
            resolved = path.resolve()
            if app not in resolved.parents:
                errors.append(f"escaping symlink: {path.relative_to(app)} -> {os.readlink(path)}")

    binaries: list[dict[str, object]] = []
    for path in mach_o_files(app):
        architecture = output("/usr/bin/lipo", "-archs", str(path)).strip().split()
        targets = deployment_targets(path)
        dependencies = dylibs(path)
        unexpected = [
            dependency
            for dependency in dependencies
            if not dependency.startswith(ALLOWED_DYLIB_PREFIXES)
        ]
        if architecture != ["arm64"]:
            errors.append(f"architecture must be arm64 only: {path.relative_to(app)}")
        if contains_local_build_path(path):
            errors.append(f"local build path embedded: {path.relative_to(app)}")
        if len(targets) != 1 or not deployment_target_supported(targets[0]):
            errors.append(
                f"unsupported deployment target: {path.relative_to(app)}: "
                f"{', '.join(targets) or 'missing'}"
            )
        if unexpected:
            errors.append(f"unexpected dylib: {path.relative_to(app)}: {', '.join(unexpected)}")
        binaries.append(
            {
                "path": path.relative_to(app).as_posix(),
                "architecture": architecture,
                "deployment_target": targets[0] if len(targets) == 1 else None,
                "dependencies": dependencies,
            }
        )

    signature = subprocess.run(
        ["/usr/bin/codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)],
        capture_output=True,
        text=True,
    )
    signature_details = subprocess.run(
        ["/usr/bin/codesign", "-dv", "--verbose=4", str(app)],
        capture_output=True,
        text=True,
        check=False,
    ).stderr.strip()
    binary_inventory = json.dumps(binaries, separators=(",", ":"), sort_keys=True).encode()
    quarantine = subprocess.run(
        ["/usr/bin/xattr", "-p", "com.apple.quarantine", str(app)],
        capture_output=True,
        text=True,
    )
    report = {
        "artifact_class": "local unsigned development package",
        "architecture": "arm64",
        "bundle_id": plist.get("CFBundleIdentifier"),
        "binaries": binaries,
        "codesign_verify_exit": signature.returncode,
        "codesign_verify_stderr": signature.stderr.strip(),
        "codesign_details": signature_details.splitlines(),
        "errors": errors,
        "macho_inventory_sha256": hashlib.sha256(binary_inventory).hexdigest(),
        "notarized": False,
        "quarantine_attribute": (
            quarantine.stdout.strip() if quarantine.returncode == 0 else "absent"
        ),
        "resource_manifest_entries": manifest_entries,
        "resource_manifest_sha256": manifest_digest,
        "runtime_state_files": runtime_state_files,
        "status": "pass" if not errors and signature.returncode == 0 else "fail",
    }
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if report["status"] != "pass":
        raise SystemExit("bundle audit failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
