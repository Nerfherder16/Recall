"""
Tests for retrieval pipeline singleton caching.

Verifies that get_retrieval_pipeline() returns the same instance
on repeated calls, avoiding redundant store lookups.
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock storage drivers before importing retrieval
for mod_name in [
    "neo4j",
    "asyncpg",
    "qdrant_client",
    "qdrant_client.models",
    "qdrant_client.http",
    "qdrant_client.http.models",
    "redis",
    "redis.asyncio",
]:
    sys.modules.setdefault(mod_name, MagicMock())


@pytest.mark.asyncio
async def test_singleton_returns_same_instance():
    """Two calls to get_retrieval_pipeline() return the same object."""
    from src.core.retrieval import (
        RetrievalPipeline,
        get_retrieval_pipeline,
        reset_retrieval_pipeline,
    )

    reset_retrieval_pipeline()

    with (
        patch("src.storage.get_qdrant_store", new_callable=AsyncMock, return_value=MagicMock()),
        patch("src.storage.get_neo4j_store", new_callable=AsyncMock, return_value=MagicMock()),
        patch("src.storage.get_redis_store", new_callable=AsyncMock, return_value=MagicMock()),
    ):
        first = await get_retrieval_pipeline()
        second = await get_retrieval_pipeline()

    assert first is second
    assert isinstance(first, RetrievalPipeline)
    reset_retrieval_pipeline()


@pytest.mark.asyncio
async def test_reset_clears_singleton():
    """reset_retrieval_pipeline() clears the cached instance."""
    from src.core.retrieval import get_retrieval_pipeline, reset_retrieval_pipeline

    reset_retrieval_pipeline()

    with (
        patch("src.storage.get_qdrant_store", new_callable=AsyncMock, return_value=MagicMock()),
        patch("src.storage.get_neo4j_store", new_callable=AsyncMock, return_value=MagicMock()),
        patch("src.storage.get_redis_store", new_callable=AsyncMock, return_value=MagicMock()),
    ):
        first = await get_retrieval_pipeline()
        reset_retrieval_pipeline()
        second = await get_retrieval_pipeline()

    assert first is not second
    reset_retrieval_pipeline()


@pytest.mark.asyncio
async def test_singleton_only_calls_stores_once():
    """Store factories are only called once across multiple get_retrieval_pipeline() calls."""
    from src.core.retrieval import get_retrieval_pipeline, reset_retrieval_pipeline

    reset_retrieval_pipeline()

    mock_get_qdrant = AsyncMock(return_value=MagicMock())
    mock_get_neo4j = AsyncMock(return_value=MagicMock())
    mock_get_redis = AsyncMock(return_value=MagicMock())

    with (
        patch("src.storage.get_qdrant_store", mock_get_qdrant),
        patch("src.storage.get_neo4j_store", mock_get_neo4j),
        patch("src.storage.get_redis_store", mock_get_redis),
    ):
        await get_retrieval_pipeline()
        await get_retrieval_pipeline()
        await get_retrieval_pipeline()

    assert mock_get_qdrant.call_count == 1
    assert mock_get_neo4j.call_count == 1
    assert mock_get_redis.call_count == 1
    reset_retrieval_pipeline()
