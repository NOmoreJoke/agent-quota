from __future__ import annotations

import pytest

from agent_quota.model import (
    AccountScope,
    CapabilityKind,
    CapabilitySnapshot,
    Freshness,
    Health,
)


def test_scope_components_are_unambiguous() -> None:
    with pytest.raises(ValueError):
        AccountScope("provider:forged", "subject", "capability")
    with pytest.raises(ValueError):
        AccountScope("provider", "subject\nforged", "capability")


def snapshot(**overrides: object) -> CapabilitySnapshot:
    values = {
        "scope": AccountScope("p", "s", "c"),
        "kind": CapabilityKind.WINDOW,
        "unit": "requests",
        "used": 1,
        "limit": 10,
        "remaining": 9,
        "reset_at_ns": None,
        "observed_at_ns": 1,
        "freshness": Freshness.FRESH,
        "health": Health.OK,
    }
    values.update(overrides)
    return CapabilitySnapshot(**values)  # type: ignore[arg-type]


def test_scope_round_trip() -> None:
    value = AccountScope("provider", "subject", "capability")
    assert AccountScope.parse(value.opaque_ref) == value


@pytest.mark.parametrize("value", ["", "a:b", "a:b:c:d", "a::c", f"{'x' * 65}:b:c"])
def test_scope_rejects_invalid_shape(value: str) -> None:
    with pytest.raises(ValueError):
        AccountScope.parse(value)


@pytest.mark.parametrize(
    "overrides",
    [
        {"limit": None, "remaining": 1},
        {"limit": 1, "remaining": None},
        {"limit": 1, "remaining": 2},
        {"used": -1},
        {"unit": ""},
    ],
)
def test_snapshot_rejects_invalid_values(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        snapshot(**overrides)


def test_unlimited_snapshot_is_valid() -> None:
    assert snapshot(used=0, limit=None, remaining=None).renderer_projection()["limit"] is None
