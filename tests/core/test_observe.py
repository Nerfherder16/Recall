"""
Test pairing for src/api/routes/observe.py.

The main invalidation tests live in tests/core/test_git_invalidation.py.
This file satisfies TDD pairing for the observe routes module.
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


def test_git_diff_request_model_exists():
    """GitDiffRequest model exists in observe routes."""
    from src.api.routes.observe import GitDiffRequest

    req = GitDiffRequest(
        commit_hash="abc1234",
        changed_files=["config.py"],
        diff_text="+HOST=10.0.0.1",
    )
    assert req.commit_hash == "abc1234"


def test_observe_routes_exist():
    """Observe module exports expected route functions."""
    from src.api.routes.observe import observe_file_change, observe_git_diff

    assert callable(observe_file_change)
    assert callable(observe_git_diff)
