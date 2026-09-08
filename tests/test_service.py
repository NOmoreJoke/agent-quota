from __future__ import annotations

import pytest

from agent_quota.errors import (
    ContractViolation,
    NotAuthorized,
    OutcomeUnknown,
    ProviderFailure,
)
from agent_quota.model import AccountScope, CapabilityKind
from agent_quota.service import ApplicationService
from agent_quota.storage import Store
from agent_quota_testkit import FakeAdapter, Scenario


def service(store: Store, adapter: FakeAdapter) -> ApplicationService:
    return ApplicationService(store, lambda _scope: adapter)


def test_refresh_success_and_idempotent_replay(
    store: Store,
    scope: AccountScope,
) -> None:
    adapter = FakeAdapter()
    app = service(store, adapter)
    first = app.refresh(scope, idempotency_key="request-1")
    second = app.refresh(scope, idempotency_key="request-1")
    assert first.state == second.state == "succeeded"
    assert first.snapshot == second.snapshot
    assert adapter.calls == 1


def test_replay_returns_exact_request_snapshot(
    store: Store,
    scope: AccountScope,
) -> None:
    first_adapter = FakeAdapter()
    first = service(store, first_adapter).refresh(scope, idempotency_key="first")
    second = service(store, FakeAdapter(Scenario.NULL_UNLIMITED)).refresh(
        scope,
        idempotency_key="second",
    )
    replay = service(store, FakeAdapter()).refresh(scope, idempotency_key="first")
    assert first.snapshot is not None and first.snapshot.limit == 100
    assert second.snapshot is not None and second.snapshot.limit is None
    assert replay.snapshot == first.snapshot


def test_idempotency_key_is_bound_to_scope(
    store: Store,
    scope: AccountScope,
) -> None:
    adapter = FakeAdapter()
    app = service(store, adapter)
    app.refresh(scope, idempotency_key="shared")
    other = AccountScope("openrouter", "team", "current-key-team")
    store.seed_scope(
        other,
        provider="OpenRouter",
        principal_label="OpenRouter",
        subject_label="API Key 团队",
        kind=CapabilityKind.WINDOW,
        unit="requests",
    )
    with pytest.raises(ContractViolation):
        app.refresh(other, idempotency_key="shared")
    assert adapter.calls == 1


def test_timeout_becomes_outcome_unknown_without_replay(
    store: Store,
    scope: AccountScope,
) -> None:
    adapter = FakeAdapter(Scenario.TIMEOUT)
    app = service(store, adapter)
    with pytest.raises(OutcomeUnknown):
        app.refresh(scope, idempotency_key="request-timeout")
    with pytest.raises(OutcomeUnknown):
        app.refresh(scope, idempotency_key="request-timeout")
    assert adapter.calls == 1


def test_expired_running_refresh_recovers_to_outcome_unknown(
    store: Store,
    scope: AccountScope,
) -> None:
    lease = store.acquire_lease(f"refresh:{scope.opaque_ref}", "crashed", 10)
    store.start_refresh("crashed-request", scope, lease)
    store.clock.mono += 11  # type: ignore[attr-defined]
    adapter = FakeAdapter()
    app = service(store, adapter)
    with pytest.raises(OutcomeUnknown):
        app.refresh(scope, idempotency_key="crashed-request")
    assert adapter.calls == 0


def test_unexpected_adapter_error_is_outcome_unknown(
    store: Store,
    scope: AccountScope,
) -> None:
    class BrokenAdapter:
        calls = 0

        def fetch(self, _context: object) -> object:
            self.calls += 1
            raise RuntimeError("unexpected")

    adapter = BrokenAdapter()
    app = ApplicationService(store, lambda _scope: adapter)  # type: ignore[arg-type]
    with pytest.raises(OutcomeUnknown):
        app.refresh(scope, idempotency_key="unexpected")
    with pytest.raises(OutcomeUnknown):
        app.refresh(scope, idempotency_key="unexpected")
    assert adapter.calls == 1


def test_expired_fence_after_dispatch_does_not_publish_snapshot(
    store: Store,
    scope: AccountScope,
) -> None:
    class SlowAdapter(FakeAdapter):
        def fetch(self, context: object) -> object:
            observation = super().fetch(context)  # type: ignore[arg-type]
            store.clock.mono += 10_000_000_001  # type: ignore[attr-defined]
            return observation

    adapter = SlowAdapter()
    app = service(store, adapter)
    with pytest.raises(OutcomeUnknown):
        app.refresh(scope, idempotency_key="expired-after-dispatch")
    assert store.latest_snapshot(scope) is None
    row = store.refresh_row("expired-after-dispatch")
    assert row is not None and row["state"] == "outcome_unknown"


