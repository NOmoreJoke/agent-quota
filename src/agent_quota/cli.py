"""Auxiliary maintenance CLI; it does not expose credential input."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import NoReturn

from agent_quota.errors import AgentQuotaError, ProviderFailure
from agent_quota.exporting import write_redacted_export
from agent_quota.model import AccountScope
from agent_quota.purge import plan_purge
from agent_quota.service import ApplicationService
from agent_quota.storage import Store


def _no_adapter(_scope: AccountScope) -> NoReturn:
    raise ProviderFailure("adapter_not_configured")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="agent-quota")
    root.add_argument(
        "--db",
        type=Path,
        default=Path.home() / "Library/Application Support/AgentQuota/agent-quota.sqlite",
    )
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    commands.add_parser("accounts")
    status = commands.add_parser("status")
    status.add_argument("scope_ref")
    export = commands.add_parser("export")
    export.add_argument("destination", type=Path)
    purge = commands.add_parser("purge-plan")
    purge.add_argument("--generation", type=int, default=1)
    return root


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        store = Store(arguments.db)
        try:
            service = ApplicationService(store, _no_adapter)
            if arguments.command == "init":
                output: object = {"status": "ok", "schema_version": 1}
            elif arguments.command == "accounts":
                output = {"status": "ok", "accounts": service.accounts()}
            elif arguments.command == "status":
                scope = AccountScope.parse(arguments.scope_ref)
                snapshot = service.status(scope)
                output = {
                    "status": "ok",
                    "projection": snapshot.renderer_projection() if snapshot else None,
                }
            elif arguments.command == "export":
                write_redacted_export(store, arguments.destination)
                output = {"status": "ok", "export": "created"}
            elif arguments.command == "purge-plan":
                plan = plan_purge(arguments.db.parent, arguments.generation)
                output = {"status": "ok", "plan": plan.renderer_projection()}
            else:
                raise RuntimeError("unreachable command")
        finally:
            store.close()
    except (AgentQuotaError, OSError, ValueError) as error:
        code = getattr(error, "code", "invalid_request")
        print(json.dumps({"status": "error", "error": code}, sort_keys=True))
        return 1
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
