"""
Tests for git-aware memory invalidation.

Covers: POST /observe/git-diff endpoint, invalidation worker logic,
admin stale listing, and resolve endpoint.
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


# ---- Task 6: API endpoint + invalidation worker ----


def test_git_diff_request_model():
    """GitDiffRequest model has expected fields."""
    from src.api.routes.observe import GitDiffRequest

    req = GitDiffRequest(
        commit_hash="abc1234",
        changed_files=["src/config.py"],
        diff_text="+HOST=10.0.0.1",
    )
    assert req.commit_hash == "abc1234"
    assert len(req.changed_files) == 1
    assert req.diff_text is not None


@pytest.mark.asyncio
async def test_check_invalidations_flags_matching():
    """Invalidation worker flags memories whose content matches extracted values."""
    from src.workers.invalidation import check_invalidations

    mock_qdrant = MagicMock()

    # Simulate scrolling permanent/durable memories
    memory_point = MagicMock()
    memory_point.id = "mem-1"
    memory_point.payload = {
        "content": "Ollama runs on 192.168.50.62 port 11434",
        "durability": "permanent",
        "domain": "infrastructure",
    }
    mock_qdrant.client = MagicMock()
    mock_qdrant.client.scroll = AsyncMock(return_value=([memory_point], None))
    mock_qdrant.client.set_payload = AsyncMock()
    mock_qdrant.collection = "recall_memories"

    mock_postgres = MagicMock()
    mock_postgres.log_audit = AsyncMock()

    extracted_values = [
        {"type": "ip", "value": "192.168.50.62"},
        {"type": "port", "value": "11434"},
    ]

    with (
        patch(
            "src.storage.get_qdrant_store",
            new_callable=AsyncMock,
            return_value=mock_qdrant,
        ),
        patch(
            "src.storage.get_postgres_store",
            new_callable=AsyncMock,
            return_value=mock_postgres,
        ),
    ):
        result = await check_invalidations(
            commit_hash="abc1234",
            changed_files=["docker-compose.yml"],
            extracted_values=extracted_values,
        )

    assert result["flagged_count"] >= 1
    mock_qdrant.client.set_payload.assert_called()
    # Verify the invalidation_flag was set
    set_call = mock_qdrant.client.set_payload.call_args
    payload = set_call.kwargs.get("payload") or set_call[1].get("payload")
    assert "invalidation_flag" in payload
    assert payload["invalidation_flag"]["commit_hash"] == "abc1234"


@pytest.mark.asyncio
async def test_check_invalidations_skips_non_matching():
    """Non-matching memories are not flagged."""
    from src.workers.invalidation import check_invalidations

    mock_qdrant = MagicMock()

    memory_point = MagicMock()
    memory_point.id = "mem-2"
    memory_point.payload = {
        "content": "React uses JSX for templating",
        "durability": "durable",
        "domain": "development",
    }
    mock_qdrant.client = MagicMock()
    mock_qdrant.client.scroll = AsyncMock(return_value=([memory_point], None))
    mock_qdrant.client.set_payload = AsyncMock()
    mock_qdrant.collection = "recall_memories"

    mock_postgres = MagicMock()
    mock_postgres.log_audit = AsyncMock()

    extracted_values = [
        {"type": "ip", "value": "10.0.0.99"},
    ]

    with (
        patch(
            "src.storage.get_qdrant_store",
            new_callable=AsyncMock,
            return_value=mock_qdrant,
        ),
        patch(
            "src.storage.get_postgres_store",
            new_callable=AsyncMock,
            return_value=mock_postgres,
        ),
    ):
        result = await check_invalidations(
            commit_hash="def5678",
            changed_files=["src/app.tsx"],
            extracted_values=extracted_values,
        )

    assert result["flagged_count"] == 0
    mock_qdrant.client.set_payload.assert_not_called()


@pytest.mark.asyncio
async def test_check_invalidations_writes_audit():
    """Each flagged memory gets an audit log entry."""
    from src.workers.invalidation import check_invalidations

    mock_qdrant = MagicMock()

    points = []
    for i in range(3):
        p = MagicMock()
        p.id = f"mem-{i}"
        p.payload = {
            "content": f"Server at 10.0.0.{i + 1} is important",
            "durability": "permanent",
        }
        points.append(p)
    mock_qdrant.client = MagicMock()
    mock_qdrant.client.scroll = AsyncMock(return_value=(points, None))
    mock_qdrant.client.set_payload = AsyncMock()
    mock_qdrant.collection = "recall_memories"

    mock_postgres = MagicMock()
    mock_postgres.log_audit = AsyncMock()

    # Only 10.0.0.1 and 10.0.0.3 match
    extracted_values = [
        {"type": "ip", "value": "10.0.0.1"},
        {"type": "ip", "value": "10.0.0.3"},
    ]

    with (
        patch(
            "src.storage.get_qdrant_store",
            new_callable=AsyncMock,
            return_value=mock_qdrant,
        ),
        patch(
            "src.storage.get_postgres_store",
            new_callable=AsyncMock,
            return_value=mock_postgres,
        ),
    ):
        result = await check_invalidations(
            commit_hash="111aaa",
            changed_files=["config.yml"],
            extracted_values=extracted_values,
        )

    assert result["flagged_count"] == 2
    assert mock_postgres.log_audit.call_count == 2


# ---- Task 7: admin endpoints + resolve ----


@pytest.mark.asyncio
async def test_list_stale_returns_flagged():
    """GET /admin/stale returns memories with invalidation_flag set."""
    from src.api.routes.admin import list_stale_memories

    mock_qdrant = MagicMock()
    flagged_point = MagicMock()
    flagged_point.id = "mem-flagged"
    flagged_point.payload = {
        "content": "Ollama on 192.168.50.62",
        "domain": "infrastructure",
        "invalidation_flag": {
            "reason": "Values ['192.168.50.62'] found in commit abc1234",
            "commit_hash": "abc1234def5678",
            "flagged_at": "2026-02-18T20:00:00",
        },
    }
    mock_qdrant.client = MagicMock()
    mock_qdrant.client.scroll = AsyncMock(return_value=([flagged_point], None))
    mock_qdrant.collection = "recall_memories"

    mock_request = MagicMock()

    with patch(
        "src.storage.get_qdrant_store",
        new_callable=AsyncMock,
        return_value=mock_qdrant,
    ):
        result = await list_stale_memories(request=mock_request)

    assert len(result["stale_memories"]) == 1
    assert result["stale_memories"][0]["id"] == "mem-flagged"
    assert result["stale_memories"][0]["invalidation_flag"]["commit_hash"] == "abc1234def5678"


@pytest.mark.asyncio
async def test_list_stale_empty():
    """GET /admin/stale returns empty when no flagged memories."""
    from src.api.routes.admin import list_stale_memories

    mock_qdrant = MagicMock()
    mock_qdrant.client = MagicMock()
    mock_qdrant.client.scroll = AsyncMock(return_value=([], None))
    mock_qdrant.collection = "recall_memories"

    mock_request = MagicMock()

    with patch(
        "src.storage.get_qdrant_store",
        new_callable=AsyncMock,
        return_value=mock_qdrant,
    ):
        result = await list_stale_memories(request=mock_request)

    assert result["stale_memories"] == []
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_resolve_stale_clears_flag():
    """POST /admin/stale/{id}/resolve clears the invalidation_flag."""
    from src.api.routes.admin import resolve_stale_memory

    mock_qdrant = MagicMock()
    mock_qdrant.client = MagicMock()
    mock_qdrant.client.set_payload = AsyncMock()
    mock_qdrant.collection = "recall_memories"

    mock_postgres = MagicMock()
    mock_postgres.log_audit = AsyncMock()

    mock_request = MagicMock()

    with (
        patch(
            "src.storage.get_qdrant_store",
            new_callable=AsyncMock,
            return_value=mock_qdrant,
        ),
        patch(
            "src.storage.get_postgres_store",
            new_callable=AsyncMock,
            return_value=mock_postgres,
        ),
    ):
        result = await resolve_stale_memory(request=mock_request, memory_id="mem-flagged")

    assert result["status"] == "resolved"
    # Verify set_payload called with null invalidation_flag
    mock_qdrant.client.set_payload.assert_called_once()
    call_kwargs = mock_qdrant.client.set_payload.call_args
    payload = call_kwargs.kwargs.get("payload") or call_kwargs[1].get("payload")
    assert payload["invalidation_flag"] is None
