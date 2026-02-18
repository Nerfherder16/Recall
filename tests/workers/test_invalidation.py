"""
Test pairing for src/workers/invalidation.py.

The main tests live in tests/core/test_git_invalidation.py which exercises
the check_invalidations function with mock Qdrant/Postgres.
"""

import sys
from unittest.mock import MagicMock

for mod_name in [
    "neo4j",
    "asyncpg",
    "qdrant_client",
    "qdrant_client.models",
    "qdrant_client.http",
    "qdrant_client.http.models",
    "redis",
    "redis.asyncio",
    "arq",
    "arq.connections",
]:
    sys.modules.setdefault(mod_name, MagicMock())


def test_invalidation_module_exists():
    """Invalidation worker module exports check_invalidations."""
    from src.workers.invalidation import check_invalidations

    assert callable(check_invalidations)
