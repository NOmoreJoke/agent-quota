#!/usr/bin/env python3
"""Emit closed source-to-artifact provenance for a local macOS RC."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_signing_audit(signing: object, app: Path) -> dict[str, object]:
    if not isinstance(signing, dict) or set(signing) != {
        "schema",
        "mode",
        "keychain_identity_stable",
        "notarized",
        "components",
    }:
        raise ValueError("invalid signing audit shape")
    mode = signing["mode"]
    stable = mode == "apple-team"
    if (
        signing["schema"] != "agent-quota-signing-audit-v1"
        or mode not in {"apple-team", "adhoc-test-only"}
        or signing["keychain_identity_stable"] is not stable
        or signing["notarized"] is not False
    ):
        raise ValueError("inconsistent signing audit mode")
    expected = {
        "main": ("com.agentquota.desktop", "Contents/MacOS/agent-quota-desktop"),
        "helper": (
            "com.agentquota.desktop.native-helper",
            "Contents/Resources/native-helper/AgentQuotaNative.app/Contents/MacOS/AgentQuotaNative",
        ),
        "sidecar": (
            "com.agentquota.desktop.sidecar",
            "Contents/Resources/sidecar/agent-quota-sidecar",
        ),
    }
    components = signing["components"]
    if not isinstance(components, dict) or set(components) != set(expected):
        raise ValueError("missing signing audit components")
    teams = set()
    for name, (identifier, relative) in expected.items():
        component = components[name]
        if not isinstance(component, dict) or set(component) != {
            "identifier",
            "team_id",
            "cdhash",
            "designated_requirement",
            "keychain_identity_stable",
            "executable_sha256",
        }:
            raise ValueError("invalid signing audit component")
        requirement = component["designated_requirement"]
        if (
            component["identifier"] != identifier
            or component["keychain_identity_stable"] is not stable
            or not isinstance(component["cdhash"], str)
            or re.fullmatch(r"[0-9a-f]{40}", component["cdhash"]) is None
            or component["executable_sha256"] != sha256(app / relative)
            or not isinstance(requirement, str)
            or not requirement
        ):
            raise ValueError("signing audit does not match artifact")
        team = component["team_id"]
        if stable:
            if not isinstance(team, str) or re.fullmatch(r"[A-Z0-9]{10}", team) is None:
                raise ValueError("missing Apple Team ID")
            if "cdhash" in requirement or "anchor apple" not in requirement:
                raise ValueError("unstable signing requirement")
            teams.add(team)
        elif team is not None:
            raise ValueError("ad-hoc report claims an Apple team")
    if stable and len(teams) != 1:
        raise ValueError("mixed signing teams")
    return signing


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--dmg", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--signing-audit", type=Path, required=True)
    args = parser.parse_args()

    if re.fullmatch(r"[0-9a-f]{40}", args.commit) is None:
        raise SystemExit("invalid source commit")
    executable = args.app / "Contents/MacOS/agent-quota-desktop"
    if not executable.is_file() or not args.dmg.is_file():
        raise SystemExit("artifact is incomplete")
    signing = validate_signing_audit(json.loads(args.signing_audit.read_text()), args.app)

    document = {
        "app_executable_sha256": sha256(executable),
        "artifact_class": "local development package",
        "dmg_sha256": sha256(args.dmg),
        "schema": "agent-quota-build-provenance-v1",
        "source_commit": args.commit,
        "source_dirty": False,
        "signing_audit_sha256": sha256(args.signing_audit),
        "signing_mode": signing["mode"],
        "keychain_identity_stable": signing["keychain_identity_stable"],
    }
    args.output.write_text(
        json.dumps(document, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
