"""Sign with a stable Apple team identity, or an explicitly requested test identity.

Self-signed certificates are intentionally not a fallback: macOS keychain partitions
still identify them by CDHash. Never change a user's keychain ACL from this tool.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import subprocess
from pathlib import Path

APPLE_SIGNER_REQUIREMENT = (
    "anchor apple generic and ("
    "(certificate 1[field.1.2.840.113635.100.6.2.6] exists and "
    "certificate leaf[field.1.2.840.113635.100.6.1.13] exists) or "
    "(certificate 1[field.1.2.840.113635.100.6.2.1] exists and "
    "certificate leaf[field.1.2.840.113635.100.6.1.12] exists))"
)
COMPONENTS = {
    "main": ("", "com.agentquota.desktop"),
    "helper": (
        "Contents/Resources/native-helper/AgentQuotaNative.app",
        "com.agentquota.desktop.native-helper",
    ),
    "sidecar": (
        "Contents/Resources/sidecar/agent-quota-sidecar",
        "com.agentquota.desktop.sidecar",
    ),
}
MACHO_MAGICS = {
    b"\xfe\xed\xfa\xce",
    b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe",
    b"\xbe\xba\xfe\xca",
    b"\xca\xfe\xba\xbf",
    b"\xbf\xba\xfe\xca",
}


def configuration(environ: dict[str, str]) -> tuple[str, str | None]:
    identity = environ.get("AQ_CODESIGN_IDENTITY", "")
    team = environ.get("AQ_CODESIGN_TEAM_ID", "")
    adhoc = environ.get("AQ_ALLOW_ADHOC_SIGNING", "")
    if identity or team:
        if adhoc:
            raise ValueError("Apple signing and AQ_ALLOW_ADHOC_SIGNING cannot be combined")
        if not re.fullmatch(r"[0-9a-fA-F]{40}", identity):
            raise ValueError("AQ_CODESIGN_IDENTITY must be the certificate's 40-digit SHA-1")
        if not re.fullmatch(r"[A-Z0-9]{10}", team):
            raise ValueError("AQ_CODESIGN_TEAM_ID must be the expected 10-character Apple Team ID")
        return identity.upper(), team
    if adhoc == "1":
        return "-", None
    raise ValueError(
        "Stable signing requires AQ_CODESIGN_IDENTITY and AQ_CODESIGN_TEAM_ID. "
        "Install an Apple Development or Developer ID Application identity in Keychain. "
        "Only for tests, explicitly set AQ_ALLOW_ADHOC_SIGNING=1; "
        "that mode does not preserve keychain authorization across helper changes."
    )


def run(*command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True)


def preflight(identity: str) -> None:
    if identity == "-":
        return
    identities = run("/usr/bin/security", "find-identity", "-v", "-p", "codesigning").stdout
    if re.search(rf"\b{re.escape(identity)}\b", identities, re.IGNORECASE) is None:
        raise ValueError("The selected valid code-signing identity is not available in Keychain")


def parse_details(details: str) -> dict[str, str]:
    result = {}
    for line in details.splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            if key in {"Identifier", "TeamIdentifier", "CDHash", "Signature"}:
                result[key] = value
        if line.startswith("designated => ") or line.startswith("# designated => "):
            result["requirement"] = line.split("=> ", 1)[1]
    return result


def is_developer_id_identity(identity: str) -> bool:
    if identity == "-":
        return False
    identities = run("/usr/bin/security", "find-identity", "-v", "-p", "codesigning").stdout
    pattern = re.compile(
        rf'\b{re.escape(identity)}\b.*"Developer ID Application:',
        re.IGNORECASE,
    )
    return any(pattern.search(line) for line in identities.splitlines())


def verify(path: Path, identifier: str, team: str | None) -> dict[str, object]:
    run("/usr/bin/codesign", "--verify", "--strict", str(path))
    output = run("/usr/bin/codesign", "-d", "--verbose=4", "-r-", str(path))
    details = parse_details(output.stdout + "\n" + output.stderr)
    if details.get("Identifier") != identifier:
        raise ValueError(f"Unexpected signing identifier for {path.name}")
    if team:
        if details.get("TeamIdentifier") != team or "cdhash" in details.get("requirement", ""):
            raise ValueError(f"Unstable or unexpected team identity for {path.name}")
        requirement = (
            f'({APPLE_SIGNER_REQUIREMENT}) and identifier "{identifier}" '
            f'and certificate leaf[subject.OU] = "{team}"'
        )
        run("/usr/bin/codesign", "--verify", "--strict", "-R", f"={requirement}", str(path))
        if not details.get("requirement"):
            raise ValueError("Missing designated requirement")
    elif details.get("Signature") != "adhoc":
        raise ValueError(f"Expected explicit ad-hoc test signature for {path.name}")
    executable = path
    if path.is_dir():
        plist = plistlib.loads((path / "Contents/Info.plist").read_bytes())
        name = plist["CFBundleExecutable"]
        if not isinstance(name, str) or Path(name).name != name:
            raise ValueError("Unsafe bundle executable name")
        executable = path / "Contents/MacOS" / name
    return {
        "identifier": identifier,
        "team_id": team,
        "cdhash": details.get("CDHash"),
        "designated_requirement": details.get("requirement"),
        "keychain_identity_stable": team is not None,
        "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
    }


def sign(
    path: Path,
    identifier: str,
    identity: str,
    team: str | None,
    *,
    hardened_runtime: bool = False,
) -> dict[str, object]:
    if not re.fullmatch(r"[A-Za-z0-9.-]+", identifier):
        raise ValueError("Invalid signing identifier")
    # Do not use --deep to sign: resources were signed before their manifest was pinned.
    command = ["/usr/bin/codesign", "--force", "--sign", identity, "--identifier", identifier]
    if team:
        command.append("--timestamp")
        if hardened_runtime:
            command.extend(["--options", "runtime"])
    run(*command, str(path))
    return verify(path, identifier, team)


def sign_sidecar_tree(
    root: Path,
    identity: str,
    team: str | None,
    *,
    hardened_runtime: bool = False,
) -> None:
    # PyInstaller contains extension modules and a Python framework as regular files.
    # Sign each nested Mach-O first, without relaxing library or keychain permissions.
    main = root / "agent-quota-sidecar"
    paths = sorted(root.rglob("*"), key=lambda p: (-len(p.parts), str(p)))
    # The pinned uv CPython runtime is flat. Framework/app bundles need their own
    # resource seals; reject an unsupported layout before changing any signatures.
    if any(p.is_dir() and p.suffix in {".framework", ".app", ".xpc", ".bundle"} for p in paths):
        raise ValueError("Nested runtime bundles are unsupported; use the pinned flat uv Python")
    for path in paths:
        if path.is_symlink():
            raise ValueError("Sidecar resource symlinks must be materialized before signing")
        if not path.is_file() or path == main:
            continue
        with path.open("rb") as stream:
            magic = stream.read(4)
        if magic in MACHO_MAGICS:
            relative = path.relative_to(root).as_posix()
            # A deterministic identifier for every embedded object; no user path is embedded.
            suffix = hashlib.sha256(relative.encode()).hexdigest()[:24]
            sign(
                path,
                f"com.agentquota.desktop.runtime.{suffix}",
                identity,
                team,
                hardened_runtime=hardened_runtime,
            )
    sign(
        main,
        "com.agentquota.desktop.sidecar",
        identity,
        team,
        hardened_runtime=hardened_runtime,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["preflight", "sign", "sign-sidecar", "audit"])
    parser.add_argument("--path", type=Path)
    parser.add_argument("--identifier")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    identity, team = configuration(dict(os.environ))
    preflight(identity)
    if args.action == "preflight":
        print("apple-team" if team else "adhoc-test-only")
        return 0
    if args.path is None:
        parser.error("--path is required")
    hardened_runtime = bool(team) and (
        os.environ.get("AQ_CODESIGN_HARDENED_RUNTIME") == "1" or is_developer_id_identity(identity)
    )
    if args.action == "sign":
        if not args.identifier:
            parser.error("--identifier is required")
        sign(args.path, args.identifier, identity, team, hardened_runtime=hardened_runtime)
    elif args.action == "sign-sidecar":
        sign_sidecar_tree(args.path, identity, team, hardened_runtime=hardened_runtime)
    else:
        if args.output is None:
            parser.error("--output is required for audit")
        components = {
            name: verify(args.path / relative, identifier, team)
            for name, (relative, identifier) in COMPONENTS.items()
        }
        report = {
            "schema": "agent-quota-signing-audit-v1",
            "mode": "apple-team" if team else "adhoc-test-only",
            "keychain_identity_stable": team is not None,
            "notarized": False,
            "components": components,
        }
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, subprocess.CalledProcessError) as error:
        detail = (
            error.stderr.strip() if isinstance(error, subprocess.CalledProcessError) else str(error)
        )
        raise SystemExit(f"macOS signing failed: {detail}") from None
