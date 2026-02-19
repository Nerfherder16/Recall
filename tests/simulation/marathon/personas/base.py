"""
BasePersona — Abstract base class for marathon simulation personas.

Each persona runs an async loop with a configurable cycle interval,
rate-limited API calls, and per-persona operation counting.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any

from ...client import TimedRecallClient
from ..scheduler import RateLimitScheduler


class BasePersona(ABC):
    """Base class for all marathon personas."""

    name: str = "base"
    cycle_interval: float = 10.0  # seconds between cycles

    def __init__(
        self,
        client: TimedRecallClient,
        scheduler: RateLimitScheduler,
        domain_prefix: str,
    ):
        self.client = client
        self.scheduler = scheduler
        self.domain_prefix = domain_prefix

        # Per-persona stats
        self.ops: dict[str, int] = {}
        self.errors: list[str] = []
        self.cycles: int = 0
        self._start_time: float = 0.0

    def domain(self, subdomain: str) -> str:
        """Build a full domain name: sim-marathon-{run_id}-{subdomain}."""
        return f"{self.domain_prefix}-{subdomain}"

    def count_op(self, op_name: str, n: int = 1):
        self.ops[op_name] = self.ops.get(op_name, 0) + n

    def record_error(self, msg: str):
        self.errors.append(f"[{self.name}] {msg}")
        if len(self.errors) > 200:
            self.errors = self.errors[-100:]  # keep recent

    @abstractmethod
    async def cycle(self):
        """Execute one persona cycle. Called repeatedly by run_loop."""

    async def run_loop(self, stop_event: asyncio.Event):
        """Run persona cycles until stop_event is set."""
        self._start_time = time.monotonic()
        while not stop_event.is_set():
            self.cycles += 1
            try:
                await self.cycle()
            except Exception as e:
                self.record_error(f"cycle {self.cycles}: {e}")

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.cycle_interval)
                break
            except asyncio.TimeoutError:
                pass

    def summary(self) -> dict[str, Any]:
        """Return persona summary for the report."""
        elapsed = time.monotonic() - self._start_time if self._start_time else 0
        return {
            "name": self.name,
            "cycles": self.cycles,
            "elapsed_seconds": round(elapsed, 1),
            "ops": dict(self.ops),
            "error_count": len(self.errors),
            "errors_sample": self.errors[:10],
        }
