"""Prove Apple-signed Keychain continuity across distinct CDHash builds in an isolated keychain.

Positive check: Build A and Build B have different binary bytes/CDHashes, share the same
Apple Team ID signature, and Build B reads Build A's Keychain item with UI interaction disabled.
Negative check: Build C has the same CFBundleIdentifier but ad-hoc signature and MUST be denied.
Never touches the user's login keychain.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

import macos_signing

SWIFT_PROBE_TEMPLATE = """
import Foundation
import Security

let buildSalt = "__BUILD_SALT__"
let keychainPath = CommandLine.arguments[1]
let password = Data(CommandLine.arguments[2].utf8)
let mode = CommandLine.arguments[3]
let service = "com.agentquota.desktop.continuity-self-test"
let account = CommandLine.arguments[4]

var keychain: SecKeychain?
if mode == "create-keychain" {
    let status = password.withUnsafeBytes { raw in
        SecKeychainCreate(
            keychainPath,
            UInt32(password.count),
            raw.baseAddress!,
            false,
            nil,
            &keychain
        )
    }
    guard status == errSecSuccess else { exit(20) }
    exit(0)
}

guard SecKeychainOpen(keychainPath, &keychain) == errSecSuccess, let kc = keychain else {
    exit(21)
}
let unlockStatus = password.withUnsafeBytes { raw in
    SecKeychainUnlock(kc, UInt32(password.count), raw.baseAddress!, true)
}
guard unlockStatus == errSecSuccess else { exit(22) }

if mode == "delete-keychain" {
    _ = SecKeychainDelete(kc)
    exit(0)
}

if mode == "write" {
    var access: SecAccess?
    let desc = "Continuity Probe \\(buildSalt)" as CFString
    guard SecAccessCreate(desc, nil, &access) == errSecSuccess,
          let acl = access
    else { exit(23) }
    let secret = Data("probe-secret-payload".utf8)
    let query: [CFString: Any] = [
        kSecClass: kSecClassGenericPassword,
        kSecAttrService: service,
        kSecAttrAccount: account,
        kSecAttrAccess: acl,
        kSecUseKeychain: kc,
        kSecValueData: secret,
    ]
    let status = SecItemAdd(query as CFDictionary, nil)
    guard status == errSecSuccess else {
        fputs("SecItemAdd failed: \\(status)\\n", stderr)
        exit(24)
    }
    exit(0)
}

