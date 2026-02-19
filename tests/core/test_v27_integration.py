"""
Integration smoke tests for v2.7 "Trust & Context" features.

Covers: rehydrate endpoint, git-diff endpoint, stale admin endpoints,
diff_parser extraction, and ML eval harness execution.
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock storage drivers before importing
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


def test_rehydrate_models_importable():
    """RehydrateRequest and RehydrateResponse are importable."""
    from src.api.routes.search import (
        RehydrateEntry,
        RehydrateRequest,
    )

    req = RehydrateRequest(domain="infrastructure")
    assert req.domain == "infrastructure"
    assert req.include_narrative is False
    assert req.include_anti_patterns is False

    entry = RehydrateEntry(
        id="mem-1",
        content="test",
        summary="test summary",
        memory_type="semantic",
        domain="infra",
        importance=0.8,
        created_at="2026-02-18T00:00:00Z",
        is_anti_pattern=False,
    )
    assert entry.is_anti_pattern is False


@pytest.mark.asyncio
async def test_rehydrate_endpoint_returns_entries():
    """POST /search/rehydrate returns chronological entries."""
    from src.api.routes.search import rehydrate_context

    mock_qdrant = MagicMock()
    mock_qdrant.scroll_time_range = AsyncMock(return_value=[])
    mock_redis = MagicMock()
    mock_redis.client = MagicMock()
    mock_redis.client.get = AsyncMock(return_value=None)
    mock_redis.client.setex = AsyncMock()
    mock_request = MagicMock()

    with (
        patch(
            "src.storage.get_qdrant_store",
            new_callable=AsyncMock,
            return_value=mock_qdrant,
        ),
        patch(
            "src.storage.get_redis_store",
            new_callable=AsyncMock,
            return_value=mock_redis,
        ),
    ):
        from src.api.routes.search import RehydrateRequest

        req = RehydrateRequest(domain="test")
        result = await rehydrate_context(request=mock_request, body=req)

    assert hasattr(result, "entries")
    assert hasattr(result, "window_start")


def test_git_diff_request_model():
    """GitDiffRequest model is importable and has expected fields."""
    from src.api.routes.observe import GitDiffRequest

    req = GitDiffRequest(
        commit_hash="abc1234",
        changed_files=["src/config.py"],
        diff_text="+HOST=10.0.0.1",
    )
    assert req.commit_hash == "abc1234"


def test_diff_parser_extracts_ips():
    """diff_parser extracts IP addresses from diff text."""
    from src.core.diff_parser import extract_values

    values = extract_values("+OLLAMA_HOST=192.168.50.62")
    types = [v["type"] for v in values]
    vals = [v["value"] for v in values]
    assert "ip" in types
    assert "192.168.50.62" in vals


def test_diff_parser_extracts_ports():
    """diff_parser extracts port numbers from diff text."""
    from src.core.diff_parser import extract_values

    values = extract_values("+EXPOSE 8200")
    types = [v["type"] for v in values]
    vals = [v["value"] for v in values]
    assert "port" in types
    assert "8200" in vals


def test_diff_parser_extracts_urls():
    """diff_parser extracts URLs from diff text."""
    from src.core.diff_parser import extract_values

    values = extract_values("+API_URL=http://192.168.50.19:8200")
    types = [v["type"] for v in values]
    assert "url" in types


def test_stale_endpoints_exist():
    """Admin module exports stale management endpoints."""
    from src.api.routes.admin import list_stale_memories, resolve_stale_memory

    assert callable(list_stale_memories)
    assert callable(resolve_stale_memory)


@pytest.mark.asyncio
async def test_invalidation_worker_callable():
    """check_invalidations is async callable."""
    from src.workers.invalidation import check_invalidations

    assert callable(check_invalidations)


def test_eval_harness_runs():
    """ML eval harness modules are importable and produce metrics."""
    from tests.ml.run_eval import (
        compute_metrics,
        eval_baseline,
        eval_reranker,
    )

    # Basic metric computation works
    m = compute_metrics([True, False], [True, False])
    assert m["f1"] == 1.0

    # Reranker eval with minimal data
    data = [
        {"features": [0.9] * 11, "expected_useful": True},
        {"features": [0.1] * 11, "expected_useful": False},
    ]
    rm = eval_reranker(data)
    assert rm["model"] == "reranker"
    assert rm["total"] == 2

    # Baseline eval with minimal data (no trained model needed)
    sdata = [
        {
            "turns": [
                {"role": "user", "content": "Fix the error crash bug"},
                {"role": "assistant", "content": "Fixed the timeout issue"},
            ],
            "is_signal": True,
            "signal_type": "error_fix",
        },
        {
            "turns": [
                {"role": "user", "content": "Hi there"},
                {"role": "assistant", "content": "Hello!"},
            ],
            "is_signal": False,
            "signal_type": "none",
        },
    ]
    bl, _ = eval_baseline(sdata)
    assert bl["total"] == 2
    assert bl["model"] == "baseline_heuristic"