def test_lease_cleanup_failure_does_not_replace_success(
    store: Store,
    scope: AccountScope,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_cleanup(_lease: object) -> bool:
        raise RuntimeError("cleanup failed")

    monkeypatch.setattr(store, "release_lease", fail_cleanup)
    result = service(store, FakeAdapter()).refresh(scope, idempotency_key="cleanup-failure")
    assert result.state == "succeeded"


@pytest.mark.parametrize(
    ("scenario", "code"),
    [
        (Scenario.AUTH_401, "auth_error"),
        (Scenario.AUTH_403, "not_authorized"),
        (Scenario.RATE_429, "rate_limited"),
        (Scenario.SERVER_5XX, "provider_unavailable"),
    ],
)
def test_provider_failure_is_terminal_for_same_key(
    store: Store,
    scope: AccountScope,
    scenario: Scenario,
    code: str,
) -> None:
    adapter = FakeAdapter(scenario)
    app = service(store, adapter)
    for _ in range(2):
        with pytest.raises(ProviderFailure) as failure:
            app.refresh(scope, idempotency_key=f"request-{scenario}")
        assert failure.value.code == code
    assert adapter.calls == 1


@pytest.mark.parametrize(
    "scenario",
    [
        Scenario.MISSING,
        Scenario.WRONG_TYPE,
        Scenario.OVERSIZE,
        Scenario.SCOPE_MISMATCH,
        Scenario.IDENTITY_MISMATCH,
        Scenario.DIGEST_MISMATCH,
    ],
)
def test_adversarial_observation_rejected(
    store: Store,
    scope: AccountScope,
    scenario: Scenario,
) -> None:
    app = service(store, FakeAdapter(scenario))
    with pytest.raises(ContractViolation):
        app.refresh(scope, idempotency_key=f"request-{scenario}")


def test_unlimited_observation_is_accepted(store: Store, scope: AccountScope) -> None:
    result = service(store, FakeAdapter(Scenario.NULL_UNLIMITED)).refresh(
        scope,
        idempotency_key="request-unlimited",
    )
    assert result.snapshot is not None
    assert result.snapshot.limit is result.snapshot.remaining is None


def test_authorization_precedes_adapter(store: Store) -> None:
    adapter = FakeAdapter()
    app = service(store, adapter)
    with pytest.raises(NotAuthorized):
        app.refresh(
            AccountScope("unknown", "unknown", "unknown"),
            idempotency_key="forged",
        )
    assert adapter.calls == 0


@pytest.mark.parametrize("budget", [0, -1, 9_000_000_001])
def test_budget_bounds_rejected(
    store: Store,
    scope: AccountScope,
    budget: int,
) -> None:
    adapter = FakeAdapter()
    with pytest.raises(ContractViolation):
        service(store, adapter).refresh(
            scope,
            idempotency_key="budget",
            remaining_budget_ns=budget,
        )
    assert adapter.calls == 0


@pytest.mark.parametrize("elapsed", [10, 11])
def test_request_deadline_rejects_late_response_with_live_lease(
    store: Store, scope: AccountScope, elapsed: int
) -> None:
    class SlowAdapter(FakeAdapter):
        def fetch(self, context: object) -> object:
            result = super().fetch(context)  # type: ignore[arg-type]
            store.clock.mono += elapsed  # type: ignore[attr-defined]
            return result

    adapter = SlowAdapter()
    app = service(store, adapter)
    with pytest.raises(OutcomeUnknown):
        app.refresh(scope, idempotency_key="late", remaining_budget_ns=10)
    assert store.latest_snapshot(scope) is None
    assert store.refresh_row("late")["state"] == "outcome_unknown"
    with pytest.raises(OutcomeUnknown):
        app.refresh(scope, idempotency_key="late")
    assert adapter.calls == 1


def test_refresh_insert_race_replays_and_releases_lease(
    store: Store, scope: AccountScope, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = FakeAdapter()
    app = service(store, adapter)
    original_acquire = store.acquire_lease
    raced = False

    def acquire_after_other_request(name: str, owner: str, duration: int) -> object:
        nonlocal raced
        if not raced:
            raced = True
            app.refresh(scope, idempotency_key="raced")
        return original_acquire(name, owner, duration)

    monkeypatch.setattr(store, "acquire_lease", acquire_after_other_request)
    result = app.refresh(scope, idempotency_key="raced")
    assert result.state == "succeeded"
    assert adapter.calls == 1
    assert app.refresh(scope, idempotency_key="next").state == "succeeded"


def test_refresh_start_failure_releases_lease(
    store: Store, scope: AccountScope, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sqlite3

    original_start = store.start_refresh

    def fail_start(*_args: object) -> None:
        raise sqlite3.IntegrityError("unrelated insert failure")

    monkeypatch.setattr(store, "start_refresh", fail_start)
    app = service(store, FakeAdapter())
    with pytest.raises(sqlite3.IntegrityError):
        app.refresh(scope, idempotency_key="failure")
    monkeypatch.setattr(store, "start_refresh", original_start)
    assert app.refresh(scope, idempotency_key="next").state == "succeeded"
