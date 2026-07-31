from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from agent_quota.model import AccountScope, CapabilityKind
from agent_quota.storage import Store


@dataclass
class FakeClock:
    boot_id: str = "boot-a"
    mono: int = 1_000_000_000
    wall: int = 2_000_000_000

    def monotonic_ns(self) -> int:
        return self.mono

    def wall_ns(self) -> int:
        return self.wall


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def scope() -> AccountScope:
    return AccountScope("openrouter", "personal", "current-key")


@pytest.fixture
def store(tmp_path: Path, clock: FakeClock, scope: AccountScope) -> Store:
    value = Store(tmp_path / "data" / "agent-quota.sqlite", clock)
    value.seed_scope(
        scope,
        provider="OpenRouter",
        principal_label="OpenRouter",
        subject_label="API Key 个人",
        kind=CapabilityKind.WINDOW,
        unit="requests",
    )
    yield value
    value.close()
