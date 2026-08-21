import os
import runpy
from pathlib import Path

import pytest

deployment_target_supported = runpy.run_path(
    Path(__file__).parents[1] / "tools" / "audit_macos_bundle.py"
)["deployment_target_supported"]
contains_local_build_path = runpy.run_path(
    Path(__file__).parents[1] / "tools" / "audit_macos_bundle.py"
)["contains_local_build_path"]
is_runtime_state_path = runpy.run_path(
    Path(__file__).parents[1] / "tools" / "audit_macos_bundle.py"
)["is_runtime_state_path"]
resolve_bundle_dependency = runpy.run_path(
    Path(__file__).parents[1] / "tools" / "audit_macos_bundle.py"
)["resolve_bundle_dependency"]
resolve_rpath_root = runpy.run_path(Path(__file__).parents[1] / "tools" / "audit_macos_bundle.py")[
    "resolve_rpath_root"
]
resolve_rpath_dependency = runpy.run_path(
    Path(__file__).parents[1] / "tools" / "audit_macos_bundle.py"
)["resolve_rpath_dependency"]
resolve_scoped_rpath_dependency = runpy.run_path(
    Path(__file__).parents[1] / "tools" / "audit_macos_bundle.py"
)["resolve_scoped_rpath_dependency"]
parse_macho_linkage = runpy.run_path(Path(__file__).parents[1] / "tools" / "audit_macos_bundle.py")[
    "parse_macho_linkage"
]
validate_bundle_nodes = runpy.run_path(
    Path(__file__).parents[1] / "tools" / "audit_macos_bundle.py"
)["validate_bundle_nodes"]


def test_deployment_target_accepts_macos_13_and_older() -> None:
    assert deployment_target_supported("11.0")
    assert deployment_target_supported("13.0")


def test_deployment_target_rejects_newer_macos() -> None:
    assert not deployment_target_supported("13.0.1")
    assert not deployment_target_supported("13.1")
    assert not deployment_target_supported("26.0")


def test_runtime_account_state_paths_are_rejected_from_bundle() -> None:
    from pathlib import PurePosixPath

    for relative in (
        "Contents/Resources/native-accounts-v1.json",
        "Contents/Resources/agent-quota.sqlite-wal",
        "Contents/Resources/Application Support/com.agentquota.desktop/state.json",
        "Contents/Resources/Local Storage/leveldb/000001.log",
    ):
        assert is_runtime_state_path(PurePosixPath(relative))
    assert not is_runtime_state_path(
        PurePosixPath("Contents/Resources/_internal/agent_quota/resources/provider_catalog_v1.json")
    )


def test_local_build_paths_are_rejected(tmp_path: Path) -> None:
    binary = tmp_path / "binary"
    binary.write_bytes(b"prefix/Users/example/.cargo/registry/src/suffix")
    assert contains_local_build_path(binary)
    binary.write_bytes(b"/build/home/.cargo/registry/src")
    assert not contains_local_build_path(binary)


def test_macho_parser_never_hides_load_command_equal_to_install_name() -> None:
    details = """
Load command 1
          cmd LC_ID_DYLIB
      cmdsize 64
         name @rpath/libsame.dylib (offset 24)
Load command 2
          cmd LC_LOAD_DYLIB
      cmdsize 64
         name @rpath/libsame.dylib (offset 24)
Load command 3
          cmd LC_RPATH
      cmdsize 40
         path /tmp/shadow (offset 12)
"""
    dependencies, rpath_entries, unknown = parse_macho_linkage(details)
    assert dependencies == ["@rpath/libsame.dylib"]
    assert rpath_entries == ["/tmp/shadow"]
    assert unknown == []


@pytest.mark.parametrize(
    ("block", "expected"),
    [
        (
            """Load command 1
          cmd LC_LOAD_DYLINKER
      cmdsize 32
         name /tmp/evil-dyld (offset 12)
""",
            "unsafe LC_LOAD_DYLINKER",
        ),
        (
            """Load command 1
          cmd LC_DYLD_ENVIRONMENT
      cmdsize 48
         name DYLD_LIBRARY_PATH=/tmp (offset 12)
""",
            "forbidden LC_DYLD_ENVIRONMENT",
        ),
        (
            """Load command 1
      cmdsize 48
         name @rpath/hidden.dylib (offset 12)
""",
            "malformed load command",
        ),
    ],
)
def test_macho_parser_rejects_unsafe_or_malformed_linkage(block: str, expected: str) -> None:
    dependencies, rpath_entries, errors = parse_macho_linkage(block)
    assert dependencies == []
    assert rpath_entries == []
    assert expected in errors


