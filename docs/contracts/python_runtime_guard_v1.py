"""Local audit-evidence check for the pinned CPython implementation.

This module deliberately does not authenticate who launched the process.  A
production launch claim requires a repository-external attestation rooted in
an already trusted launcher.  The checks here only describe the local process
that is currently running.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import platform
import stat
import subprocess
import sys
import sysconfig
from pathlib import Path


EXPECTED = {
    "implementation": "CPython",
    "version": "3.11.15",
    "abi": "cpython-311-darwin",
    "platform": "macosx-26.0-arm64",
    "system": "Darwin",
    "system_release": "25.5.0",
    "os_build": "25F84",
    "machine": "arm64",
    "resolved_executable": "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/bin/python3.11",
    "executable_sha256": "50de159a94723fa71090030ac642b101e27f8d29488ec4bdae91edfa1e86dbbd",
    "framework_binary": "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/Python",
    "framework_sha256": "c12f5240b4501ea1adb52db3568c3c19f5034f1f8c665ec0c3fe2ea401b2902d",
    "stdlib_root": "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11",
    "stdlib_tree_count": 2487,
    "stdlib_tree_sha256": "7cd4b339d6976a04f23d9894c1afdb172df8359441fef18a271e3e4f467c22ab",
}

EXTERNAL_LAUNCH_TOOLS = {
    "/bin/ps": "472992c470606d28f577590decfecd7f4a20f832fd92c671bebc6d44790b5d02",
    "/bin/pwd": "ff2c9704307a064566ae9835ff0becf3a765481580c0abe28c8654e2a3045639",
    "/bin/rm": "0e7aa0987cecc8d8ca629e1c61857321e8e281a6c1d0711b21163a15e454dc9d",
    "/bin/sh": "ad5c194b05f83bc5e793c1cd67b148a4b680467b5a5730ab1a31fe4e6460ee9f",
    "/bin/sleep": "a2be9ba33f4fbf10a4f2702cd9b687ac98274ad28de509109ee86f2f4b0e2beb",
    "/usr/bin/awk": "3693175058d0be720f941a8e9c645756f7d38848f3457abd938d8e27ba35f8ab",
    "/usr/bin/env": "6e506aec3c0cff703ac1e66cedc6f1945354ad41339a38db4425c7c88227128f",
    "/usr/bin/find": "cbab4ddd20b57c5090196f79b1c969e8a17fc48b4bb8e4a18765d0bbc714481e",
    "/usr/bin/grep": "569588bf23c56895f046b63b029285217e442d46bec1b18498b58fefb50d8f1f",
    "/usr/bin/mktemp": "7bb3299fdb41f16ea5d9f7748cb5cb654b93208e0a1d1d78360145dcbbfb21fe",
    "/usr/bin/otool": "179301dcb41ea78accc3fa0048a7e6f6710d891945a751a34addd622020c1818",
    "/usr/bin/readlink": "934656def5cfb8e85b2e4d983bb59ba97479cec49b63b4ea2fa42d067c569242",
    "/usr/bin/shasum": "0812595f981a26f813d98dc380af14d4af427626c9339eda29eb849ae13de1e3",
    "/usr/bin/sort": "e595f29543691f7355d16035f71992512c6a23804f9447b73e6d484b7887d731",
    "/usr/bin/stat": "934656def5cfb8e85b2e4d983bb59ba97479cec49b63b4ea2fa42d067c569242",
    "/usr/bin/sw_vers": "f4704a35bc196e6dd101a7de40f9e9ce51dd17bdba7ef29ce465a00d123f2ec5",
    "/usr/bin/tr": "1ddc659c4c983056863cad854384c35d78d004dd2c53cc63ea3b3b380e76233a",
    "/usr/bin/uname": "c189136263d277786f29a16eb3137de7bcf4512d2282d0036f440022f325bfc4",
    "/usr/bin/wc": "48afbe8af0942865f6ee7b5bfface7d9f3ec2b6ab71e81deb3ae47b8644b804f",
}

# Every non-Apple image observed in any registered Python evidence entry is
# individually pinned.  System images are covered by the exact macOS build
# trust boundary and must resolve below /System or /usr/lib.
EXPECTED_NON_SYSTEM_IMAGES = {
    "/opt/homebrew/Cellar/openssl@3/3.6.2/lib/libcrypto.3.dylib": "ef2239cec921003b54b61968f00489271e2a2805d7d1b4e69d632423f38efe1e",
    "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/Python": "c12f5240b4501ea1adb52db3568c3c19f5034f1f8c665ec0c3fe2ea401b2902d",
    "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/Resources/Python.app/Contents/MacOS/Python": "e17826d56c53bce1083f70b4cdb68ea29105fdc84c1c345746523f2af0b8287d",
    "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/lib-dynload/_bisect.cpython-311-darwin.so": "b17cc8d594f3355518b61a1a1faf9b4c9eb86b071be3275ee28f2d64acb43196",
    "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/lib-dynload/_blake2.cpython-311-darwin.so": "77235b1a51778aafc8be14b18d8a3b9b75b75a929f64755e740c086e96f84121",
    "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/lib-dynload/_bz2.cpython-311-darwin.so": "470b482dad9723baaae29d4d310107db04c1ef2e76d6b32755761a98c46860fc",
    "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/lib-dynload/_ctypes.cpython-311-darwin.so": "9d85025a92249013d1e0a7d17e6c273f7f53f59fb889a4d2a310660f7f858f71",
    "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/lib-dynload/_hashlib.cpython-311-darwin.so": "cfde53c75126f755139658d8de1beddc4119067214ce023dafc4d9424add95a2",
    "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/lib-dynload/_heapq.cpython-311-darwin.so": "1ad8ac36d73ff4568260b402165f49269a8abd120ead5e1c3f5e69f77bb3693e",
    "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/lib-dynload/_json.cpython-311-darwin.so": "abfe71999367bb543a9f438e6c1f772e220d9f07e4e63a7e7030446dbde9bac9",
    "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/lib-dynload/_lzma.cpython-311-darwin.so": "e3c5b4dc99b3bfae774a4d6e1c4bc91111dcef1b854ba4acb6da7fa71c07adf7",
    "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/lib-dynload/_opcode.cpython-311-darwin.so": "618be25ab7947cbb2ba1d72cdb0898b954b04fa706a1f32bc8295ec8f701cf24",
    "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/lib-dynload/_posixsubprocess.cpython-311-darwin.so": "e2ce6672d7e21120092abddb3fd5e93eda3b8c66beb70eeae25c2a6976797633",
    "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/lib-dynload/_random.cpython-311-darwin.so": "eb17ec468415481579cb02fc41cdafe26427655439ab57963da59ac311625f7c",
    "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/lib-dynload/_sha512.cpython-311-darwin.so": "e685abf22589cdcff31a7515c8c719798fa0c61e63722b8ce8fe55bc9f946bdf",
    "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/lib-dynload/_struct.cpython-311-darwin.so": "00ed50d891d30f3e76a21c98f50c8f481f39f37565bcb21a09c31fd8d0cad5ba",
    "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/lib-dynload/_typing.cpython-311-darwin.so": "9f40385350abddb6381519087cc481d9209205aa1af5f8fbd0e32799b00e4337",
    "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/lib-dynload/binascii.cpython-311-darwin.so": "632b64eddda2e7d29693d764734818349baeb69ace77d7200dae9e7111baeb8c",
    "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/lib-dynload/fcntl.cpython-311-darwin.so": "51439a6cd81672f1d0821594c7d7a9ccfff42a5cafecfbddced31804e107a7a5",
    "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/lib-dynload/math.cpython-311-darwin.so": "e976f1e6f71967212f1c8dafae5e6e636a186cbf933b382b02b153e7e55311b0",
    "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/lib-dynload/select.cpython-311-darwin.so": "c34bebe9b6cab0e54a8ad98424d65daaa46fe09841390bbec284c8dfe0cab232",
    "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/lib-dynload/unicodedata.cpython-311-darwin.so": "9117f2f3b4826b6622928c9ab5138e7515e2ed5d4ce7f95e7b9b7792d32f782d",
    "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/lib-dynload/zlib.cpython-311-darwin.so": "cbeffde53d308e49104a0c0f042fdb8e179e9faeb0f74a140eb1b13c89a30214",
    "/opt/homebrew/Cellar/xz/5.8.3/lib/liblzma.5.dylib": "3d5bfa2f097c31463642b1daab5e662b44368bb4da368f85e412e7f9adcbaa10",
}

REQUIRED_NON_SYSTEM_IMAGES = frozenset({
    EXPECTED["framework_binary"],
    "/opt/homebrew/Cellar/openssl@3/3.6.2/lib/libcrypto.3.dylib",
    "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/Resources/Python.app/Contents/MacOS/Python",
    "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/lib-dynload/_ctypes.cpython-311-darwin.so",
    "/opt/homebrew/Cellar/python@3.11/3.11.15_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/lib-dynload/_hashlib.cpython-311-darwin.so",
})


def _sha(path: Path) -> str:
    handle = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(handle)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeError(f"runtime path is not regular: {path}")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(handle, 65536)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(handle)
        identity = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if identity(before) != identity(after):
            raise RuntimeError(f"runtime path changed during read: {path}")
        return digest.hexdigest()
    finally:
        os.close(handle)


def _canonical_loaded_image_path(raw_path: str) -> tuple[str, bool]:
    """Classify one dyld image without using an installation-prefix allowlist.

    Exact-build Apple images may be absent as standalone files because they can
    come from the dyld shared cache.  Every other image must resolve to a
    canonical, no-symlink, regular file before it can enter the observed set.
    """
    if not os.path.isabs(raw_path) or os.path.normpath(raw_path) != raw_path:
        raise RuntimeError(f"loaded image path is not canonical absolute: {raw_path}")
    resolved = os.path.realpath(raw_path)
    if not os.path.isabs(resolved) or os.path.normpath(resolved) != resolved:
        raise RuntimeError(f"loaded image path cannot canonicalize: {raw_path}")
    is_system = resolved.startswith("/System/") or resolved.startswith("/usr/lib/")
    if is_system:
        return resolved, True
    current = os.path.sep
    try:
        for segment in resolved.split(os.path.sep)[1:]:
            current = os.path.join(current, segment)
            metadata = os.lstat(current)
            if stat.S_ISLNK(metadata.st_mode):
                raise RuntimeError(f"non-system loaded image path contains a symlink: {current}")
        metadata = os.lstat(resolved)
    except OSError as error:
        raise RuntimeError(f"non-system loaded image cannot canonicalize: {raw_path}") from error
    if not stat.S_ISREG(metadata.st_mode) or resolved != raw_path:
        raise RuntimeError(f"non-system loaded image is not a canonical regular file: {raw_path}")
    return resolved, False


def _exact_os_build() -> str:
    completed = subprocess.run(
        ["/usr/bin/sw_vers", "-buildVersion"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
        timeout=10,
        check=False,
    )
    if completed.returncode != 0 or len(completed.stdout.splitlines()) != 1:
        raise RuntimeError("Darwin OS build probe failed")
    return completed.stdout.strip()


def _stdlib_manifest() -> tuple[int, str]:
    root = Path(EXPECTED["stdlib_root"])
    rows: list[str] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().encode("utf-8")):
        rel = path.relative_to(root).as_posix()
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"} or rel.startswith("site-packages/"):
            continue
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            rows.append(f"L\t{rel}\t{os.readlink(path)}\n")
        elif stat.S_ISREG(metadata.st_mode):
            rows.append(f"F\t{rel}\t{_sha(path)}\n")
    raw = "".join(rows).encode("utf-8")
    return len(rows), hashlib.sha256(raw).hexdigest()


def _loaded_non_system_images() -> set[str]:
    process = ctypes.CDLL(None)
    process._dyld_image_count.restype = ctypes.c_uint32
    process._dyld_get_image_name.argtypes = [ctypes.c_uint32]
    process._dyld_get_image_name.restype = ctypes.c_char_p
    images: set[str] = set()
    for index in range(process._dyld_image_count()):
        raw = process._dyld_get_image_name(index)
        if raw is None:
            continue
        path, is_system = _canonical_loaded_image_path(os.fsdecode(raw))
        if not is_system:
            images.add(path)
    return images


def _verify_closed_environment() -> None:
    forbidden = [
        name for name in os.environ
        if name.startswith(("DYLD_", "LD_", "PYTHON"))
        and name not in {"PYTHONHASHSEED", "PYTHONDONTWRITEBYTECODE", "PYTHONUTF8"}
    ]
    if forbidden:
        raise RuntimeError(f"unregistered loader/Python environment: {','.join(sorted(forbidden))}")
    expected = {
        "LANG": "C",
        "LC_ALL": "C",
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1",
    }
    if any(os.environ.get(name) != value for name, value in expected.items()):
        raise RuntimeError("local audit runtime environment is not the closed registered profile")


def verify_runtime(*, require_external_bootstrap: bool) -> dict[str, object]:
    """Verify local bytes; never convert caller-controlled values to proof."""
    if require_external_bootstrap:
        _verify_closed_environment()
    actual = {
        "implementation": platform.python_implementation(),
        "version": platform.python_version(),
        "abi": sysconfig.get_config_var("SOABI"),
        "platform": sysconfig.get_platform(),
        "system": platform.system(),
        "system_release": platform.release(),
        "machine": platform.machine(),
        "resolved_executable": os.path.realpath(sys.executable),
    }
    for key, value in actual.items():
        if value != EXPECTED[key]:
            raise RuntimeError(f"Python runtime identity mismatch: {key}")
    if _exact_os_build() != EXPECTED["os_build"]:
        raise RuntimeError("Darwin OS build trust boundary mismatch")
    if _sha(Path(EXPECTED["resolved_executable"])) != EXPECTED["executable_sha256"]:
        raise RuntimeError("Python executable digest mismatch")
    if _sha(Path(EXPECTED["framework_binary"])) != EXPECTED["framework_sha256"]:
        raise RuntimeError("Python framework digest mismatch")
    count, tree_sha = _stdlib_manifest()
    if count != EXPECTED["stdlib_tree_count"] or tree_sha != EXPECTED["stdlib_tree_sha256"]:
        raise RuntimeError("Python stdlib implementation tree mismatch")
    images = _loaded_non_system_images()
    unknown = images - set(EXPECTED_NON_SYSTEM_IMAGES)
    missing = REQUIRED_NON_SYSTEM_IMAGES - images
    if unknown:
        raise RuntimeError(f"unregistered non-system loaded image: {sorted(unknown)[0]}")
    if missing:
        raise RuntimeError(f"required non-system loaded image missing: {sorted(missing)[0]}")
    for path in sorted(images, key=lambda value: value.encode("utf-8")):
        if _sha(Path(path)) != EXPECTED_NON_SYSTEM_IMAGES[path]:
            raise RuntimeError(f"non-system loaded image digest mismatch: {path}")
    return {
        **actual,
        "stdlib_tree_count": count,
        "stdlib_tree_sha256": tree_sha,
        "loaded_non_system_images": sorted(images, key=lambda value: value.encode("utf-8")),
        "external_launch_attestation": "absent",
        "launch_authority": "local-audit-evidence-only-not-fixed-launch-proof",
    }
