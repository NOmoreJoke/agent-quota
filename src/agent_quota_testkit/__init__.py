"""Test-only helpers; production code must never import this package."""

from agent_quota_testkit.fake_adapter import FakeAdapter, Scenario

__all__ = ["FakeAdapter", "Scenario"]
