from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path


def test_plist_identity_parser_rejects_shape_and_preserves_exact_rows() -> None:
    document = {
        "images": [
            {
                "image-path": "/tmp/image.dmg",
                "system-entities": [{"dev-entry": "/dev/disk9", "mount-point": "/tmp/mount"}],
            }
        ]
    }
    helper = Path(__file__).resolve().parents[1] / "tools/dmg_mount_identity.py"
    valid = subprocess.run(
        [
            sys.executable,
            str(helper),
            "--image",
            "/tmp/image.dmg",
            "--mount",
            "/tmp/mount",
        ],
        input=plistlib.dumps(document),
        capture_output=True,
        check=False,
    )
    assert valid.returncode == 0
    assert valid.stdout.strip() == b"/dev/disk9"
    for invalid in ({}, {"images": [{}]}, {"images": "bad"}):
        rejected = subprocess.run(
            [
                sys.executable,
                str(helper),
                "--image",
                "/tmp/image.dmg",
                "--mount",
                "/tmp/mount",
            ],
            input=plistlib.dumps(invalid),
            capture_output=True,
            check=False,
        )
        assert rejected.returncode == 2


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o700)


def _run_cleanup(
    tmp_path: Path, *, mode: str, expected_device: str
) -> subprocess.CompletedProcess[str]:
    root = tmp_path / "case"
    root.mkdir(parents=True)
    image = root / "image.dmg"
    image.touch()
    mount = root / "mount"
    mount.mkdir()
    state = root / "state"
    state.write_text("mounted 0")
    actual_device = "/dev/disk9"
    hdiutil = root / "hdiutil"
    mount_bin = root / "mount-bin"
    sleep_bin = root / "sleep"
    _write_executable(
        hdiutil,
        f"""#!/usr/bin/env python3
import plistlib, sys
from pathlib import Path
state=Path({str(state)!r})
mounted, attempts=state.read_text().split(); attempts=int(attempts)
args=sys.argv[1:]
if args == ['info','-plist']:
    if {mode!r} == 'malformed':
        sys.stdout.buffer.write(b'not-plist'); raise SystemExit(0)
    images=[]
    if mounted == 'mounted':
        images=[{{'image-path':{str(image)!r},'system-entities':[{{'dev-entry':{actual_device!r},'mount-point':{str(mount)!r}}}]}}]
    sys.stdout.buffer.write(plistlib.dumps({{'images':images}})); raise SystemExit(0)
if args and args[0] == 'detach':
    force='-force' in args
    if {mode!r} == 'busy' and not force and attempts < 5:
        state.write_text(f'mounted {{attempts+1}}'); raise SystemExit(1)
    state.write_text(f'unmounted {{attempts}}'); raise SystemExit(0)
raise SystemExit(2)
""",
    )
    _write_executable(
        mount_bin,
        f"""#!/bin/sh
set -- $(cat {state})
[ "$1" = mounted ] && printf '%s on %s (apfs, local)\\n' {actual_device} {str(mount)!r}
""",
    )
    _write_executable(sleep_bin, "#!/bin/sh\nexit 0\n")
    env = {
        **os.environ,
        "AQ_HDIUTIL_BIN": str(hdiutil),
        "AQ_MOUNT_BIN": str(mount_bin),
        "AQ_PYTHON_BIN": "/usr/bin/python3",
        "AQ_SLEEP_BIN": str(sleep_bin),
        "AQ_IDENTITY_HELPER": str(
            Path(__file__).resolve().parents[1] / "tools/dmg_mount_identity.py"
        ),
    }
    command = (
        f'. "{Path(__file__).resolve().parents[1] / "tools/dmg_lifecycle_cleanup.sh"}"; '
        f'aq_cleanup_dmg "{image}" "{mount}" "{expected_device}"'
    )
    return subprocess.run(
        ["/bin/sh", "-eu", "-c", command],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_cleanup_normal_and_busy_force_paths(tmp_path: Path) -> None:
    normal = _run_cleanup(tmp_path / "normal", mode="normal", expected_device="/dev/disk9")
    assert normal.returncode == 0, normal.stderr
    busy = _run_cleanup(tmp_path / "busy", mode="busy", expected_device="/dev/disk9")
    assert busy.returncode == 0, busy.stderr


def test_cleanup_rejects_device_drift_and_malformed_plist(tmp_path: Path) -> None:
    drift = _run_cleanup(tmp_path / "drift", mode="normal", expected_device="/dev/disk8")
    assert drift.returncode != 0
    assert "identity drift" in drift.stderr
    malformed = _run_cleanup(tmp_path / "malformed", mode="malformed", expected_device="/dev/disk9")
    assert malformed.returncode != 0
    assert "cannot prove" in malformed.stderr


def test_lifecycle_validation_preserves_fixed_real_state() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "tools/test_macos_package_lifecycle.sh").read_text()
    assert "pwd.getpwuid(os.geteuid()).pw_dir" in script
    assert "AQ_DATA_ROOT" not in script
    assert "lifecycle-sentinel" not in script
    assert "state_before=" in script
    assert "assert_persistent_state" in script
    assert "find-generic-password" in script
    assert "credential-references" not in script
    assert "evidence_root=" not in script
    assert '/usr/bin/find "$test_root" -depth -delete' in script
    assert 'echo "evidence_retention=none"' in script
