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


def verify_resource_manifest(resources: Path, errors: list[str]) -> tuple[str, set[str]]:
    manifest_path = resources / "resource-manifest.json"
    try:
        raw = manifest_path.read_bytes()
        manifest = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        errors.append("resource manifest is unreadable")
        return "", set()
    digest = hashlib.sha256(raw).hexdigest()
    if (
        set(manifest) != {"artifact_class", "entries", "schema"}
        or manifest["artifact_class"] != "local unsigned development package"
        or manifest["schema"] != "agent-quota-resource-manifest-v1"
        or not isinstance(manifest["entries"], list)
    ):
        errors.append("resource manifest contract mismatch")
        return digest, set()
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
    return digest, expected


def mach_o_files(app: Path) -> list[Path]:
    results: list[Path] = []
    for path in sorted(app.rglob("*")):
        if path.is_file() and not path.is_symlink():
            description = output("/usr/bin/file", "-b", str(path))
            if "Mach-O" in description:
                results.append(path)
    return results


DYLIB_LOAD_COMMANDS = {
    "LC_LAZY_LOAD_DYLIB",
    "LC_LOAD_DYLIB",
    "LC_LOAD_UPWARD_DYLIB",
    "LC_LOAD_WEAK_DYLIB",
    "LC_REEXPORT_DYLIB",
}


def parse_macho_linkage(details: str) -> tuple[list[str], list[str], list[str]]:
    dependencies: list[str] = []
    rpath_entries: list[str] = []
    linkage_errors: list[str] = []
    dynamic_linkers = 0
    blocks = re.split(r"^Load command \d+\s*$", details, flags=re.MULTILINE)[1:]
    for block in blocks:
        command_match = re.search(r"^\s*cmd (LC_[A-Z0-9_]+)\s*$", block, re.MULTILINE)
        if command_match is None:
            if block.strip():
                linkage_errors.append("malformed load command")
            continue
        command = command_match.group(1)
        if command == "LC_LOAD_DYLINKER":
            dynamic_linkers += 1
            name_match = re.search(
                r"^\s*name (.+?) \(offset \d+\)\s*$",
                block,
                re.MULTILINE,
            )
            if dynamic_linkers != 1 or name_match is None or name_match.group(1) != "/usr/lib/dyld":
                linkage_errors.append("unsafe LC_LOAD_DYLINKER")
            continue
        if command == "LC_DYLD_ENVIRONMENT" or command.startswith("LC_SUB_"):
            linkage_errors.append(f"forbidden {command}")
            continue
        if command == "LC_RPATH":
            path_match = re.search(r"^\s*path (.+?) \(offset \d+\)\s*$", block, re.MULTILINE)
            if path_match is None:
                linkage_errors.append("malformed LC_RPATH")
            else:
                rpath_entries.append(path_match.group(1))
            continue
        if "DYLIB" not in command or command == "LC_ID_DYLIB":
            if "DYLINKER" in command:
                linkage_errors.append(f"unknown {command}")
            continue
        if command not in DYLIB_LOAD_COMMANDS:
            linkage_errors.append(command)
            continue
        name_match = re.search(r"^\s*name (.+?) \(offset \d+\)\s*$", block, re.MULTILINE)
        if name_match is None:
            linkage_errors.append(f"malformed {command}")
        else:
            dependencies.append(name_match.group(1))
    return dependencies, rpath_entries, linkage_errors


def macho_linkage(path: Path) -> tuple[list[str], list[str], list[str]]:
    return parse_macho_linkage(output("/usr/bin/otool", "-l", str(path)))


