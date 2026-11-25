"""Signing must fail closed, and certificate identity must survive a code update."""

from __future__ import annotations

import hashlib
import importlib.util
import runpy
import subprocess
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "macos_signing", Path(__file__).parents[1] / "tools/macos_signing.py"
)
assert SPEC is not None and SPEC.loader is not None
signing = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(signing)

TEAM = "ABCDE12345"
IDENTITY = "a" * 40
IDENTIFIER = "com.agentquota.desktop.native-helper"


def test_missing_identity_never_silently_falls_back() -> None:
    with pytest.raises(ValueError, match="Stable signing requires"):
        signing.configuration({})
    assert signing.configuration({"AQ_ALLOW_ADHOC_SIGNING": "1"}) == ("-", None)


@pytest.mark.parametrize(
    "env",
    [
        {"AQ_CODESIGN_IDENTITY": "-", "AQ_CODESIGN_TEAM_ID": TEAM},
        {"AQ_CODESIGN_IDENTITY": IDENTITY},
        {"AQ_CODESIGN_TEAM_ID": TEAM},
        {"AQ_CODESIGN_IDENTITY": IDENTITY, "AQ_CODESIGN_TEAM_ID": 'bad" or true'},
        {"AQ_ALLOW_ADHOC_SIGNING": "true"},
        {
            "AQ_CODESIGN_IDENTITY": IDENTITY,
            "AQ_CODESIGN_TEAM_ID": TEAM,
            "AQ_ALLOW_ADHOC_SIGNING": "1",
        },
    ],
)
def test_ambiguous_or_unsafe_configuration_is_rejected(env: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        signing.configuration(env)


def test_exact_identity_and_expected_team_are_required() -> None:
    assert signing.configuration(
        {"AQ_CODESIGN_IDENTITY": IDENTITY, "AQ_CODESIGN_TEAM_ID": TEAM}
    ) == (IDENTITY.upper(), TEAM)


def stub_codesign(monkeypatch: pytest.MonkeyPatch, details: str, *, reject_anchor: bool = False):
    commands = []

    def run(*command):
        commands.append(command)
        if "-R" in command and reject_anchor:
            raise subprocess.CalledProcessError(3, command, stderr="requirement not satisfied")
        return subprocess.CompletedProcess(
            command, 0, stdout="", stderr=details if "-d" in command else ""
        )

    monkeypatch.setattr(signing, "run", run)
    monkeypatch.setattr(Path, "read_bytes", lambda _path: b"fake executable bytes")
    return commands


def details(cdhash: str, *, team: str = TEAM, requirement: str | None = None) -> str:
    dr = requirement or (
        f'identifier "{IDENTIFIER}" and anchor apple generic '
        f'and certificate leaf[subject.OU] = "{team}"'
    )
    return f"Identifier={IDENTIFIER}\nTeamIdentifier={team}\nCDHash={cdhash}\ndesignated => {dr}\n"


def test_code_changes_keep_team_based_identity_and_check_apple_chain(monkeypatch) -> None:
    reports = []
    for cdhash in ["1" * 40, "2" * 40]:
        commands = stub_codesign(monkeypatch, details(cdhash))
        reports.append(signing.verify(Path("helper.app"), IDENTIFIER, TEAM))
        checks = [command[command.index("-R") + 1] for command in commands if "-R" in command]
        assert len(checks) == 1
        assert "anchor apple generic" in checks[0]
        assert "1.2.840.113635.100.6.1.13" in checks[0]
        assert f'certificate leaf[subject.OU] = "{TEAM}"' in checks[0]
    assert reports[0]["cdhash"] != reports[1]["cdhash"]
    assert reports[0]["designated_requirement"] == reports[1]["designated_requirement"]
    assert all(report["keychain_identity_stable"] for report in reports)


@pytest.mark.parametrize(
    "text",
    [details("1" * 40, team="OTHER12345"), details("1" * 40, requirement='cdhash H"1111"')],
)
def test_wrong_team_or_hash_bound_identity_is_rejected(monkeypatch, text) -> None:
    stub_codesign(monkeypatch, text)
    with pytest.raises(ValueError, match="Unstable or unexpected"):
        signing.verify(Path("helper.app"), IDENTIFIER, TEAM)


def test_self_signed_certificate_cannot_masquerade_as_apple_team(monkeypatch) -> None:
    stub_codesign(monkeypatch, details("1" * 40), reject_anchor=True)
    with pytest.raises(subprocess.CalledProcessError):
        signing.verify(Path("helper.app"), IDENTIFIER, TEAM)


def test_signing_does_not_resign_pinned_nested_resources(monkeypatch) -> None:
    commands = stub_codesign(monkeypatch, details("1" * 40))
    signing.sign(Path("helper.app"), IDENTIFIER, IDENTITY, TEAM)
    command = commands[0]
    assert "--deep" not in command
    assert command[command.index("--sign") + 1] == IDENTITY
    assert "--timestamp" in command
    assert "--options" not in command
    checks = [cmd[cmd.index("-R") + 1] for cmd in commands if "-R" in cmd]
    assert len(checks) == 1
    assert checks[0].startswith("=")


def test_hardened_runtime_flag_and_developer_id_detection(monkeypatch) -> None:
    commands = stub_codesign(monkeypatch, details("1" * 40))
    signing.sign(Path("helper.app"), IDENTIFIER, IDENTITY, TEAM, hardened_runtime=True)
    command = commands[0]
    options_index = command.index("--options")
    assert command[options_index + 1] == "runtime"
    assert "--timestamp" in command

    sample_identities = (
        f'  1) {IDENTITY.upper()} "Developer ID Application: Example Corp ({TEAM})"\n'
        f'  2) {"b" * 40} "Apple Development: Example User ({TEAM})"\n'
        "     2 valid identities found\n"
    )
    monkeypatch.setattr(
        signing,
        "run",
        lambda *_cmd: subprocess.CompletedProcess(_cmd, 0, stdout=sample_identities, stderr=""),
    )
    assert signing.is_developer_id_identity(IDENTITY) is True
    assert signing.is_developer_id_identity("b" * 40) is False
    assert signing.is_developer_id_identity("-") is False


def test_unsupported_runtime_bundle_is_rejected_before_any_signature_changes(tmp_path, monkeypatch):
    (tmp_path / "Python.framework").mkdir()
    (tmp_path / "agent-quota-sidecar").write_bytes(b"\xcf\xfa\xed\xfe")
    commands = []
    monkeypatch.setattr(signing, "run", lambda *command: commands.append(command))
    with pytest.raises(ValueError, match="Nested runtime bundles"):
        signing.sign_sidecar_tree(tmp_path, "-", None)
    assert commands == []


@pytest.mark.parametrize(
    "corruption", [None, "missing-component", "contradictory-mode", "wrong-bytes"]
)
def test_provenance_binds_signing_report_to_actual_components(tmp_path, corruption):
    validate = runpy.run_path(Path(__file__).parents[1] / "tools/generate_build_provenance.py")[
        "validate_signing_audit"
    ]
    components = {}
    for name, (relative, identifier) in signing.COMPONENTS.items():
        if name == "main":
            executable = tmp_path / "Contents/MacOS/agent-quota-desktop"
        elif name == "helper":
            executable = tmp_path / relative / "Contents/MacOS/AgentQuotaNative"
        else:
            executable = tmp_path / relative
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_bytes(name.encode())
        components[name] = {
            "identifier": identifier,
            "team_id": None,
            "cdhash": "1" * 40,
            "designated_requirement": 'cdhash H"' + "1" * 40 + '"',
            "keychain_identity_stable": False,
            "executable_sha256": hashlib.sha256(name.encode()).hexdigest(),
        }
    report = {
        "schema": "agent-quota-signing-audit-v1",
        "mode": "adhoc-test-only",
        "keychain_identity_stable": False,
        "notarized": False,
        "components": components,
    }
    if corruption == "missing-component":
        del components["helper"]
    elif corruption == "contradictory-mode":
        report["keychain_identity_stable"] = True
    elif corruption == "wrong-bytes":
        components["helper"]["executable_sha256"] = "0" * 64
    if corruption:
        with pytest.raises(ValueError):
            validate(report, tmp_path)
    else:
        assert validate(report, tmp_path) is report


def test_auto_discovery_extracts_subject_ou_instead_of_cn_member_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sha_dev = "d" * 40
    sha_dist = "e" * 40

    def fake_run(*command: str, stdin_text: str | None = None) -> subprocess.CompletedProcess[str]:
        if command[:3] == ("/usr/bin/security", "find-identity", "-v"):
            out = (
                f'  1) {sha_dev.upper()} "Apple Development: dev@example.com (392AK27NA8)"\n'
                f'  2) {sha_dist.upper()} "Developer ID Application: Dev (34Y68VQZ4R)"\n'
            )
            return subprocess.CompletedProcess(command, 0, stdout=out, stderr="")
        if command[:3] == ("/usr/bin/security", "find-certificate", "-a"):
            out = (
                f"SHA-1 hash: {sha_dev.upper()}\n"
                "-----BEGIN CERTIFICATE-----\nDEV\n-----END CERTIFICATE-----\n"
                f"SHA-1 hash: {sha_dist.upper()}\n"
                "-----BEGIN CERTIFICATE-----\nDIST\n-----END CERTIFICATE-----\n"
            )
            return subprocess.CompletedProcess(command, 0, stdout=out, stderr="")
        if command[0] == "/usr/bin/openssl":
            assert stdin_text is not None
            # CN carries Member ID 392AK27NA8, whereas OU holds true Team ID 34Y68VQZ4R
            subject = (
                "subject=UID=U1,CN=Apple Development: dev@example.com (392AK27NA8),"
                "OU=34Y68VQZ4R,C=US\n"
            )
            return subprocess.CompletedProcess(command, 0, stdout=subject, stderr="")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(signing, "run", fake_run)
    identities = signing.discover_signing_identities()
    assert len(identities) == 2
    assert all(entry["team_id"] == "34Y68VQZ4R" for entry in identities)
    # Auto mode prefers Developer ID Application when same Team ID has both
    assert signing.configuration({"AQ_CODESIGN_AUTO": "1"}) == (sha_dist.upper(), "34Y68VQZ4R")
    with pytest.raises(ValueError, match="cannot be combined"):
        signing.configuration({"AQ_CODESIGN_AUTO": "1", "AQ_ALLOW_ADHOC_SIGNING": "1"})
