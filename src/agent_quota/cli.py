"""Auxiliary maintenance CLI; it does not expose credential input."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NoReturn

from agent_quota.errors import AgentQuotaError, ProviderFailure
from agent_quota.exporting import write_redacted_export
from agent_quota.model import AccountScope
from agent_quota.native_control import NativeControlPlane
from agent_quota.providers import MAX_PROVIDER_BODY_BYTES
from agent_quota.purge import plan_purge
from agent_quota.service import ApplicationService
from agent_quota.storage import Store

DEFAULT_DESKTOP_ROOT = Path.home() / "Library/Application Support/com.agentquota.desktop"


def _no_adapter(_scope: AccountScope) -> NoReturn:
    raise ProviderFailure("adapter_not_configured")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="agent-quota")
    root.add_argument(
        "--db",
        type=Path,
        default=Path.home() / "Library/Application Support/AgentQuota/agent-quota.sqlite",
    )
    root.add_argument(
        "--data-root",
        type=Path,
        default=DEFAULT_DESKTOP_ROOT,
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
    commands.add_parser("desktop-status")
    ingest = commands.add_parser("ingest-antigravity-statusline")
    ingest.add_argument("--quiet", action="store_true")
    return root


def _read_bounded_stdin(max_bytes: int = MAX_PROVIDER_BODY_BYTES) -> bytes:
    payload = sys.stdin.buffer.read(max_bytes + 1)
    if not 1 <= len(payload) <= max_bytes:
        raise ValueError("statusline payload exceeds bounds")
    return payload


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    quiet = bool(getattr(arguments, "quiet", False))
    try:
        if arguments.command == "desktop-status":
            control = NativeControlPlane(arguments.data_root.resolve())
            output: object = {
                "status": "ok",
                "accounts": control.renderer_accounts(),
                "projection": control.quota_projection("scope-all"),
            }
        elif arguments.command == "ingest-antigravity-statusline":
            control = NativeControlPlane(arguments.data_root.resolve())
            updated = control.ingest_antigravity_statusline(_read_bounded_stdin())
            output = {"status": "ok", "updated": updated}
        else:
            store = Store(arguments.db)
            try:
                service = ApplicationService(store, _no_adapter)
                if arguments.command == "init":
                    output = {"status": "ok", "schema_version": 1}
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
    except (AgentQuotaError, OSError, OverflowError, ValueError) as error:
        if not quiet:
            code = getattr(error, "code", "invalid_request")
            print(json.dumps({"status": "error", "error": code}, sort_keys=True))
        return 1
    if not quiet:
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
