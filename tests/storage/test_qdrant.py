"""
Tests for QdrantStore methods — specifically scroll_time_range.

The bulk of rehydrate-related tests live in tests/core/test_rehydrate.py.
This file satisfies TDD pairing for src/storage/qdrant.py.
"""

import sys
from unittest.mock import MagicMock

import pytest

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
async def test_scroll_time_range_exists():
    """scroll_time_range method exists on QdrantStore."""
    from src.storage.qdrant import QdrantStore

    assert hasattr(QdrantStore, "scroll_time_range")