def test_macho_parser_allows_only_canonical_dynamic_linker() -> None:
    details = """Load command 1
          cmd LC_LOAD_DYLINKER
      cmdsize 32
         name /usr/lib/dyld (offset 12)
"""
    assert parse_macho_linkage(details) == ([], [], [])


def test_loader_path_resolves_inside_manifested_bundle_resource(tmp_path: Path) -> None:
    app = tmp_path / "Agent Quota.app"
    executable = app / "Contents/MacOS/Agent Quota"
    image = app / "Contents/Resources/sidecar/agent-quota-sidecar"
    library = app / "Contents/Resources/sidecar/lib/libsafe.dylib"
    for path in (executable, image, library):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"binary")
        path.chmod(0o755)

    resolved, error = resolve_bundle_dependency(
        dependency="@loader_path/lib/libsafe.dylib",
        image=image,
        executable=executable,
        app=app,
        resources=app / "Contents/Resources",
        manifest={"sidecar/lib/libsafe.dylib"},
    )

    assert error is None
    assert resolved == library


def test_loader_path_rejects_escape_unmanifested_and_unsupported_rpath(tmp_path: Path) -> None:
    app = tmp_path / "Agent Quota.app"
    executable = app / "Contents/MacOS/Agent Quota"
    image = app / "Contents/Resources/sidecar/agent-quota-sidecar"
    first = image.parent / "lib/libunsafe.dylib"
    for path in (executable, image, first):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"binary")
        path.chmod(0o755)

    resolved, error = resolve_bundle_dependency(
        dependency="@loader_path/../../../../../../tmp/libunsafe.dylib",
        image=image,
        executable=executable,
        app=app,
        resources=app / "Contents/Resources",
        manifest=set(),
    )
    assert resolved is None
    assert error is not None and "unsafe relocatable dependency" in error

    resolved, error = resolve_bundle_dependency(
        dependency="@loader_path/lib/libunsafe.dylib",
        image=image,
        executable=executable,
        app=app,
        resources=app / "Contents/Resources",
        manifest=set(),
    )
    assert resolved is None
    assert error is not None and "unmanifested relocatable target" in error

    resolved, error = resolve_bundle_dependency(
        dependency="@rpath/libunsafe.dylib",
        image=image,
        executable=executable,
        app=app,
        resources=app / "Contents/Resources",
        manifest={"sidecar/lib/libunsafe.dylib"},
    )
    assert resolved is None
    assert error is not None and "unsupported relocatable dependency" in error


def test_pyinstaller_libssl_and_sqlite_rpaths_resolve_to_manifest(tmp_path: Path) -> None:
    app = tmp_path / "Agent Quota.app"
    executable = app / "Contents/MacOS/Agent Quota"
    internal = app / "Contents/Resources/sidecar/_internal"
    libssl = internal / "libssl.3.dylib"
    libcrypto = internal / "libcrypto.3.dylib"
    sqlite_module = internal / "python3.11/lib-dynload/_sqlite3.cpython-311-darwin.so"
    libsqlite = internal / "libsqlite3.dylib"
    for path in (executable, libssl, libcrypto, sqlite_module, libsqlite):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"binary")
        path.chmod(0o755)
    manifest = {
        path.relative_to(app / "Contents/Resources").as_posix()
        for path in (libssl, libcrypto, sqlite_module, libsqlite)
    }

    ssl_root, error = resolve_rpath_root(
        entry="@loader_path",
        image=libssl,
        executable=executable,
        app=app,
    )
    assert error is None and ssl_root == internal
    sqlite_root, error = resolve_rpath_root(
        entry="@loader_path/../..",
        image=sqlite_module,
        executable=executable,
        app=app,
    )
    assert error is None and sqlite_root == internal

    resolved, error = resolve_rpath_dependency(
        dependency="@rpath/libcrypto.3.dylib",
        roots={ssl_root, sqlite_root},
        app=app,
        resources=app / "Contents/Resources",
        manifest=manifest,
    )
    assert error is None and resolved == libcrypto
    resolved, error = resolve_rpath_dependency(
        dependency="@rpath/libsqlite3.dylib",
        roots={ssl_root, sqlite_root},
        app=app,
        resources=app / "Contents/Resources",
        manifest=manifest,
    )
    assert error is None and resolved == libsqlite


