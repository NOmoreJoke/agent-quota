#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec /usr/bin/python3 -I -S - "$repo_root" <<'PY'
from __future__ import annotations

import os
import pwd
import re
import subprocess
import sys
from pathlib import Path

ALLOWED_ENV_KEYS = {
    "AQ_CODESIGN_IDENTITY",
    "AQ_CODESIGN_TEAM_ID",
    "AQ_CODESIGN_HARDENED_RUNTIME",
    "AQ_RUST_BIN",
    "AQ_ANTIGRAVITY_OAUTH_CLIENT_ID",
    "AQ_ANTIGRAVITY_OAUTH_CLIENT_SECRET",
    "AQ_NOTARY_KEYCHAIN_PROFILE",
}


def load_env_local(path: Path, env: dict[str, str]) -> None:
    if not path.exists():
        return
    if path.is_symlink() or not path.is_file():
        raise SystemExit(".env.local must be a regular non-symlink file")
    for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise SystemExit(f"Invalid .env.local syntax on line {lineno}")
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in ALLOWED_ENV_KEYS:
            raise SystemExit(f"Disallowed key in .env.local on line {lineno}: {key}")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if value and not env.get(key):
            env[key] = value


def extract_team_ou(common_name: str, expected_sha1: str) -> str:
    certs_out = subprocess.run(
        ["/usr/bin/security", "find-certificate", "-a", "-Z", "-c", common_name, "-p"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    pem_blocks = re.findall(
        r"SHA-1 hash:\s*([0-9A-Fa-f]{40})\s*\n(-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----)",
        certs_out,
        flags=re.DOTALL,
    )
    selected_pem = next(
        (pem for sha, pem in pem_blocks if sha.upper() == expected_sha1.upper()),
        None,
    )
    if not selected_pem:
        raise SystemExit("Unable to locate PEM certificate matching selected SHA-1 identity")
    subject = subprocess.run(
        ["/usr/bin/openssl", "x509", "-noout", "-subject"],
        input=selected_pem,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    match = re.search(r"(?:^|/|\s|,)OU=([A-Z0-9]{10})(?:/|,|\s|$)", subject)
    if not match:
        raise SystemExit(
            "Unable to extract 10-character Apple Team ID (OU) from selected certificate"
        )
    return match.group(1)


def discover_apple_identity(
    explicit_identity: str, explicit_team: str
) -> tuple[str, str]:
    identities_out = subprocess.run(
        ["/usr/bin/security", "find-identity", "-v", "-p", "codesigning"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    entries: list[tuple[str, str]] = []
    for line in identities_out.splitlines():
        match = re.match(r'^\s*\d+\)\s+([0-9A-Fa-f]{40})\s+"([^"]+)"\s*$', line)
        if match:
            entries.append((match.group(1).upper(), match.group(2)))
    if not entries:
        raise SystemExit(
            "No valid code-signing certificate found in Keychain; "
            "install Apple Development or Developer ID Application first."
        )

    if explicit_identity:
        matches = [item for item in entries if item[0] == explicit_identity.upper()]
        if not matches:
            raise SystemExit("Configured AQ_CODESIGN_IDENTITY was not found in Keychain")
        chosen_sha, chosen_cn = matches[0]
        team = explicit_team or extract_team_ou(chosen_cn, chosen_sha)
        return chosen_sha, team

    dev_id = [item for item in entries if item[1].startswith("Developer ID Application:")]
    apple_dev = [item for item in entries if item[1].startswith("Apple Development:")]
    candidates = dev_id if dev_id else apple_dev
    if len(candidates) != 1:
        raise SystemExit(
            "Expected exactly one Developer ID Application or Apple Development identity "
            f"(found {len(candidates)}); set AQ_CODESIGN_IDENTITY and AQ_CODESIGN_TEAM_ID explicitly."
        )
    chosen_sha, chosen_cn = candidates[0]
    team = explicit_team or extract_team_ou(chosen_cn, chosen_sha)
    return chosen_sha, team


def main() -> None:
    repo_root = Path(sys.argv[1]).resolve(strict=True)
    env = dict(os.environ)
    if env.get("AQ_ALLOW_ADHOC_SIGNING"):
        raise SystemExit(
            "build_apple_signed_package.sh refuses AQ_ALLOW_ADHOC_SIGNING; "
            "use build_macos_package.sh directly for ad-hoc test builds."
        )
    load_env_local(repo_root / ".env.local", env)
    identity, team = discover_apple_identity(
        env.get("AQ_CODESIGN_IDENTITY", "").strip(),
        env.get("AQ_CODESIGN_TEAM_ID", "").strip(),
    )
    env["AQ_CODESIGN_IDENTITY"] = identity
    env["AQ_CODESIGN_TEAM_ID"] = team

    if not env.get("AQ_RUST_BIN"):
        real_home = Path(pwd.getpwuid(os.geteuid()).pw_dir)
        default_rust_bin = real_home / "Library/Caches/agent-quota/rust-1.97.1/bin"
        if default_rust_bin.is_dir():
            env["AQ_RUST_BIN"] = str(default_rust_bin)

    os.execvpe("/bin/sh", ["/bin/sh", str(repo_root / "tools/build_macos_package.sh")], env)


if __name__ == "__main__":
    main()
PY
