"""
Tests for asyncio.gather() parallelization in health dashboard.

Verifies that compute_dashboard() fires all 6 metric queries
concurrently via asyncio.gather() instead of sequentially.
"""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock storage drivers not installed locally
for mod in [
    "neo4j",
    "neo4j.exceptions",
    "asyncpg",
    "qdrant_client",
    "qdrant_client.models",
    "qdrant_client.http",
    "qdrant_client.http.models",
    "redis",
    "redis.asyncio",
]:
    sys.modules.setdefault(mod, MagicMock())

from src.core.health import HealthComputer  # noqa: E402


def _make_health_computer():
    """Create a HealthComputer with mock stores."""
    pg = MagicMock()
    qdrant = MagicMock()
    neo4j = MagicMock()
    redis = MagicMock()
    with patch("src.core.health.get_settings"):
        computer = HealthComputer(pg, qdrant, neo4j, redis)
    return computer


class TestDashboardParallel:
    """Verify compute_dashboard uses asyncio.gather for concurrent queries."""

    @pytest.mark.asyncio
    async def test_gather_fires_all_queries_concurrently(self):
        """All 6 metric queries should start before any completes."""
        call_order = []

        async def make_tracked_coro(name, result):
            call_order.append(("start", name))
            await asyncio.sleep(0.01)
            call_order.append(("end", name))
            return result

        computer = _make_health_computer()

        # Patch all 6 private methods to track call order
        computer._feedback_metrics = lambda: make_tracked_coro(
            "feedback", {"total": 0, "useful": 0}
        )
        computer._population_balance = lambda: make_tracked_coro(
            "population", {"stores": 0, "net_growth": 0}
        )
        computer._graph_cohesion = lambda: make_tracked_coro(
            "graph", {"avg_edge_strength": 0.0, "edge_count": 0}
        )
        computer._pin_ratio = lambda: make_tracked_coro(
            "pins", {"pinned": 0, "total": 0, "ratio": 0.0}
        )
        computer._importance_distribution = lambda: make_tracked_coro("importance", [])
        computer._feedback_similarity = lambda: make_tracked_coro("similarity", [])

        await computer.compute_dashboard()

        # With gather: all starts should come before all ends
        starts = [i for i, (action, _) in enumerate(call_order) if action == "start"]
        ends = [i for i, (action, _) in enumerate(call_order) if action == "end"]

        assert max(starts) < min(ends), (
            f"Expected all starts before any end (parallel), but got order: {call_order}"
        )

    @pytest.mark.asyncio
    async def test_dashboard_returns_all_sections(self):
        """Result dict should contain all 6 metric sections."""
        computer = _make_health_computer()

        computer._feedback_metrics = AsyncMock(return_value={"total": 10})
        computer._population_balance = AsyncMock(return_value={"net_growth": 5})
        computer._graph_cohesion = AsyncMock(return_value={"edge_count": 20})
        computer._pin_ratio = AsyncMock(return_value={"ratio": 0.1})
        computer._importance_distribution = AsyncMock(return_value=[{"bucket": "0.5", "count": 3}])
        computer._feedback_similarity = AsyncMock(return_value=[{"bucket": "0.8", "count": 2}])

        result = await computer.compute_dashboard()

        assert "feedback" in result
        assert "population" in result
        assert "graph" in result
        assert "pins" in result
        assert "importance_distribution" in result
        assert "feedback_similarity" in result
        assert "generated_at" in result

    @pytest.mark.asyncio
    async def test_dashboard_values_match_methods(self):
        """Values in result should come from the correct methods."""
        computer = _make_health_computer()

        expected_feedback = {"total": 42, "useful": 30}
        expected_population = {"net_growth": 10}

        computer._feedback_metrics = AsyncMock(return_value=expected_feedback)
        computer._population_balance = AsyncMock(return_value=expected_population)
        computer._graph_cohesion = AsyncMock(return_value={})
        computer._pin_ratio = AsyncMock(return_value={})
        computer._importance_distribution = AsyncMock(return_value=[])
        computer._feedback_similarity = AsyncMock(return_value=[])

        result = await computer.compute_dashboard()

        assert result["feedback"] == expected_feedback
        assert result["population"] == expected_population