if mode == "read-noninteractive" {
    guard SecKeychainSetUserInteractionAllowed(false) == errSecSuccess else { exit(25) }
    defer { _ = SecKeychainSetUserInteractionAllowed(true) }
    let query: [CFString: Any] = [
        kSecClass: kSecClassGenericPassword,
        kSecAttrService: service,
        kSecAttrAccount: account,
        kSecMatchSearchList: [kc],
        kSecMatchLimit: kSecMatchLimitOne,
        kSecReturnData: true,
    ]
    var item: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &item)
    guard status == errSecSuccess,
          let data = item as? Data,
          String(data: data, encoding: .utf8) == "probe-secret-payload"
    else {
        fputs("SecItemCopyMatching status: \\(status) (salt=\\(buildSalt))\\n", stderr)
        exit(30)
    }
    exit(0)
}
exit(64)
"""


def build_probe_bundle(
    work: Path,
    name: str,
    salt: str,
    identifier: str,
    identity: str,
    team: str | None,
) -> tuple[Path, dict[str, object]]:
    src = work / f"{name}.swift"
    src.write_text(SWIFT_PROBE_TEMPLATE.replace("__BUILD_SALT__", salt), encoding="utf-8")
    bundle = work / f"{name}.app"
    macos_dir = bundle / "Contents/MacOS"
    macos_dir.mkdir(parents=True)
    exe = macos_dir / "ContinuityProbe"
    subprocess.run(
        [
            "/usr/bin/xcrun",
            "swiftc",
            "-target",
            "arm64-apple-macosx13.0",
            "-O",
            "-framework",
            "Security",
            str(src),
            "-o",
            str(exe),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    plist = bundle / "Contents/Info.plist"
    subprocess.run(["/usr/bin/plutil", "-create", "xml1", str(plist)], check=True)
    subprocess.run(
        [
            "/usr/bin/plutil",
            "-insert",
            "CFBundleExecutable",
            "-string",
            "ContinuityProbe",
            str(plist),
        ],
        check=True,
    )
    subprocess.run(
        ["/usr/bin/plutil", "-insert", "CFBundleIdentifier", "-string", identifier, str(plist)],
        check=True,
    )
    subprocess.run(
        ["/usr/bin/plutil", "-insert", "CFBundlePackageType", "-string", "APPL", str(plist)],
        check=True,
    )
    meta = macos_signing.sign(bundle, identifier, identity, team)
    return exe, meta


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    env = dict(os.environ)
    if not env.get("AQ_CODESIGN_IDENTITY") and not env.get("AQ_ALLOW_ADHOC_SIGNING"):
        env["AQ_CODESIGN_AUTO"] = "1"
    identity, team = macos_signing.configuration(env)
    if team is None:
        raise SystemExit(
            "Cross-build Keychain continuity verification requires an Apple Team identity"
        )
    macos_signing.preflight(identity)

    identifier = "com.agentquota.desktop.continuity-probe"
    with tempfile.TemporaryDirectory(prefix="aq-xcode-continuity-") as raw_tmp:
        work = Path(raw_tmp).resolve()
        kc_path = work / "isolated.keychain-db"
        kc_pass = uuid.uuid4().hex
        account = f"probe-{uuid.uuid4()}"

        exe_a, meta_a = build_probe_bundle(
            work, "ProbeA", "build-v1-alpha", identifier, identity, team
        )
        exe_b, meta_b = build_probe_bundle(
            work, "ProbeB", "build-v2-bravo-updated", identifier, identity, team
        )
        exe_c, meta_c = build_probe_bundle(
            work, "ProbeC", "build-v3-adhoc-spoof", identifier, "-", None
        )

        if meta_a["cdhash"] == meta_b["cdhash"]:
            raise SystemExit("ProbeA and ProbeB unexpectedly produced identical CDHashes")

        subprocess.run([str(exe_a), str(kc_path), kc_pass, "create-keychain", account], check=True)
        try:
            subprocess.run([str(exe_a), str(kc_path), kc_pass, "write", account], check=True)
            # Positive proof: Build B (different CDHash, same Apple Team ID) reads with 0 UI prompts
            read_b = subprocess.run(
                [str(exe_b), str(kc_path), kc_pass, "read-noninteractive", account],
                capture_output=True,
                text=True,
            )
            if read_b.returncode != 0:
                detail = read_b.stderr.strip()
                raise SystemExit(
                    f"Apple-signed Build B failed non-interactive Keychain read: {detail}"
                )
            # Negative proof: Ad-hoc Build C (same bundle ID, no Apple Team ID) MUST be blocked
            read_c = subprocess.run(
                [str(exe_c), str(kc_path), kc_pass, "read-noninteractive", account],
                capture_output=True,
                text=True,
            )
            if read_c.returncode == 0:
                raise SystemExit(
                    "Negative control failed: ad-hoc Build C unexpectedly read Apple-team item"
                )
        finally:
            subprocess.run(
                [str(exe_a), str(kc_path), kc_pass, "delete-keychain", account],
                check=False,
                capture_output=True,
            )

    report = {
        "adhoc_spoof_blocked": True,
        "build_a_cdhash": meta_a["cdhash"],
        "build_b_cdhash": meta_b["cdhash"],
        "adhoc_c_cdhash": meta_c["cdhash"],
        "designated_requirement": meta_a["designated_requirement"],
        "noninteractive_cross_build_read": "pass",
        "status": "pass",
        "team_id": team,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
