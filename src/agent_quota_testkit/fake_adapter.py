"""Deterministic adapter covering success and adversarial response classes."""

from __future__ import annotations

from dataclasses import replace
from enum import StrEnum

from agent_quota.adapters import AdapterObservation, FetchContext
from agent_quota.errors import ProviderFailure
from agent_quota.model import CapabilityKind


class Scenario(StrEnum):
    NORMAL = "normal"
    NULL_UNLIMITED = "null_unlimited"
    MISSING = "missing"
    WRONG_TYPE = "wrong_type"
    AUTH_401 = "401"
    AUTH_403 = "403"
    RATE_429 = "429"
    SERVER_5XX = "5xx"
    TIMEOUT = "timeout"
    OVERSIZE = "oversize"
    SCOPE_MISMATCH = "scope_mismatch"
    IDENTITY_MISMATCH = "identity_mismatch"
    DIGEST_MISMATCH = "digest_mismatch"


class FakeAdapter:
    def __init__(self, scenario: Scenario = Scenario.NORMAL) -> None:
        self.scenario = scenario
        self.calls = 0

    def fetch(self, context: FetchContext) -> AdapterObservation:
        self.calls += 1
        failures = {
            Scenario.AUTH_401: "auth_error",
            Scenario.AUTH_403: "not_authorized",
            Scenario.RATE_429: "rate_limited",
            Scenario.SERVER_5XX: "provider_unavailable",
        }
        if self.scenario in failures:
            raise ProviderFailure(failures[self.scenario])
        if self.scenario == Scenario.TIMEOUT:
            raise TimeoutError("fake timeout")
        if self.scenario == Scenario.MISSING:
            raise ValueError("missing required field")
        if self.scenario == Scenario.WRONG_TYPE:
            raise TypeError("wrong field type")
        if self.scenario == Scenario.OVERSIZE:
            raise ValueError("response exceeds one MiB")
        observation = AdapterObservation(
            scope=context.scope,
            kind=CapabilityKind.WINDOW,
            unit="requests",
            used=76,
            limit=100,
            remaining=24,
            reset_at_ns=None,
            identity_evidence=context.identity_evidence,
            request_digest=context.request_digest,
        )
        if self.scenario == Scenario.NULL_UNLIMITED:
            observation = replace(observation, used=0, limit=None, remaining=None)
        elif self.scenario == Scenario.SCOPE_MISMATCH:
            observation = replace(
                observation,
                scope=replace(context.scope, capability_id="other"),
            )
        elif self.scenario == Scenario.IDENTITY_MISMATCH:
            observation = replace(observation, identity_evidence="wrong")
        elif self.scenario == Scenario.DIGEST_MISMATCH:
            observation = replace(observation, request_digest="0" * 64)
        return observation
