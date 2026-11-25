#!/usr/bin/env python3
"""Fail-closed Apple Developer ID notarization, stapling, and Gatekeeper verification."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_cmd(*command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True)


def locate_dmg(artifact_dir: Path) -> Path:
    preferred = artifact_dir / "Agent-Quota-0.1.0-arm64-local-development.dmg"
    if preferred.is_file():
        return preferred
    candidates = sorted(p for p in artifact_dir.glob("*.dmg") if p.is_file())
    if len(candidates) != 1:
        raise ValueError(f"Expected exactly 1 .dmg in {artifact_dir}, found {len(candidates)}")
    return candidates[0]


def inspect_codesign_app(app: Path) -> dict[str, object]:
    output = run_cmd("/usr/bin/codesign", "-dv", "--verbose=4", str(app))
    text = output.stdout + "\n" + output.stderr
    authorities: list[str] = []
    hardened_runtime = False
    team_id: str | None = None
    for line in text.splitlines():
        if line.startswith("Authority="):
            authorities.append(line.split("=", 1)[1].strip())
        elif line.startswith("CodeDirectory "):
            match = re.search(r"\bflags=0x[0-9a-fA-F]+\(([^)]*)\)", line)
            if match:
                flags = {flag.strip().lower() for flag in match.group(1).split(",") if flag.strip()}
                hardened_runtime = "runtime" in flags
        elif line.startswith("TeamIdentifier="):
            value = line.split("=", 1)[1].strip()
            team_id = None if value == "not set" else value
    is_developer_id = any(auth.startswith("Developer ID Application:") for auth in authorities)
    return {
        "authorities": authorities,
        "is_developer_id": is_developer_id,
        "hardened_runtime": hardened_runtime,
        "team_id": team_id,
    }


def validate_ready_for_notarization(artifact_dir: Path, profile: str | None) -> dict[str, object]:
    app = artifact_dir / "Agent Quota.app"
    if not app.is_dir():
        raise ValueError(f"Missing Agent Quota.app in {artifact_dir}")
    dmg = locate_dmg(artifact_dir)
    signing_audit_path = artifact_dir / "signing-audit.json"
    provenance_path = artifact_dir / "build-provenance.json"
    if not signing_audit_path.is_file() or not provenance_path.is_file():
        raise ValueError("Missing signing-audit.json or build-provenance.json in artifact-dir")

    signing_audit = json.loads(signing_audit_path.read_text(encoding="utf-8"))
    if (
        signing_audit.get("mode") != "apple-team"
        or signing_audit.get("keychain_identity_stable") is not True
    ):
        raise ValueError("Artifact signing mode must be apple-team with stable keychain identity")

    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    source_commit = provenance.get("source_commit")
    if not isinstance(source_commit, str) or re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
        raise ValueError("build-provenance.json missing valid 40-char source_commit")

    run_cmd("/usr/bin/codesign", "--verify", "--deep", "--strict", str(app))
    signature = inspect_codesign_app(app)
    if not signature["is_developer_id"]:
        raise ValueError(
            "Apple notarization requires a Developer ID Application certificate; "
            "Apple Development signatures cannot be notarized."
        )
    if not signature["hardened_runtime"]:
        raise ValueError(
            "Apple notarization requires Hardened Runtime (--options runtime) on Agent Quota.app"
        )

    chosen_profile = (profile or os.environ.get("AQ_NOTARY_KEYCHAIN_PROFILE", "")).strip()
    if not chosen_profile or re.fullmatch(r"[A-Za-z0-9._-]+", chosen_profile) is None:
        raise ValueError(
            "Valid notarytool keychain profile required via --profile or AQ_NOTARY_KEYCHAIN_PROFILE"
        )

    return {
        "app": app,
        "dmg": dmg,
        "commit": source_commit,
        "profile": chosen_profile,
        "team_id": signature["team_id"],
    }


def notarize_artifact_dir(
    artifact_dir: Path,
    profile: str | None = None,
    *,
    dry_run: bool = False,
) -> dict[str, object]:
    plan = validate_ready_for_notarization(artifact_dir, profile)
    app: Path = plan["app"]  # type: ignore[assignment]
    dmg: Path = plan["dmg"]  # type: ignore[assignment]
    commit: str = plan["commit"]  # type: ignore[assignment]
    chosen_profile: str = plan["profile"]  # type: ignore[assignment]

    if dry_run:
        return {
            "schema": "agent-quota-notarization-preflight-v1",
            "status": "ready",
            "commit": commit,
            "app": app.name,
            "dmg": dmg.name,
            "profile": chosen_profile,
            "authority_type": "developer-id",
            "hardened_runtime": True,
        }

    submit = run_cmd(
        "/usr/bin/xcrun",
        "notarytool",
        "submit",
        str(dmg),
        "--keychain-profile",
        chosen_profile,
        "--wait",
        "--output-format",
        "json",
    )
    submit_payload = json.loads(submit.stdout)
    submission_id = submit_payload.get("id")
    notary_status = submit_payload.get("status")
    if (
        notary_status != "Accepted"
        or not isinstance(submission_id, str)
        or not submission_id.strip()
    ):
        raise ValueError(f"Apple notarization did not accept DMG: status={notary_status!r}")

    run_cmd("/usr/bin/xcrun", "stapler", "staple", str(app))
    run_cmd("/usr/bin/xcrun", "stapler", "validate", str(app))
    run_cmd("/usr/bin/xcrun", "stapler", "staple", str(dmg))
    run_cmd("/usr/bin/xcrun", "stapler", "validate", str(dmg))
    run_cmd("/usr/sbin/spctl", "--assess", "--verbose=4", "--type", "execute", str(app))
    run_cmd("/usr/bin/codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app))

    executable = app / "Contents/MacOS/agent-quota-desktop"
    report: dict[str, object] = {
        "schema": "agent-quota-notarization-audit-v1",
        "commit": commit,
        "submission_id": submission_id,
        "status": "Accepted",
        "stapled_app": True,
        "stapled_dmg": True,
        "gatekeeper_assessed": True,
        "dmg_sha256": sha256_file(dmg),
        "app_executable_sha256": sha256_file(executable),
    }
    output_path = artifact_dir / "notarization-audit.json"
    output_path.write_text(
        json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = notarize_artifact_dir(
        args.artifact_dir,
        profile=args.profile,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        detail = (
            error.stderr.strip()
            if isinstance(error, subprocess.CalledProcessError) and error.stderr
            else str(error)
        )
        raise SystemExit(f"macOS notarization failed: {detail}") from None
