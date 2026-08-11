"""Host-only native credential metadata and destructive two-phase control."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from agent_quota.filesystem import atomic_write_private, open_directory_nofollow, read_regular_at
from agent_quota.providers import PROVIDER_IDS, manifest, parse_provider_response

STATE_SCHEMA: Final = "aq-native-account-state-v1"
MAX_ACCOUNTS: Final = 64
PLAN_TTL_NS: Final = 60_000_000_000
FRESHNESS_TTL_MS: Final = 15 * 60 * 1000
UUID_PATTERN: Final = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
REFERENCE_PATTERN: Final = re.compile(rf"credential-{UUID_PATTERN}\Z")
PRINCIPAL_PATTERN: Final = re.compile(r"principal-[0-9a-f]{24}\Z")
TOKEN_PATTERN: Final = re.compile(rf"{UUID_PATTERN}\Z")
INTENTS: Final = {
    "cascade",
    "delete",
    "destructive-config-diff",
    "disable",
    "purge",
}


@dataclass(frozen=True)
class CredentialCommit:
    principal_ref: str
    old_reference: str | None


@dataclass(frozen=True)
class DestructivePlan:
    plan_id: str
    operation_intent: str
    opaque_selection_handle: str
    summary: str
    digest: str
    generation: int
    nonce: str
    expires_at_ns: int

    def host_projection(self) -> dict[str, object]:
        return {
            "plan_id": self.plan_id,
            "operation_intent": self.operation_intent,
            "summary": self.summary,
            "digest": self.digest,
            "generation": self.generation,
            "nonce": self.nonce,
        }


class NativeControlPlane:
    """Persistent redacted metadata; Keychain remains the secret authority."""

    def __init__(self, data_root: Path) -> None:
        if not data_root.is_absolute():
            raise ValueError("native data root must be absolute")
        self.data_root = data_root
        self.path = data_root / "native-accounts-v1.json"
        self._pending: dict[str, DestructivePlan] = {}
        self._used_presence_tokens: set[str] = set()
        self._ensure_root()
        self._state = self._load()

    def _ensure_root(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = open_directory_nofollow(self.data_root, require_owner=True)
        try:
            os.fchmod(descriptor, 0o700)
        finally:
            os.close(descriptor)

    @staticmethod
    def _empty_state() -> dict[str, object]:
        return {
            "schema": STATE_SCHEMA,
            "generation": 0,
            "accounts": [],
            "pending_keychain_deletions": [],
        }

    def _load(self) -> dict[str, object]:
        directory = open_directory_nofollow(
            self.data_root,
            require_owner=True,
            require_mode=0o700,
        )
        try:
            try:
                payload, metadata = read_regular_at(directory, self.path.name)
            except FileNotFoundError:
                return self._empty_state()
            except OSError as error:
                raise ValueError("native state must be a regular file") from error
        finally:
            os.close(directory)
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise ValueError("native state permissions mismatch")
        if len(payload) > 64 * 1024:
            raise ValueError("native state is oversized")
        document: object = json.loads(payload.decode("utf-8"))
        self._validate_state(document)
        return cast(dict[str, object], document)

    @staticmethod
    def _validate_state(document: object) -> None:
        if not isinstance(document, dict) or set(document) != {
            "schema",
            "generation",
            "accounts",
            "pending_keychain_deletions",
        }:
            raise ValueError("native state shape mismatch")
        if document["schema"] != STATE_SCHEMA:
            raise ValueError("native state schema mismatch")
        generation = document["generation"]
        accounts = document["accounts"]
        pending_deletions = document["pending_keychain_deletions"]
        if (
            isinstance(generation, bool)
            or not isinstance(generation, int)
            or not 0 <= generation <= 2**63 - 1
            or not isinstance(accounts, list)
            or len(accounts) > MAX_ACCOUNTS
            or not isinstance(pending_deletions, list)
            or len(pending_deletions) > MAX_ACCOUNTS * 2
        ):
            raise ValueError("native state bounds mismatch")
        seen_principals: set[str] = set()
        seen_references: set[str] = set()
        for account in accounts:
            if not isinstance(account, dict) or set(account) != {
                "credential_reference",
                "credential_type",
                "display_label",
                "generation",
                "last_error_code",
                "last_refresh_epoch_ms",
                "lifecycle",
                "principal_ref",
                "provider_id",
                "quota_projection",
            }:
                raise ValueError("native account shape mismatch")
            principal = account["principal_ref"]
            reference = account["credential_reference"]
            label = account["display_label"]
            account_generation = account["generation"]
            provider_id = account["provider_id"]
            projection = account["quota_projection"]
            last_refresh = account["last_refresh_epoch_ms"]
            last_error = account["last_error_code"]
            if (
                not isinstance(principal, str)
                or PRINCIPAL_PATTERN.fullmatch(principal) is None
                or principal in seen_principals
                or not isinstance(reference, str)
                or REFERENCE_PATTERN.fullmatch(reference) is None
                or reference in seen_references
                or not isinstance(label, str)
                or not 1 <= len(label.encode()) <= 128
                or account["lifecycle"] not in {"active", "disabled", "needs-reauth"}
                or isinstance(account_generation, bool)
                or not isinstance(account_generation, int)
                or not 1 <= account_generation <= generation
                or not isinstance(provider_id, str)
                or provider_id not in PROVIDER_IDS
                or account["credential_type"] != manifest(provider_id).credential_type
                or not isinstance(projection, list)
                or len(projection) > 256
                or isinstance(last_refresh, bool)
                or not isinstance(last_refresh, int)
                or not 0 <= last_refresh <= 2**63 - 1
                or (
                    last_error is not None
                    and (
                        not isinstance(last_error, str)
                        or last_error
                        not in {
                            "contract-error",
                            "keychain-locked",
                            "provider-unavailable",
                            "reauth-required",
                            "timeout",
                        }
                    )
                )
            ):
                raise ValueError("native account value mismatch")
            for row in projection:
                if (
                    not isinstance(row, dict)
                    or set(row) != {"capability_ref", "display_kind", "health", "value_display"}
                    or not isinstance(row["display_kind"], str)
                    or row["display_kind"] not in {"balance", "counter", "status", "window"}
                    or not isinstance(row["health"], str)
                    or row["health"] not in {"error", "incompatible", "ok", "unsupported"}
                    or any(
                        not isinstance(row[field], str) or not 1 <= len(row[field].encode()) <= 128
                        for field in ("capability_ref", "value_display")
                    )
                ):
                    raise ValueError("native quota projection mismatch")
            seen_principals.add(principal)
            seen_references.add(reference)
        if any(
            not isinstance(reference, str) or REFERENCE_PATTERN.fullmatch(reference) is None
            for reference in pending_deletions
        ) or len(set(pending_deletions)) != len(pending_deletions):
            raise ValueError("pending keychain deletion mismatch")

    def _persist(self) -> None:
        self._validate_state(self._state)
        payload = json.dumps(
            self._state,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        atomic_write_private(self.path, payload)

    @property
    def generation(self) -> int:
        value = self._state["generation"]
        assert isinstance(value, int)
        return value

    @property
    def accounts(self) -> list[dict[str, object]]:
        value = self._state["accounts"]
        assert isinstance(value, list)
        return value

    @property
    def pending_keychain_deletions(self) -> list[str]:
        value = self._state["pending_keychain_deletions"]
        assert isinstance(value, list)
        return cast(list[str], value)

    def renderer_accounts(self) -> list[dict[str, object]]:
        return [
            {
                "principal_ref": account["principal_ref"],
                "display_label": account["display_label"],
                "lifecycle": account["lifecycle"],
                **(
                    {"last_error_code": account["last_error_code"]}
                    if account["last_error_code"] is not None
                    else {}
                ),
            }
            for account in self.accounts
        ]

    def credential_reference(self, principal_ref: str) -> tuple[str, int]:
        self._validate_principal(principal_ref)
        for account in self.accounts:
            if account["principal_ref"] == principal_ref:
                reference = account["credential_reference"]
                generation = account["generation"]
                assert isinstance(reference, str)
                assert isinstance(generation, int)
                return reference, generation
        raise ValueError("unknown principal")

    def credential_context(self, principal_ref: str) -> tuple[str, int, str]:
        reference, generation = self.credential_reference(principal_ref)
        for account in self.accounts:
            if account["principal_ref"] == principal_ref:
                provider_id = account["provider_id"]
                assert isinstance(provider_id, str)
                return reference, generation, provider_id
        raise ValueError("unknown principal")

    def quota_projection(self, scope_ref: str) -> dict[str, object]:
        rows: list[dict[str, str]] = []
        refreshed: list[int] = []
        reauth_blocked = False
        for account in self.accounts:
            if scope_ref not in {"scope-all", account["principal_ref"]}:
                continue
            principal = cast(str, account["principal_ref"])
            if account["lifecycle"] == "needs-reauth" and account["quota_projection"]:
                reauth_blocked = True
            for source in cast(list[dict[str, str]], account["quota_projection"]):
                row = dict(source)
                identity = hashlib.sha256(
                    f"{principal}\0{source['capability_ref']}".encode()
                ).hexdigest()[:24]
                provider_id = cast(str, account["provider_id"])
                row["capability_ref"] = f"cap-{provider_id}-account-{identity}"
                rows.append(row)
            refreshed.append(cast(int, account["last_refresh_epoch_ms"]))
        newest = max(refreshed, default=0)
        now_ms = int(time.time() * 1000)
        return {
            "capability_rows": rows,
            "freshness": (
                "fresh"
                if rows and not reauth_blocked and 0 <= now_ms - newest <= FRESHNESS_TTL_MS
                else "stale"
            ),
            "scope_ref": scope_ref,
        }

    def commit_credential(
        self,
        *,
        purpose: str,
        credential_reference: str,
        principal_ref: str | None,
        expected_generation: int | None,
        provider_id: str = "deepseek",
    ) -> CredentialCommit:
        self._validate_reference(credential_reference)
        provider = manifest(provider_id)
        if any(
            account["credential_reference"] == credential_reference for account in self.accounts
        ):
            raise ValueError("credential reference already committed")
        if purpose == "create-credential-reference":
            if principal_ref is not None or expected_generation is not None:
                raise ValueError("create credential context mismatch")
            if len(self.accounts) >= MAX_ACCOUNTS:
                raise ValueError("native account limit reached")
            next_generation = self._next_generation()
            principal = (
                "principal-" + hashlib.sha256(credential_reference.encode()).hexdigest()[:24]
            )
            self.accounts.append(
                {
                    "principal_ref": principal,
                    "credential_reference": credential_reference,
                    "credential_type": provider.credential_type,
                    "display_label": provider.display_name,
                    "lifecycle": "active",
                    "generation": next_generation,
                    "last_error_code": None,
                    "last_refresh_epoch_ms": 0,
                    "provider_id": provider.provider_id,
                    "quota_projection": [],
                }
            )
            self._state["generation"] = next_generation
            self._persist()
            return CredentialCommit(principal, None)
        if purpose != "replace-credential-reference":
            raise ValueError("unknown credential purpose")
        if principal_ref is None or expected_generation is None:
            raise ValueError("replace credential context is missing")
        self._validate_principal(principal_ref)
        for account in self.accounts:
            if account["principal_ref"] != principal_ref:
                continue
            if account["generation"] != expected_generation:
                raise ValueError("credential generation drift")
            if account["provider_id"] != provider_id:
                raise ValueError("credential provider drift")
            old_reference = account["credential_reference"]
            next_generation = self._next_generation()
            account["credential_reference"] = credential_reference
            account["generation"] = next_generation
            account["lifecycle"] = "active"
            account["last_error_code"] = None
            account["last_refresh_epoch_ms"] = 0
            account["quota_projection"] = []
            self._queue_keychain_deletion(old_reference)
            self._state["generation"] = next_generation
            self._persist()
            assert isinstance(old_reference, str)
            return CredentialCommit(principal_ref, old_reference)
        raise ValueError("unknown principal")

    def commit_provider_response(
        self,
        *,
        principal_ref: str,
        expected_generation: int,
        provider_id: str,
        http_status: int,
        body_base64: str,
    ) -> tuple[str | None, bool]:
        self._validate_principal(principal_ref)
        if isinstance(http_status, bool) or not 100 <= http_status <= 599:
            raise ValueError("invalid provider HTTP status")
        for account in self.accounts:
            if account["principal_ref"] != principal_ref:
                continue
            if account["generation"] != expected_generation:
                raise ValueError("provider response generation drift")
            if account["provider_id"] != provider_id:
                raise ValueError("provider response identity drift")
            result = parse_provider_response(provider_id, http_status, body_base64)
            if result.ok:
                account["quota_projection"] = [dict(row) for row in result.rows]
                account["last_refresh_epoch_ms"] = int(time.time() * 1000)
            account["last_error_code"] = result.safe_error_code
            if result.safe_error_code == "reauth-required":
                account["lifecycle"] = "needs-reauth"
            elif account["lifecycle"] != "disabled":
                account["lifecycle"] = "active"
            self._persist()
            return result.safe_error_code, result.retryable
        raise ValueError("unknown principal")

    def commit_provider_failure(
        self,
        *,
        principal_ref: str,
        expected_generation: int,
        provider_id: str,
        safe_error_code: str,
    ) -> None:
        self._validate_principal(principal_ref)
        if safe_error_code not in {
            "contract-error",
            "keychain-locked",
            "provider-unavailable",
            "reauth-required",
            "timeout",
        }:
            raise ValueError("invalid provider failure")
        for account in self.accounts:
            if account["principal_ref"] != principal_ref:
                continue
            if account["generation"] != expected_generation:
                raise ValueError("provider failure generation drift")
            if account["provider_id"] != provider_id:
                raise ValueError("provider failure identity drift")
            account["last_error_code"] = safe_error_code
            if safe_error_code == "reauth-required":
                account["lifecycle"] = "needs-reauth"
            self._persist()
            return
        raise ValueError("unknown principal")

    def cleanup_pending(self) -> list[str]:
        return list(self.pending_keychain_deletions)

    def acknowledge_cleanup(self, references: list[str]) -> None:
        if not references or len(references) > MAX_ACCOUNTS * 2:
            raise ValueError("invalid cleanup acknowledgement")
        for reference in references:
            self._validate_reference(reference)
            if reference not in self.pending_keychain_deletions:
                raise ValueError("unknown cleanup reference")
        acknowledged = set(references)
        self.pending_keychain_deletions[:] = [
            reference
            for reference in self.pending_keychain_deletions
            if reference not in acknowledged
        ]
        self._persist()

    def prepare_destructive(
        self,
        *,
        operation_intent: str,
        opaque_selection_handle: str,
    ) -> DestructivePlan:
        now = time.monotonic_ns()
        self._pending = {
            plan_id: plan for plan_id, plan in self._pending.items() if plan.expires_at_ns > now
        }
        if len(self._pending) >= 8:
            raise ValueError("too many active destructive plans")
        if operation_intent not in INTENTS:
            raise ValueError("unknown destructive intent")
        if not 1 <= len(opaque_selection_handle.encode()) <= 128:
            raise ValueError("invalid selection handle")
        if operation_intent == "purge" and opaque_selection_handle != "selection-all-local-data":
            raise ValueError("purge scope mismatch")
        if operation_intent in {"delete", "disable", "cascade"}:
            self._validate_principal(opaque_selection_handle)
            if not any(
                account["principal_ref"] == opaque_selection_handle for account in self.accounts
            ):
                raise ValueError("unknown destructive selection")
        plan_id = secrets.token_hex(16)
        nonce = secrets.token_hex(16)
        generation = self.generation
        summary = self._plan_summary(operation_intent, opaque_selection_handle)
        payload = {
            "generation": generation,
            "intent": operation_intent,
            "plan_id": plan_id,
            "selection": opaque_selection_handle,
            "summary": summary,
        }
        digest = hashlib.sha256(
            b"agent-quota:native-destructive-plan:v1\0"
            + json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        plan = DestructivePlan(
            plan_id=plan_id,
            operation_intent=operation_intent,
            opaque_selection_handle=opaque_selection_handle,
            summary=summary,
            digest=digest,
            generation=generation,
            nonce=nonce,
            expires_at_ns=now + PLAN_TTL_NS,
        )
        self._pending[plan_id] = plan
        return plan

    def cancel_destructive(self, plan_id: str) -> bool:
        return self._pending.pop(plan_id, None) is not None

    def commit_destructive(
        self,
        *,
        plan_id: str,
        digest: str,
        generation: int,
        nonce: str,
        user_presence_token: str,
    ) -> tuple[str, ...]:
        if TOKEN_PATTERN.fullmatch(user_presence_token) is None:
            raise ValueError("invalid user presence token")
        if user_presence_token in self._used_presence_tokens:
            raise ValueError("user presence token replay")
        plan = self._pending.pop(plan_id, None)
        if plan is None:
            raise ValueError("unknown or consumed destructive plan")
        if time.monotonic_ns() >= plan.expires_at_ns:
            raise ValueError("destructive plan expired")
        if (
            plan.digest != digest
            or plan.generation != generation
            or plan.nonce != nonce
            or self.generation != generation
        ):
            raise ValueError("destructive plan drift")
        cleanup_references = self._apply_destructive(plan)
        if len(self._used_presence_tokens) >= 1024:
            self._used_presence_tokens.clear()
        self._used_presence_tokens.add(user_presence_token)
        return cleanup_references

    def _apply_destructive(self, plan: DestructivePlan) -> tuple[str, ...]:
        removed_references: list[str] = []
        if plan.operation_intent == "purge":
            removed_references = [
                cast(str, account["credential_reference"]) for account in self.accounts
            ]
            self.accounts.clear()
        elif plan.operation_intent in {"delete", "cascade"}:
            removed_references = [
                cast(str, account["credential_reference"])
                for account in self.accounts
                if account["principal_ref"] == plan.opaque_selection_handle
            ]
            self.accounts[:] = [
                account
                for account in self.accounts
                if account["principal_ref"] != plan.opaque_selection_handle
            ]
        elif plan.operation_intent == "disable":
            for account in self.accounts:
                if account["principal_ref"] == plan.opaque_selection_handle:
                    account["lifecycle"] = "disabled"
        elif plan.operation_intent != "destructive-config-diff":
            raise ValueError("unknown destructive intent")
        for reference in removed_references:
            self._queue_keychain_deletion(reference)
        self._state["generation"] = self._next_generation()
        self._persist()
        return tuple(removed_references)

    def _plan_summary(self, operation_intent: str, selection: str) -> str:
        if operation_intent == "purge":
            return f"清理 {len(self.accounts)} 个本机凭据引用及全部脱敏账户元数据"
        if operation_intent == "destructive-config-diff":
            return "应用需要原生确认的破坏性配置变更"
        return f"{operation_intent} 本机账户 {selection}"

    def _next_generation(self) -> int:
        if self.generation >= 2**63 - 1:
            raise OverflowError("native state generation overflow")
        return self.generation + 1

    def _queue_keychain_deletion(self, reference: object) -> None:
        if not isinstance(reference, str):
            raise ValueError("invalid cleanup reference")
        self._validate_reference(reference)
        if reference not in self.pending_keychain_deletions:
            if len(self.pending_keychain_deletions) >= MAX_ACCOUNTS * 2:
                raise ValueError("pending cleanup limit reached")
            self.pending_keychain_deletions.append(reference)

    @staticmethod
    def _validate_reference(value: str) -> None:
        if REFERENCE_PATTERN.fullmatch(value) is None:
            raise ValueError("invalid credential reference")

    @staticmethod
    def _validate_principal(value: str) -> None:
        if PRINCIPAL_PATTERN.fullmatch(value) is None:
            raise ValueError("invalid principal reference")
