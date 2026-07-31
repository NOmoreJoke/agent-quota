"""Injectable clock and boot identity for lease tests."""

from __future__ import annotations

import platform
import subprocess
import time
from dataclasses import dataclass
from typing import Protocol


class Clock(Protocol):
    @property
    def boot_id(self) -> str: ...

    def monotonic_ns(self) -> int: ...

    def wall_ns(self) -> int: ...


def _darwin_boot_id() -> str:
    if platform.system() != "Darwin":
        return f"{platform.system()}:{platform.release()}"
    result = subprocess.run(
        ["/usr/sbin/sysctl", "-n", "kern.boottime"],
        check=False,
        capture_output=True,
        text=True,
        timeout=2,
    )
    value = result.stdout.strip()
    return f"darwin:{value}" if result.returncode == 0 and value else "darwin:unknown"


@dataclass(frozen=True)
class SystemClock:
    boot_id: str = _darwin_boot_id()

    def monotonic_ns(self) -> int:
        return time.monotonic_ns()

    def wall_ns(self) -> int:
        return time.time_ns()