def resolve_rpath_root(
    *,
    entry: str,
    image: Path,
    executable: Path,
    app: Path,
) -> tuple[Path | None, str | None]:
    if entry == "@loader_path":
        candidate = image.parent
    elif entry.startswith("@loader_path/"):
        candidate = image.parent / entry.removeprefix("@loader_path/")
    elif entry == "@executable_path":
        candidate = executable.parent
    elif entry.startswith("@executable_path/"):
        candidate = executable.parent / entry.removeprefix("@executable_path/")
    else:
        return None, f"unsafe LC_RPATH: {entry}"
    lexical = Path(os.path.normpath(candidate))
    if lexical != app and app not in lexical.parents:
        return None, f"escaping LC_RPATH: {entry}"
    ancestry = [app]
    current = app
    for part in lexical.relative_to(app).parts:
        current /= part
        ancestry.append(current)
    for current in ancestry:
        try:
            node = current.lstat()
        except OSError:
            return None, f"unresolved LC_RPATH: {entry}"
        if (
            current.is_symlink()
            or not stat.S_ISDIR(node.st_mode)
            or node.st_uid not in {0, os.geteuid()}
            or stat.S_IMODE(node.st_mode) & 0o022
        ):
            return None, f"unsafe LC_RPATH ancestry: {entry}"
    try:
        resolved = lexical.resolve(strict=True)
        metadata = resolved.lstat()
    except OSError:
        return None, f"unresolved LC_RPATH: {entry}"
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid not in {0, os.geteuid()}
        or stat.S_IMODE(metadata.st_mode) & 0o022
        or (resolved != app and app not in resolved.parents)
    ):
        return None, f"unsafe LC_RPATH target: {entry}"
    if resolved != lexical:
        return None, f"unsafe LC_RPATH identity: {entry}"
    return resolved, None


def resolve_rpath_dependency(
    *,
    dependency: str,
    roots: set[Path],
    app: Path,
    resources: Path,
    manifest: set[str],
) -> tuple[Path | None, str | None]:
    suffix = PurePosixPath(dependency.removeprefix("@rpath/"))
    if (
        not dependency.startswith("@rpath/")
        or suffix.is_absolute()
        or not suffix.parts
        or any(part in {"", ".", ".."} for part in suffix.parts)
    ):
        return None, f"unsafe @rpath dependency: {dependency}"
    candidates: set[Path] = set()
    for root in roots:
        candidate = root.joinpath(*suffix.parts)
        try:
            metadata = candidate.lstat()
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if (
            candidate.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid not in {0, os.geteuid()}
            or stat.S_IMODE(metadata.st_mode) & 0o022
            or (resolved != app and app not in resolved.parents)
        ):
            return None, f"unsafe @rpath target: {dependency}"
        if resources != resolved and resources not in resolved.parents:
            return None, f"unmanifested @rpath target: {resolved.relative_to(app).as_posix()}"
        relative = resolved.relative_to(resources).as_posix()
        if relative not in manifest:
            return None, f"unmanifested @rpath target: {relative}"
        candidates.add(resolved)
    if len(candidates) != 1:
        return None, f"@rpath target count must be exactly one: {dependency}"
    return next(iter(candidates)), None


def resolve_scoped_rpath_dependency(
    *,
    dependency: str,
    image_roots: set[Path],
    all_roots: set[Path],
    app: Path,
    resources: Path,
    manifest: set[str],
) -> tuple[Path | None, str | None]:
    resolved, error = resolve_rpath_dependency(
        dependency=dependency,
        roots=image_roots,
        app=app,
        resources=resources,
        manifest=manifest,
    )
    if error is not None:
        return None, f"image-local {error}"
    shadow_resolved, shadow_error = resolve_rpath_dependency(
        dependency=dependency,
        roots=all_roots,
        app=app,
        resources=resources,
        manifest=manifest,
    )
    if shadow_error is not None or shadow_resolved != resolved:
        return None, f"global shadow check failed: {shadow_error or dependency}"
    return resolved, None


def resolve_bundle_dependency(
    *,
    dependency: str,
    image: Path,
    executable: Path,
    app: Path,
    resources: Path,
    manifest: set[str],
) -> tuple[Path | None, str | None]:
    if dependency.startswith("@loader_path/"):
        base = image.parent
        suffix_value = dependency.removeprefix("@loader_path/")
    elif dependency.startswith("@executable_path/"):
        base = executable.parent
        suffix_value = dependency.removeprefix("@executable_path/")
    else:
        return None, f"unsupported relocatable dependency: {dependency}"
    suffix = PurePosixPath(suffix_value)
    if (
        suffix.is_absolute()
        or not suffix.parts
        or any(part in {"", ".", ".."} for part in suffix.parts)
    ):
        return None, f"unsafe relocatable dependency: {dependency}"
    candidate = base.joinpath(*suffix.parts)
    try:
        metadata = candidate.lstat()
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None, f"unresolved relocatable dependency: {dependency}"
    if (
        candidate.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid not in {0, os.geteuid()}
        or stat.S_IMODE(metadata.st_mode) & 0o022
        or (resolved != app and app not in resolved.parents)
    ):
        return None, f"unsafe relocatable target: {dependency}"
    if resources != resolved and resources not in resolved.parents:
        return None, f"unmanifested relocatable target: {resolved.relative_to(app).as_posix()}"
    relative = resolved.relative_to(resources).as_posix()
    if relative not in manifest:
        return None, f"unmanifested relocatable target: {relative}"
    return resolved, None


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