def test_rpath_rejects_absolute_root_and_shadow_candidate(tmp_path: Path) -> None:
    app = tmp_path / "Agent Quota.app"
    executable = app / "Contents/MacOS/Agent Quota"
    first_root = app / "Contents/Resources/sidecar/one"
    second_root = app / "Contents/Resources/sidecar/two"
    for path in (
        executable,
        first_root / "libshadow.dylib",
        second_root / "libshadow.dylib",
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"binary")
        path.chmod(0o755)

    root, error = resolve_rpath_root(
        entry="/tmp",
        image=first_root / "image",
        executable=executable,
        app=app,
    )
    assert root is None
    assert error is not None and "unsafe LC_RPATH" in error

    manifest = {
        "sidecar/one/libshadow.dylib",
        "sidecar/two/libshadow.dylib",
    }
    resolved, error = resolve_rpath_dependency(
        dependency="@rpath/libshadow.dylib",
        roots={first_root, second_root},
        app=app,
        resources=app / "Contents/Resources",
        manifest=manifest,
    )
    assert resolved is None
    assert error is not None and "exactly one" in error


def test_unrelated_image_rpath_cannot_prove_dependency_reachable(tmp_path: Path) -> None:
    app = tmp_path / "Agent Quota.app"
    resources = app / "Contents/Resources"
    unrelated_root = resources / "sibling/lib"
    target = unrelated_root / "libfoo.dylib"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"binary")
    target.chmod(0o755)

    resolved, error = resolve_scoped_rpath_dependency(
        dependency="@rpath/libfoo.dylib",
        image_roots=set(),
        all_roots={unrelated_root},
        app=app,
        resources=resources,
        manifest={"sibling/lib/libfoo.dylib"},
    )
    assert resolved is None
    assert error is not None and "image-local" in error


def test_rpath_root_rejects_internal_symlink_to_manifest_directory(tmp_path: Path) -> None:
    app = tmp_path / "Agent Quota.app"
    executable = app / "Contents/MacOS/Agent Quota"
    real_root = app / "Contents/Resources/sidecar/_internal"
    image = app / "Contents/Frameworks/image.dylib"
    link = app / "Contents/Frameworks/rpath-link"
    for path in (executable, image):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"binary")
    real_root.mkdir(parents=True)
    link.symlink_to(real_root, target_is_directory=True)

    resolved, error = resolve_rpath_root(
        entry="@loader_path/rpath-link",
        image=image,
        executable=executable,
        app=app,
    )
    assert resolved is None
    assert error is not None and "ancestry" in error


def test_rpath_root_rejects_attacker_owned_app_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = tmp_path / "Agent Quota.app"
    executable = app / "Contents/MacOS/Agent Quota"
    image = app / "Contents/Resources/sidecar/image.dylib"
    for path in (executable, image):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"binary")
    original_lstat = Path.lstat

    def forged_lstat(path: Path) -> os.stat_result:
        metadata = original_lstat(path)
        if path == app:
            fields = list(metadata)
            fields[4] = os.geteuid() + 1
            return os.stat_result(fields)
        return metadata

    monkeypatch.setattr(Path, "lstat", forged_lstat)
    resolved, error = resolve_rpath_root(
        entry="@loader_path",
        image=image,
        executable=executable,
        app=app,
    )
    assert resolved is None
    assert error is not None and "ancestry" in error


def test_bundle_gate_includes_root_without_any_rpath(tmp_path: Path) -> None:
    app = tmp_path / "Agent Quota.app"
    app.mkdir(mode=0o755)
    app.chmod(0o775)
    errors: list[str] = []
    validate_bundle_nodes(app, errors)
    assert errors == ["group/world writable bundle path: ."]
