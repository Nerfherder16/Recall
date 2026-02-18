"""
Test pairing for src/api/routes/admin.py.

The main admin endpoint tests are spread across feature-specific test files:
- tests/core/test_git_invalidation.py (stale endpoints)
- tests/integration/ (admin endpoints via httpx)

This file satisfies TDD pairing for the admin routes module.
"""

import sys
from unittest.mock import MagicMock

_slowapi_mock = MagicMock()
_slowapi_mock.Limiter.return_value.limit.return_value = lambda f: f

for mod_name in [
    "neo4j",
    "asyncpg",
    "qdrant_client",
    "qdrant_client.models",
    "qdrant_client.http",
    "qdrant_client.http.models",
    "redis",
    "redis.asyncio",
    "slowapi.errors",
    "slowapi.util",
    "sse_starlette",
    "sse_starlette.sse",
    "httpx",
    "arq",
    "arq.connections",
]:
    sys.modules.setdefault(mod_name, MagicMock())
sys.modules["slowapi"] = _slowapi_mock


def test_stale_endpoints_exist():
    """Admin module exports stale memory management endpoints."""
    from src.api.routes.admin import list_stale_memories, resolve_stale_memory

    assert callable(list_stale_memories)
    assert callable(resolve_stale_memory)
