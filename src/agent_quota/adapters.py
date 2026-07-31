"""Production adapter protocol; test doubles live in agent_quota_testkit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from agent_quota.model import AccountScope, CapabilityKind


@dataclass(frozen=True)
class AdapterObservation:
    scope: AccountScope
    kind: CapabilityKind
    unit: str
    used: int | None
    limit: int | None
    remaining: int | None
    reset_at_ns: int | None
    identity_evidence: str
    request_digest: str


@dataclass(frozen=True)
class FetchContext:
    scope: AccountScope
    identity_evidence: str
    request_digest: str
    deadline_ns: int


class Adapter(Protocol):
    def fetch(self, context: FetchContext) -> AdapterObservation: ...