def validate_bundle_nodes(app: Path, errors: list[str]) -> None:
    for path in (app, *app.rglob("*")):
        metadata = path.lstat()
        relative = Path(".") if path == app else path.relative_to(app)
        if path == app and not stat.S_ISDIR(metadata.st_mode):
            errors.append("bundle root must be a directory")
        if metadata.st_uid not in {0, os.geteuid()}:
            errors.append(f"unsafe bundle path owner: {relative}")
        if stat.S_IMODE(metadata.st_mode) & 0o022:
            errors.append(f"group/world writable bundle path: {relative}")
        if path.is_symlink():
            errors.append(f"bundle symlink is forbidden: {relative}")


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
    manifest_digest, manifest_paths = verify_resource_manifest(resources, errors)
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

    validate_bundle_nodes(app, errors)

    macho_paths = mach_o_files(app)
    linkage = {path: macho_linkage(path) for path in macho_paths}
    global_rpath_roots: set[Path] = set()
    rpath_roots_by_image: dict[Path, set[Path]] = {path: set() for path in macho_paths}
    for path, (_dependencies, image_rpaths, _linkage_errors) in linkage.items():
        for entry in image_rpaths:
            root, rpath_error = resolve_rpath_root(
                entry=entry,
                image=path,
                executable=executable,
                app=app,
            )
            if rpath_error is not None:
                errors.append(f"{path.relative_to(app)}: {rpath_error}")
            if root is not None:
                global_rpath_roots.add(root)
                rpath_roots_by_image[path].add(root)

    binaries: list[dict[str, object]] = []
    for path in macho_paths:
        architecture = output("/usr/bin/lipo", "-archs", str(path)).strip().split()
        targets = deployment_targets(path)
        dependencies, image_rpaths, linkage_errors = linkage[path]
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
        if linkage_errors:
            errors.append(
                f"unsafe Mach-O linkage: {path.relative_to(app)}: " + ", ".join(linkage_errors)
            )
        resolved_bundle_dependencies: dict[str, str] = {}
        for dependency in dependencies:
            if dependency.startswith(("/System/Library/", "/usr/lib/")):
                if os.path.normpath(dependency) != dependency or ".." in dependency.split("/"):
                    errors.append(
                        f"unsafe system dylib path: {path.relative_to(app)}: {dependency}"
                    )
                continue
            if dependency.startswith("@rpath/"):
                resolved, resolution_error = resolve_scoped_rpath_dependency(
                    dependency=dependency,
                    image_roots=rpath_roots_by_image[path],
                    all_roots=global_rpath_roots,
                    app=app,
                    resources=resources,
                    manifest=manifest_paths,
                )
                if resolution_error is not None:
                    errors.append(f"{path.relative_to(app)}: {resolution_error}")
                if resolved is not None:
                    resolved_bundle_dependencies[dependency] = resolved.relative_to(app).as_posix()
                continue
            resolved, resolution_error = resolve_bundle_dependency(
                dependency=dependency,
                image=path,
                executable=executable,
                app=app,
                resources=resources,
                manifest=manifest_paths,
            )
            if resolution_error is not None:
                errors.append(f"{path.relative_to(app)}: {resolution_error}")
            if resolved is not None:
                resolved_bundle_dependencies[dependency] = resolved.relative_to(app).as_posix()
        binaries.append(
            {
                "path": path.relative_to(app).as_posix(),
                "architecture": architecture,
                "deployment_target": targets[0] if len(targets) == 1 else None,
                "dependencies": dependencies,
                "lc_rpaths": image_rpaths,
                "resolved_bundle_dependencies": resolved_bundle_dependencies,
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
        "errors": list(dict.fromkeys(errors)),
        "macho_inventory_sha256": hashlib.sha256(binary_inventory).hexdigest(),
        "notarized": False,
        "quarantine_attribute": (
            quarantine.stdout.strip() if quarantine.returncode == 0 else "absent"
        ),
        "resource_manifest_entries": len(manifest_paths),
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
