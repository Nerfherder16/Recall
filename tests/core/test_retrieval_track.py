"""
Tests for _track_access background task and browse_mode behavior.

Verifies:
- browse_mode=True skips _track_access entirely
- Normal mode fires _track_access as a background task (non-blocking)
"""

import asyncio
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock storage drivers not installed locally (needed for reranker import chain)
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

from src.core.models import MemoryQuery  # noqa: E402
from src.core.retrieval import RetrievalPipeline  # noqa: E402


def _make_pipeline(neo4j_mock=None, qdrant_mock=None, redis_mock=None):
    """Create a RetrievalPipeline with mock stores."""
    qdrant = qdrant_mock or MagicMock()
    neo4j = neo4j_mock or MagicMock()
    redis = redis_mock or MagicMock()
    with patch("src.core.retrieval.get_settings"):
        pipeline = RetrievalPipeline(qdrant, neo4j, redis)
    return pipeline


def _make_qdrant_payload(content="test"):
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


class TestTrackAccessBackground:
    """Verify _track_access behavior with browse_mode."""

    def _setup_pipeline_mocks(self):
        """Create pipeline with fully-mocked internal stages."""
        qdrant = MagicMock()
        qdrant.search = AsyncMock(return_value=[("mem-1", 0.9, _make_qdrant_payload())])
        qdrant.search_facts = AsyncMock(return_value=[])
        qdrant.search_anti_patterns = AsyncMock(return_value=[])
        qdrant.update_access = AsyncMock()
        qdrant.update_importance = AsyncMock()

        neo4j = MagicMock()
        neo4j.find_related = AsyncMock(return_value=[])
        neo4j.find_contradictions = AsyncMock(return_value=[])
        neo4j.update_importance = AsyncMock()

        redis = MagicMock()
        redis.get_working_memory = AsyncMock(return_value=[])

        pipeline = _make_pipeline(
            neo4j_mock=neo4j,
            qdrant_mock=qdrant,
            redis_mock=redis,
        )
        return pipeline, qdrant, neo4j

    @pytest.mark.asyncio
    async def test_browse_mode_skips_track_access(self):
        """browse_mode=True should not call _track_access."""
        pipeline, qdrant, neo4j = self._setup_pipeline_mocks()

        # Replace _track_access with a spy
        track_spy = AsyncMock()
        pipeline._track_access = track_spy

        # Stub out stages that need deep imports
        embed_mock = AsyncMock(return_value=[0.1] * 384)
        with patch(
            "src.core.retrieval.get_embedding_service",
            return_value=AsyncMock(embed=embed_mock),
        ):
            query = MemoryQuery(text="test query", limit=5)
            await pipeline.retrieve(query, browse_mode=True)

        track_spy.assert_not_called()

    @pytest.mark.asyncio
    async def test_normal_mode_fires_track_access(self):
        """browse_mode=False should fire _track_access as background task."""
        pipeline, qdrant, neo4j = self._setup_pipeline_mocks()

        track_called = asyncio.Event()
        original_track = pipeline._track_access

        async def track_with_signal(results):
            await original_track(results)
            track_called.set()

        pipeline._track_access = track_with_signal

        embed_mock = AsyncMock(return_value=[0.1] * 384)
        with patch(
            "src.core.retrieval.get_embedding_service",
            return_value=AsyncMock(embed=embed_mock),
        ):
            query = MemoryQuery(text="test query", limit=5)
            await pipeline.retrieve(query, browse_mode=False)

        # Wait for background task
        await asyncio.wait_for(track_called.wait(), timeout=1.0)
        assert track_called.is_set()
        # Verify actual writes happened
        assert qdrant.update_access.call_count > 0

    @pytest.mark.asyncio
    async def test_browse_mode_default_is_false(self):
        """Default browse_mode should be False (track_access fires)."""
        pipeline, qdrant, neo4j = self._setup_pipeline_mocks()

        track_called = asyncio.Event()

        async def track_with_signal(results):
            track_called.set()

        pipeline._track_access = track_with_signal

        embed_mock = AsyncMock(return_value=[0.1] * 384)
        with patch(
            "src.core.retrieval.get_embedding_service",
            return_value=AsyncMock(embed=embed_mock),
        ):
            query = MemoryQuery(text="test query", limit=5)
            await pipeline.retrieve(query)

        await asyncio.wait_for(track_called.wait(), timeout=1.0)
        assert track_called.is_set()
