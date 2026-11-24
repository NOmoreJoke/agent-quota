from __future__ import annotations

import json
from pathlib import Path

from agent_quota.cli import main
from agent_quota.model import AccountScope, CapabilityKind
from agent_quota.storage import Store


def invoke(capsys: object, arguments: list[str]) -> tuple[int, dict[str, object]]:
    code = main(arguments)
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    return code, json.loads(output)


def test_cli_init_accounts_status_export(
    tmp_path: Path,
    capsys: object,
) -> None:
    database = tmp_path / "data" / "state.sqlite"
    prefix = ["--db", str(database)]
    assert invoke(capsys, [*prefix, "init"])[0] == 0
    code, accounts = invoke(capsys, [*prefix, "accounts"])
    assert code == 0 and accounts["accounts"] == []
    store = Store(database)
    store.seed_scope(
        AccountScope("openrouter", "api-key-personal", "current-key"),
        provider="OpenRouter",
        principal_label="OpenRouter",
        subject_label="API Key personal",
        kind=CapabilityKind.WINDOW,
        unit="requests",
    )
    store.close()
    code, status = invoke(
        capsys,
        [*prefix, "status", "openrouter:api-key-personal:current-key"],
    )
    assert code == 0 and status["projection"] is None
    destination = tmp_path / "redacted.json"
    code, exported = invoke(capsys, [*prefix, "export", str(destination)])
    assert code == 0 and exported["export"] == "created"
    assert destination.exists()


def test_cli_invalid_scope_returns_safe_error(tmp_path: Path, capsys: object) -> None:
    database = tmp_path / "data" / "state.sqlite"
    code, output = invoke(
        capsys,
        ["--db", str(database), "status", "forged"],
    )
    assert code == 1
    assert output == {"status": "error", "error": "invalid_request"}


def test_cli_ingest_antigravity_and_desktop_status(
    tmp_path: Path,
    capsys: object,
    monkeypatch: object,
) -> None:
    import io

    data_root = tmp_path / "desktop"
    payload = json.dumps(
        {
            "product": "antigravity",
            "plan_tier": "Pro",
            "email": "hidden@example.com",
            "quota": {"gemini-weekly": {"remaining_fraction": 0.75}},
        }
    ).encode()
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "sys.stdin",
        type("FakeStdin", (), {"buffer": io.BytesIO(payload)})(),
    )
    code, ingested = invoke(
        capsys,
        ["--data-root", str(data_root), "ingest-antigravity-statusline"],
    )
    assert code == 0 and ingested == {"status": "ok", "updated": True}

    code, status = invoke(capsys, ["--data-root", str(data_root), "desktop-status"])
    assert code == 0
    assert len(status["accounts"]) == 1  # type: ignore[arg-type]
    assert "hidden@example.com" not in json.dumps(status)

    monkeypatch.setattr(  # type: ignore[attr-defined]
        "sys.stdin",
        type("FakeStdin", (), {"buffer": io.BytesIO(payload)})(),
    )
    quiet_code = main(["--data-root", str(data_root), "ingest-antigravity-statusline", "--quiet"])
    assert quiet_code == 0
    assert capsys.readouterr().out == ""  # type: ignore[attr-defined]

    monkeypatch.setattr(  # type: ignore[attr-defined]
        "sys.stdin",
        type("FakeStdin", (), {"buffer": io.BytesIO(payload)})(),
    )
    render_code = main(
        ["--data-root", str(data_root), "ingest-antigravity-statusline", "--render-statusline"]
    )
    rendered = capsys.readouterr().out.strip()  # type: ignore[attr-defined]
    assert render_code == 0
    assert "Antigravity (Pro)" in rendered
    assert "75%" in rendered
    assert "hidden@example.com" not in rendered

    monkeypatch.setattr(  # type: ignore[attr-defined]
        "sys.stdin",
        type("FakeStdin", (), {"buffer": io.BytesIO(b"not-json")})(),
    )
    bad_render_code = main(
        ["--data-root", str(data_root), "ingest-antigravity-statusline", "--render-statusline"]
    )
    assert bad_render_code == 1
    assert capsys.readouterr().out == ""  # type: ignore[attr-defined]


def test_cli_setup_antigravity_preserves_settings_and_guards_conflicts(
    tmp_path: Path,
    capsys: object,
) -> None:
    data_root = tmp_path / "desktop"
    settings_dir = tmp_path / "ag-config"
    settings_dir.mkdir(mode=0o755)
    settings_path = settings_dir / "settings.json"

    code, initial = invoke(
        capsys,
        [
            "--data-root",
            str(data_root),
            "setup-antigravity",
            "--settings-path",
            str(settings_path),
            "--check",
        ],
    )
    assert code == 0 and initial["configured"] is False

    settings_path.write_text(
        json.dumps({"theme": "dark", "statusLine": {"command": "echo custom"}}),
        encoding="utf-8",
    )
    conflict_code, conflict = invoke(
        capsys,
        ["--data-root", str(data_root), "setup-antigravity", "--settings-path", str(settings_path)],
    )
    assert conflict_code == 1
    assert conflict == {"status": "error", "error": "existing_statusline_conflict"}

    force_code, forced = invoke(
        capsys,
        [
            "--data-root",
            str(data_root),
            "setup-antigravity",
            "--settings-path",
            str(settings_path),
            "--force",
        ],
    )
    assert force_code == 0 and forced["configured"] is True
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["theme"] == "dark"
    assert "ingest-antigravity-statusline --render-statusline" in saved["statusLine"]["command"]

    check_code, checked = invoke(
        capsys,
        [
            "--data-root",
            str(data_root),
            "setup-antigravity",
            "--settings-path",
            str(settings_path),
            "--check",
        ],
    )
    assert check_code == 0 and checked["configured"] is True

    uninstall_code, uninstalled = invoke(
        capsys,
        [
            "--data-root",
            str(data_root),
            "setup-antigravity",
            "--settings-path",
            str(settings_path),
            "--uninstall",
        ],
    )
    assert uninstall_code == 0 and uninstalled["configured"] is False
    after_uninstall = json.loads(settings_path.read_text(encoding="utf-8"))
    assert after_uninstall == {"theme": "dark"}

    symlink_path = tmp_path / "symlink-settings.json"
    symlink_path.symlink_to(settings_path)
    sym_code, sym_out = invoke(
        capsys,
        ["--data-root", str(data_root), "setup-antigravity", "--settings-path", str(symlink_path)],
    )
    assert sym_code == 1 and sym_out == {"status": "error", "error": "settings_symlink_rejected"}


