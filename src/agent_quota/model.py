"""Closed domain values for principals, scopes and quota snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Freshness(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    EXPIRED = "expired"


class Health(StrEnum):
    OK = "ok"
    AUTH_ERROR = "auth_error"
    RATE_LIMITED = "rate_limited"
    NETWORK_ERROR = "network_error"
    SCHEMA_CHANGED = "schema_changed"
    SEMANTIC_SUSPECT = "semantic_suspect"
    PROVIDER_ERROR = "provider_error"
    UNSUPPORTED = "unsupported"
    INCOMPATIBLE = "incompatible"


class CapabilityKind(StrEnum):
    WINDOW = "window"
    BALANCE = "balance"
    COUNTER = "counter"
    STATUS = "status"


@dataclass(frozen=True)
class AccountScope:
    principal_id: str
    subject_id: str
    capability_id: str

    def __post_init__(self) -> None:
        for value in (self.principal_id, self.subject_id, self.capability_id):
            encoded = value.encode()
            if (
                not value
                or len(encoded) > 64
                or ":" in value
                or any(byte < 0x21 or byte == 0x7F for byte in encoded)
            ):
                raise ValueError("invalid scope component")

    @property
    def opaque_ref(self) -> str:
        return ":".join((self.principal_id, self.subject_id, self.capability_id))

    @classmethod
    def parse(cls, value: str) -> AccountScope:
        parts = value.split(":")
        if len(parts) != 3:
            raise ValueError("invalid scope reference")
        return cls(*parts)


@dataclass(frozen=True)
class CapabilitySnapshot:
    scope: AccountScope
    kind: CapabilityKind
    unit: str
    used: int | None
    limit: int | None
    remaining: int | None
    reset_at_ns: int | None
    observed_at_ns: int
    freshness: Freshness
    health: Health

    def __post_init__(self) -> None:
        if not self.unit or len(self.unit.encode()) > 32:
            raise ValueError("invalid unit")
        values = (self.used, self.limit, self.remaining)
        if any(value is not None and value < 0 for value in values):
            raise ValueError("quota values must be non-negative")
        if self.limit is not None and self.remaining is not None and self.remaining > self.limit:
            raise ValueError("remaining exceeds limit")
        if (self.limit is None) != (self.remaining is None):
            raise ValueError("limit and remaining nullability mismatch")

    def renderer_projection(self) -> dict[str, Any]:
        return {
            "scope_ref": self.scope.opaque_ref,
            "kind": self.kind.value,
            "unit": self.unit,
            "used": self.used,
            "limit": self.limit,
            "remaining": self.remaining,
            "reset_at_ns": self.reset_at_ns,
            "observed_at_ns": self.observed_at_ns,
            "freshness": self.freshness.value,
            "health": self.health.value,
        }
