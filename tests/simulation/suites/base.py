"""
BaseSuite — Abstract base class for all test suites.
"""

from abc import ABC, abstractmethod

from tests.simulation.client import TimedRecallClient
from tests.simulation.config import TestbedConfig
from tests.simulation.report import SuiteReport


class BaseSuite(ABC):
    """Abstract base for testbed suites."""

    name: str = "base"

    def __init__(self, client: TimedRecallClient, config: TestbedConfig):
        self.client = client
        self.config = config
        self.domain = client.suite_domain(self.name)
        self.run_tag = client.run_tag()
        self._observations: list[str] = []
        self._errors: list[str] = []
        self._metrics: dict = {}

    @abstractmethod
    async def run(self) -> SuiteReport:
        """Execute the suite and return a report."""
        ...

    def observe(self, msg: str):
        """Record a human-readable observation."""
        self._observations.append(msg)
        if self.config.verbose:
            print(f"  [{self.name}] {msg}")

    def error(self, msg: str):
        """Record an error."""
        self._errors.append(msg)
        print(f"  [{self.name}] ERROR: {msg}")

    def metric(self, key: str, value):
        """Record a metric."""
        self._metrics[key] = value

    def _make_report(self, passed: bool, duration: float) -> SuiteReport:
        """Build a SuiteReport from accumulated state."""
        return SuiteReport(
            suite_name=self.name,
            duration_seconds=round(duration, 2),
            passed=passed,
            metrics=self._metrics,
            observations=self._observations,
            errors=self._errors,
        )

    async def _store(
        self,
        content: str,
        importance: float = 0.5,
        memory_type: str = "semantic",
        tags: list[str] | None = None,
    ) -> str | None:
        """Helper to store a memory in this suite's domain."""
        r = await self.client.store_memory(
            content=content,
            domain=self.domain,
            memory_type=memory_type,
            tags=tags,
            importance=importance,
        )
        if r and r.get("id") and r.get("created"):
            return r["id"]
        if r and r.get("id"):
            return r["id"]  # dedup hit — still usable
        return None