def test_sidecar_cli_bridge_and_local_bridge_destructive_cleanup(
    tmp_path: Path,
    capsys: object,
    monkeypatch: object,
) -> None:
    import uuid

    from agent_quota import sidecar
    from agent_quota.native_control import NativeControlPlane

    data_root = (tmp_path / "sidecar-cli").resolve()
    monkeypatch.delenv("AQ_SESSION_SECRET_FD", raising=False)  # type: ignore[attr-defined]
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "sys.argv",
        ["agent-quota-sidecar", "cli", "--data-root", str(data_root), "desktop-status"],
    )
    rc = sidecar.main()
    out = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert rc == 0 and out["accounts"] == []

    # When AQ_SESSION_SECRET_FD is set by the host, "cli" mode MUST fail closed with exit 64
    monkeypatch.setenv("AQ_SESSION_SECRET_FD", "999")  # type: ignore[attr-defined]
    assert sidecar.main() == 64

    # Deleting or purging a keyless local_cli_bridge account never queues Keychain deletions
    control = NativeControlPlane(data_root)
    control.ingest_antigravity_statusline(
        json.dumps({"quota": {"gemini-5h": {"remaining_fraction": 0.5}}}).encode(),
        now_ms=1_000,
    )
    principal = str(control.renderer_accounts()[0]["principal_ref"])
    plan = control.prepare_destructive(
        operation_intent="delete",
        opaque_selection_handle=principal,
    )
    removed = control.commit_destructive(
        plan_id=plan.plan_id,
        digest=plan.digest,
        generation=plan.generation,
        nonce=plan.nonce,
        user_presence_token=str(uuid.uuid4()),
    )
    assert removed == ()
    assert control.cleanup_pending() == []
    assert control.renderer_accounts() == []


def test_cli_purge_plan_and_antigravity_settings_validation_edges(
    tmp_path: Path,
    capsys: object,
    monkeypatch: object,
) -> None:
    import io
    import os

    database = tmp_path / "data" / "state.sqlite"
    assert invoke(capsys, ["--db", str(database), "init"])[0] == 0
    code, purge = invoke(capsys, ["--db", str(database), "purge-plan", "--generation", "2"])
    assert code == 0 and purge["status"] == "ok"

    # Empty stdin fails closed
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "sys.stdin",
        type("FakeStdin", (), {"buffer": io.BytesIO(b"")})(),
    )
    assert (
        invoke(capsys, ["--data-root", str(tmp_path / "ag"), "ingest-antigravity-statusline"])[0]
        == 1
    )

    # Non-existent parent with --check returns configured=False without creating dirs
    missing_parent = tmp_path / "missing-dir" / "settings.json"
    chk_code, chk_out = invoke(
        capsys,
        ["setup-antigravity", "--settings-path", str(missing_parent), "--check"],
    )
    assert chk_code == 0 and chk_out["configured"] is False
    assert not missing_parent.parent.exists()

    # Invalid JSON / non-object JSON / world-writable dir fail closed cleanly
    unsafe_dir = tmp_path / "unsafe-dir"
    unsafe_dir.mkdir()
    os.chmod(unsafe_dir, 0o777)
    bad_dir_code, bad_dir_out = invoke(
        capsys,
        ["setup-antigravity", "--settings-path", str(unsafe_dir / "settings.json")],
    )
    assert bad_dir_code == 1 and bad_dir_out == {
        "status": "error",
        "error": "settings_directory_unsafe",
    }

    safe_dir = tmp_path / "safe-dir"
    safe_dir.mkdir(mode=0o700)
    bad_json = safe_dir / "settings.json"
    bad_json.write_text("{broken", encoding="utf-8")
    bad_json_code, bad_json_out = invoke(
        capsys,
        ["setup-antigravity", "--settings-path", str(bad_json)],
    )
    assert bad_json_code == 1 and bad_json_out == {
        "status": "error",
        "error": "settings_invalid_json",
    }

    bad_json.write_text("[]", encoding="utf-8")
    root_code, root_out = invoke(
        capsys,
        ["setup-antigravity", "--settings-path", str(bad_json)],
    )
    assert root_code == 1 and root_out == {"status": "error", "error": "settings_root_not_object"}

    bad_json.write_text(json.dumps({"statusLine": {"command": "echo other"}}), encoding="utf-8")
    uninst_code, uninst_out = invoke(
        capsys,
        ["setup-antigravity", "--settings-path", str(bad_json), "--uninstall"],
    )
    assert uninst_code == 1 and uninst_out == {
        "status": "error",
        "error": "existing_statusline_conflict",
    }
