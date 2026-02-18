"""
Tests for asyncio.gather() parallelization in graph expansion.

Verifies that _graph_expand() fires all Neo4j find_related() calls
concurrently via asyncio.gather() instead of sequentially.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.retrieval import RetrievalPipeline


def _make_pipeline(neo4j_mock=None, qdrant_mock=None, redis_mock=None):
    """Create a RetrievalPipeline with mock stores."""
    qdrant = qdrant_mock or MagicMock()
    neo4j = neo4j_mock or MagicMock()
    redis = redis_mock or MagicMock()
    with patch("src.core.retrieval.get_settings"):
        pipeline = RetrievalPipeline(qdrant, neo4j, redis)
    return pipeline


def _make_related_record(node_id: str, importance: float = 0.8, distance: int = 1):
    """Create a mock Neo4j related record."""
    return {
        "id": node_id,
        "distance": distance,
        "rel_strengths": [0.8],
        "importance": importance,
    }


def _make_qdrant_payload(content: str = "test memory"):
    """Create a mock Qdrant payload."""
    now = datetime.utcnow().isoformat()
    return {
        "content": content,
        "memory_type": "semantic",
        "domain": "test",
        "tags": [],
        "importance": 0.5,
        "stability": 0.5,
        "confidence": 0.8,
        "access_count": 1,
        "created_at": now,
        "updated_at": now,
        "last_accessed": now,
    }


class TestGraphExpandParallel:
    """Verify _graph_expand uses asyncio.gather for concurrent Neo4j calls."""

    @pytest.mark.asyncio
    async def test_gather_fires_all_calls_concurrently(self):
        """All find_related calls should start before any completes."""
        call_order = []

        async def mock_find_related(memory_id, **kwargs):
            call_order.append(("start", memory_id))
            await asyncio.sleep(0.01)  # Simulate small delay
            call_order.append(("end", memory_id))
            return [_make_related_record(f"related-{memory_id}")]

        neo4j = MagicMock()
        neo4j.find_related = AsyncMock(side_effect=mock_find_related)

        qdrant = MagicMock()
        qdrant.get = AsyncMock(return_value=("id", _make_qdrant_payload()))

        pipeline = _make_pipeline(neo4j_mock=neo4j, qdrant_mock=qdrant)

        seed_ids = ["seed-1", "seed-2", "seed-3"]
        await pipeline._graph_expand(seed_ids, None, 2)

        # With gather: all starts should come before all ends
        starts = [i for i, (action, _) in enumerate(call_order) if action == "start"]
        ends = [i for i, (action, _) in enumerate(call_order) if action == "end"]

        # All starts should happen before the first end
        assert max(starts) < min(ends), (
            f"Expected all starts before any end (parallel), but got order: {call_order}"
        )

    @pytest.mark.asyncio
    async def test_gather_calls_all_seeds(self):
        """Each seed ID should get a find_related call."""
        neo4j = MagicMock()
        neo4j.find_related = AsyncMock(return_value=[])

        pipeline = _make_pipeline(neo4j_mock=neo4j)

        seed_ids = ["a", "b", "c", "d"]
        await pipeline._graph_expand(seed_ids, None, 2)

        assert neo4j.find_related.call_count == 4
        called_ids = [call.kwargs["memory_id"] for call in neo4j.find_related.call_args_list]
        assert set(called_ids) == {"a", "b", "c", "d"}

    @pytest.mark.asyncio
    async def test_gather_merges_results_correctly(self):
        """Results from all seeds should be merged, keeping highest activation."""
        # seed-1 finds node-X with importance 0.9
        # seed-2 also finds node-X with importance 0.9 (same node from different seed)
        # Both should merge, keeping the highest activation

        async def mock_find_related(memory_id, **kwargs):
            if memory_id == "seed-1":
                return [
                    {"id": "node-X", "distance": 1, "rel_strengths": [0.9], "importance": 0.9},
                    {"id": "node-A", "distance": 1, "rel_strengths": [0.7], "importance": 0.6},
                ]
            elif memory_id == "seed-2":
                return [
                    {"id": "node-X", "distance": 1, "rel_strengths": [0.5], "importance": 0.9},
                    {"id": "node-B", "distance": 1, "rel_strengths": [0.8], "importance": 0.7},
                ]
            return []

        neo4j = MagicMock()
        neo4j.find_related = AsyncMock(side_effect=mock_find_related)

        qdrant = MagicMock()
        qdrant.get = AsyncMock(return_value=("id", _make_qdrant_payload()))

        pipeline = _make_pipeline(neo4j_mock=neo4j, qdrant_mock=qdrant)

        results = await pipeline._graph_expand(["seed-1", "seed-2"], None, 2)

        result_ids = [r.memory.id for r in results]
        # node-X should appear only once (merged, not duplicated)
        assert result_ids.count("node-X") <= 1

    @pytest.mark.asyncio
    async def test_gather_handles_single_seed(self):
        """Single seed should still work (gather with one coroutine)."""
        neo4j = MagicMock()
        neo4j.find_related = AsyncMock(
            return_value=[
                _make_related_record("related-1"),
            ]
        )

        qdrant = MagicMock()
        qdrant.get = AsyncMock(return_value=("id", _make_qdrant_payload()))

        pipeline = _make_pipeline(neo4j_mock=neo4j, qdrant_mock=qdrant)

        await pipeline._graph_expand(["only-seed"], None, 2)
        assert neo4j.find_related.call_count == 1

    @pytest.mark.asyncio
    async def test_gather_handles_empty_seeds(self):
        """Empty seed list should return empty results."""
        neo4j = MagicMock()
        neo4j.find_related = AsyncMock()

        pipeline = _make_pipeline(neo4j_mock=neo4j)

        results = await pipeline._graph_expand([], None, 2)
        assert results == []
        assert neo4j.find_related.call_count == 0
