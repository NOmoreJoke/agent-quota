"""Auxiliary maintenance CLI; it does not expose credential input."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shlex
import shutil
import stat
import sys
from pathlib import Path
from typing import NoReturn

from agent_quota.errors import AgentQuotaError, ProviderFailure
from agent_quota.exporting import write_redacted_export
from agent_quota.filesystem import open_directory_nofollow, read_regular_at
from agent_quota.model import AccountScope
from agent_quota.native_control import NativeControlPlane
from agent_quota.providers import MAX_PROVIDER_BODY_BYTES
from agent_quota.purge import plan_purge
from agent_quota.service import ApplicationService
from agent_quota.storage import Store

DEFAULT_DESKTOP_ROOT = Path.home() / "Library/Application Support/com.agentquota.desktop"
DEFAULT_ANTIGRAVITY_SETTINGS = Path.home() / ".gemini/antigravity-cli/settings.json"
MAX_SETTINGS_BYTES = 256 * 1024


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
    ingest_mode = ingest.add_mutually_exclusive_group()
    ingest_mode.add_argument("--quiet", action="store_true")
    ingest_mode.add_argument("--render-statusline", action="store_true")
    setup_ag = commands.add_parser("setup-antigravity")
    setup_ag.add_argument(
        "--settings-path",
        type=Path,
        default=DEFAULT_ANTIGRAVITY_SETTINGS,
    )
    setup_action = setup_ag.add_mutually_exclusive_group()
    setup_action.add_argument("--check", action="store_true")
    setup_action.add_argument("--uninstall", action="store_true")
    setup_ag.add_argument("--quiet-hook", action="store_true")
    setup_ag.add_argument("--force", action="store_true")
    return root


def _read_bounded_stdin(max_bytes: int = MAX_PROVIDER_BODY_BYTES) -> bytes:
    payload = sys.stdin.buffer.read(max_bytes + 1)
    if not 1 <= len(payload) <= max_bytes:
        raise ValueError("statusline payload exceeds bounds")
    return payload


def _is_managed_statusline(block: object) -> bool:
    return (
        isinstance(block, dict)
        and isinstance(block.get("command"), str)
        and "ingest-antigravity-statusline" in block["command"]
    )


def _build_antigravity_hook_command(*, data_root: Path, quiet_hook: bool) -> str:
    if getattr(sys, "frozen", False):
        prefix = f"{shlex.quote(str(Path(sys.executable).resolve()))} cli"
    else:
        argv0 = Path(sys.argv[0]) if sys.argv and sys.argv[0] else None
        if argv0 is not None and argv0.name == "agent-quota" and argv0.exists():
            prefix = shlex.quote(str(argv0.resolve()))
        elif (found := shutil.which("agent-quota")) is not None:
            prefix = shlex.quote(str(Path(found).resolve()))
        else:
            prefix = f"{shlex.quote(str(Path(sys.executable).resolve()))} -m agent_quota.cli"
    root_arg = ""
    if data_root.resolve() != DEFAULT_DESKTOP_ROOT.resolve():
        root_arg = f" --data-root {shlex.quote(str(data_root.resolve()))}"
    mode_flag = "--quiet" if quiet_hook else "--render-statusline"
    return f"{prefix}{root_arg} ingest-antigravity-statusline {mode_flag}"


def _configure_antigravity_settings(
    settings_path: Path,
    *,
    data_root: Path,
    check_only: bool,
    uninstall: bool,
    quiet_hook: bool,
    force: bool,
) -> dict[str, object]:
    expanded = settings_path.expanduser()
    if expanded.is_symlink():
        raise ValueError("settings_symlink_rejected")
    parent_candidate = expanded.parent if expanded.is_absolute() else (Path.cwd() / expanded.parent)
    if parent_candidate.is_symlink():
        raise ValueError("settings_symlink_rejected")
    if not check_only and not parent_candidate.exists():
        parent_candidate.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not parent_candidate.exists():
        return {
            "configured": False,
            "settings_path": str(parent_candidate / expanded.name),
            "status": "ok",
        }
    resolved_parent = parent_candidate.resolve(strict=True)
    target = resolved_parent / expanded.name
    directory = open_directory_nofollow(resolved_parent, require_owner=True)
    descriptor = -1
    try:
        dir_meta = os.fstat(directory)
        if stat.S_IMODE(dir_meta.st_mode) & 0o022:
            raise ValueError("settings_directory_unsafe")
        try:
            raw, _ = read_regular_at(directory, target.name, max_bytes=MAX_SETTINGS_BYTES)
            loaded = json.loads(raw.decode("utf-8"))
        except FileNotFoundError:
            loaded = {}
        except UnicodeDecodeError as error:
            raise ValueError("settings_invalid_json") from error
        except json.JSONDecodeError as error:
            raise ValueError("settings_invalid_json") from error
        if not isinstance(loaded, dict):
            raise ValueError("settings_root_not_object")

        existing = loaded.get("statusLine")
        managed = _is_managed_statusline(existing)
        if check_only:
            return {
                "configured": managed,
                "has_foreign_statusline": existing is not None and not managed,
                "settings_path": str(target),
                "status": "ok",
            }
        if uninstall:
            if existing is not None and not managed and not force:
                raise ValueError("existing_statusline_conflict")
            updated_doc = {key: value for key, value in loaded.items() if key != "statusLine"}
            action = "removed" if managed or (existing is not None and force) else "noop"
        else:
            if existing is not None and not managed and not force:
                raise ValueError("existing_statusline_conflict")
            hook_command = _build_antigravity_hook_command(
                data_root=data_root, quiet_hook=quiet_hook
            )
            updated_doc = dict(loaded)
            updated_doc["statusLine"] = {
                "type": "command",
                "command": hook_command,
            }
            action = "configured"

        serialized = (
            json.dumps(updated_doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        if len(serialized) > MAX_SETTINGS_BYTES:
            raise ValueError("settings_payload_exceeds_bounds")
        temporary = f".{target.name}.{secrets.token_hex(8)}.tmp"
        descriptor = os.open(
            temporary,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=directory,
        )
        written = 0
        while written < len(serialized):
            written += os.write(descriptor, serialized[written:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, target.name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
        return {
            "action": action,
            "configured": not uninstall,
            "settings_path": str(target),
            "status": "ok",
        }
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(directory)


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    quiet = bool(getattr(arguments, "quiet", False))
    render_statusline = bool(getattr(arguments, "render_statusline", False))
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
            if render_statusline:
                summary = control.antigravity_statusline_summary()
                if summary:
                    print(summary)
                return 0
            output = {"status": "ok", "updated": updated}
        elif arguments.command == "setup-antigravity":
            output = _configure_antigravity_settings(
                arguments.settings_path,
                data_root=arguments.data_root.resolve(),
                check_only=bool(arguments.check),
                uninstall=bool(arguments.uninstall),
                quiet_hook=bool(arguments.quiet_hook),
                force=bool(arguments.force),
            )
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
        if not quiet and not render_statusline:
            raw_code = getattr(error, "code", None)
            safe_prefixes = ("existing_", "settings_")
            code = (
                raw_code
                if isinstance(raw_code, str)
                else (
                    str(error)
                    if isinstance(error, ValueError) and str(error).startswith(safe_prefixes)
                    else "invalid_request"
                )
            )
            print(json.dumps({"status": "error", "error": code}, sort_keys=True))
        return 1
    if not quiet:
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
