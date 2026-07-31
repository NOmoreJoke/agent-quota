"""Versioned application service shared by future desktop host and CLI."""

from __future__ import annotations

import contextlib
import hashlib
import json
import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from agent_quota.adapters import Adapter, AdapterObservation, FetchContext
from agent_quota.errors import (
    ContractViolation,
    FenceConflict,
    NotAuthorized,
    OutcomeUnknown,
    ProviderFailure,
    RefreshInProgress,
)
from agent_quota.model import AccountScope, CapabilitySnapshot, Freshness, Health
from agent_quota.storage import Lease, Store


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(b"agent-quota:request:v1\0" + encoded).hexdigest()


@dataclass(frozen=True)
class RefreshResult:
    state: str
    snapshot: CapabilitySnapshot | None
    error_code: str | None = None


AdapterResolver = Callable[[AccountScope], Adapter]


class ApplicationService:
    version = "v1"

    def __init__(self, store: Store, adapter_resolver: AdapterResolver) -> None:
        self.store = store
        self.adapter_resolver = adapter_resolver
        self.store.recover_incomplete_refreshes()

    def accounts(self) -> list[dict[str, object]]:
        return self.store.list_accounts()

    def status(self, scope: AccountScope) -> CapabilitySnapshot | None:
        self._authorize(scope)
        return self.store.latest_snapshot(scope)

    def refresh(
        self,
        scope: AccountScope,
        *,
        idempotency_key: str,
        remaining_budget_ns: int = 9_000_000_000,
    ) -> RefreshResult:
        self._authorize(scope)
        if not idempotency_key or len(idempotency_key.encode()) > 128:
            raise ContractViolation("invalid idempotency key")
        if not 1 <= remaining_budget_ns <= 9_000_000_000:
            raise ContractViolation("remaining budget is out of bounds")
        existing = self.store.refresh_row(idempotency_key)
        if existing is not None:
            return self._existing_refresh(existing, scope)

        owner = uuid.uuid4().hex
        lease = self.store.acquire_lease(
            f"refresh:{scope.opaque_ref}",
            owner,
            remaining_budget_ns + 1_000_000_000,
        )
        self.store.start_refresh(idempotency_key, scope, lease)
        request_digest = _digest(
            {
                "scope_ref": scope.opaque_ref,
                "idempotency_key": idempotency_key,
                "fence": lease.fence,
            }
        )
        identity_evidence = _digest({"principal_id": scope.principal_id, "fence": lease.fence})
        deadline_ns = self.store.clock.monotonic_ns() + remaining_budget_ns
        if deadline_ns > 2**63 - 1:
            self.store.finish_refresh(
                idempotency_key,
                "failed",
                lease=lease,
                error_code="deadline_overflow",
            )
            raise ContractViolation("deadline overflow")
        context = FetchContext(
            scope=scope,
            identity_evidence=identity_evidence,
            request_digest=request_digest,
            deadline_ns=deadline_ns,
        )
        try:
            adapter = self.adapter_resolver(scope)
            if self.store.clock.monotonic_ns() >= deadline_ns:
                self.store.finish_refresh(
                    idempotency_key,
                    "failed",
                    lease=lease,
                    error_code="deadline_expired_before_dispatch",
                )
                raise ContractViolation("deadline expired before dispatch")
            observation = adapter.fetch(context)
            self._validate_observation(context, observation)
            snapshot = CapabilitySnapshot(
                scope=scope,
                kind=observation.kind,
                unit=observation.unit,
                used=observation.used,
                limit=observation.limit,
                remaining=observation.remaining,
                reset_at_ns=observation.reset_at_ns,
                observed_at_ns=self.store.clock.wall_ns(),
                freshness=Freshness.FRESH,
                health=Health.OK,
            )
            self.store.complete_refresh_success(idempotency_key, snapshot, lease)
            return RefreshResult("succeeded", snapshot)
        except TimeoutError:
            self._finish_or_unknown(
                idempotency_key,
                "outcome_unknown",
                lease=lease,
                error_code="timeout_after_dispatch",
            )
            raise OutcomeUnknown(idempotency_key) from None
        except ProviderFailure as error:
            self._finish_or_unknown(
                idempotency_key,
                "failed",
                lease=lease,
                error_code=error.code,
            )
            raise
        except (ContractViolation, TypeError, ValueError) as error:
            refresh = self.store.refresh_row(idempotency_key)
            if refresh is None:
                raise ContractViolation("refresh state disappeared") from error
            if refresh["state"] == "running":
                self._finish_or_unknown(
                    idempotency_key,
                    "failed",
                    lease=lease,
                    error_code="adapter_contract_violation",
                )
            raise ContractViolation(str(error)) from error
        except Exception as error:
            self._finish_or_unknown(
                idempotency_key,
                "outcome_unknown",
                lease=lease,
                error_code="unexpected_after_dispatch",
            )
            raise OutcomeUnknown(idempotency_key) from error
        finally:
            # Cleanup cannot replace the already determined public result.
            with contextlib.suppress(Exception):
                self.store.release_lease(lease)

    def _finish_or_unknown(
        self,
        key: str,
        state: str,
        *,
        lease: Lease,
        error_code: str,
    ) -> None:
        try:
            self.store.finish_refresh(
                key,
                state,
                lease=lease,
                error_code=error_code,
            )
        except FenceConflict as error:
            self.store.recover_incomplete_refreshes()
            raise OutcomeUnknown(key) from error

    def _authorize(self, scope: AccountScope) -> None:
        if not self.store.authorize(scope):
            raise NotAuthorized(scope.opaque_ref)

    def _existing_refresh(
        self,
        row: sqlite3.Row,
        scope: AccountScope,
    ) -> RefreshResult:
        if row["scope_ref"] != scope.opaque_ref:
            raise ContractViolation("idempotency key scope mismatch")
        state = row["state"]
        if state == "succeeded":
            snapshot_id = row["snapshot_id"]
            snapshot = self.store.snapshot_by_id(snapshot_id, scope)
            if snapshot is None:
                raise ContractViolation("idempotency snapshot is unavailable")
            return RefreshResult(state, snapshot)
        if state == "running":
            raise RefreshInProgress(scope.opaque_ref)
        if state == "outcome_unknown":
            raise OutcomeUnknown(scope.opaque_ref)
        if state == "failed":
            raise ProviderFailure(row["error_code"] or "provider_failed")
        raise ContractViolation("unknown persisted refresh state")

    @staticmethod
    def _validate_observation(
        context: FetchContext,
        observation: AdapterObservation,
    ) -> None:
        required = (
            "scope",
            "identity_evidence",
            "request_digest",
            "kind",
            "unit",
            "used",
            "limit",
            "remaining",
            "reset_at_ns",
        )
        if any(not hasattr(observation, field) for field in required):
            raise ContractViolation("adapter observation field closure mismatch")
        if observation.scope != context.scope:
            raise ContractViolation("adapter scope mismatch")
        if observation.identity_evidence != context.identity_evidence:
            raise ContractViolation("identity evidence mismatch")
        if observation.request_digest != context.request_digest:
            raise ContractViolation("request digest mismatch")
