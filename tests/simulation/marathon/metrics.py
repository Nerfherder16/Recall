"""
MetricsCollector — Periodic system state snapshots during marathon runs.

Queries /stats, /stats/domains, /admin/health/dashboard, /admin/ml/reranker-status
every N seconds and stores time-series snapshots.
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..client import TimedRecallClient
from .scheduler import RateLimitScheduler


@dataclass
class MetricSnapshot:
    """Single point-in-time system state capture."""

    timestamp: str
    elapsed_minutes: float

    # Population
    total_memories: int = 0
    graph_nodes: int = 0
    graph_edges: int = 0

    # Domain breakdown (domain -> count)
    domain_counts: dict[str, int] = field(default_factory=dict)

    # Health dashboard
    importance_distribution: dict[str, Any] = field(default_factory=dict)
    population_balance: float = 0.0
    graph_cohesion: float = 0.0
    pin_ratio: float = 0.0
    feedback_metrics: dict[str, Any] = field(default_factory=dict)

    # Reranker
    reranker_cv_score: float | None = None
    reranker_n_samples: int | None = None

    # Latency (p50/p95 at snapshot time)
    latency_p50: dict[str, float] = field(default_factory=dict)
    latency_p95: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "elapsed_minutes": round(self.elapsed_minutes, 1),
            "total_memories": self.total_memories,
            "graph_nodes": self.graph_nodes,
            "graph_edges": self.graph_edges,
            "domain_counts": self.domain_counts,
            "importance_distribution": self.importance_distribution,
            "population_balance": self.population_balance,
            "graph_cohesion": self.graph_cohesion,
            "pin_ratio": self.pin_ratio,
            "feedback_metrics": self.feedback_metrics,
            "reranker_cv_score": self.reranker_cv_score,
            "reranker_n_samples": self.reranker_n_samples,
            "latency_p50": self.latency_p50,
            "latency_p95": self.latency_p95,
        }


class MetricsCollector:
    """Collects system state snapshots at regular intervals."""

    def __init__(
        self,
        client: TimedRecallClient,
        scheduler: RateLimitScheduler,
        interval: int = 300,
    ):
        self.client = client
        self.scheduler = scheduler
        self.interval = interval
        self.snapshots: list[MetricSnapshot] = []
        self._start_time = time.monotonic()
        self._running = False

    async def collect_snapshot(self) -> MetricSnapshot:
        """Collect a single snapshot from all endpoints."""
        snap = MetricSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            elapsed_minutes=(time.monotonic() - self._start_time) / 60.0,
        )

        # /stats (default bucket)
        await self.scheduler.acquire("default")
        stats = await self.client.stats()
        if stats:
            mem_stats = stats.get("memories", {})
            snap.total_memories = mem_stats.get("total", 0)
            snap.graph_nodes = mem_stats.get("graph_nodes", 0)
            snap.graph_edges = mem_stats.get("relationships", 0)

        # /stats/domains (default bucket)
        await self.scheduler.acquire("default")
        domains = await self.client._request("GET", "/stats/domains")
        if domains and isinstance(domains, dict):
            for d in domains.get("domains", []):
                name = d.get("domain", "unknown")
                snap.domain_counts[name] = d.get("count", 0)

        # /admin/health/dashboard (admin bucket)
        await self.scheduler.acquire("admin")
        health = await self.client._request("GET", "/admin/health/dashboard")
        if health and isinstance(health, dict):
            snap.importance_distribution = health.get("importance_distribution", {})
            snap.population_balance = health.get("population_balance", 0.0)
            snap.graph_cohesion = health.get("graph_cohesion", 0.0)
            snap.pin_ratio = health.get("pin_ratio", 0.0)
            snap.feedback_metrics = health.get("feedback_metrics", {})

        # /admin/ml/reranker-status (admin bucket)
        await self.scheduler.acquire("admin")
        reranker = await self.client._request("GET", "/admin/ml/reranker-status")
        if reranker and isinstance(reranker, dict):
            snap.reranker_cv_score = reranker.get("cv_score")
            snap.reranker_n_samples = reranker.get("n_samples")

        # Latency stats from client
        all_stats = self.client.latency_stats()
        for op, s in all_stats.items():
            if isinstance(s, dict) and s.get("count", 0) > 0:
                snap.latency_p50[op] = s.get("p50", 0)
                snap.latency_p95[op] = s.get("p95", 0)

        self.snapshots.append(snap)
        return snap

    async def run_loop(self, stop_event: asyncio.Event):
        """Run snapshot collection loop until stop_event is set."""
        self._running = True
        self._start_time = time.monotonic()

        # Initial snapshot
        try:
            await self.collect_snapshot()
        except Exception as e:
            print(f"  [metrics] Initial snapshot error: {e}")

        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.interval)
                break  # stop_event was set
            except asyncio.TimeoutError:
                pass  # interval elapsed, collect next snapshot

            try:
                snap = await self.collect_snapshot()
                n = len(self.snapshots)
                print(f"  [metrics] Snapshot #{n}: {snap.total_memories} memories, "
                      f"{snap.graph_nodes} nodes, {snap.graph_edges} edges")
            except Exception as e:
                print(f"  [metrics] Snapshot error: {e}")

        self._running = False
