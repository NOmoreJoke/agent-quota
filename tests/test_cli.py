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
