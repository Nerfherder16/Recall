"""
Tests for the POST /search/rehydrate endpoint.

Verifies temporal context reconstruction: time-range scroll,
chronological ordering, domain filtering, and response models.
"""

import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock storage and API drivers before importing
# Configure slowapi mock so @limiter.limit() acts as a pass-through decorator
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


def _make_payload(
    content: str,
    domain: str = "development",
    memory_type: str = "semantic",
    importance: float = 0.5,
    created_at: str | None = None,
    durability: str | None = "durable",
    pinned: str = "false",
    access_count: int = 1,
    username: str | None = None,
) -> dict:
    """Create a mock Qdrant payload."""
    if created_at is None:
        created_at = datetime.utcnow().isoformat()
    return {
        "content": content,
        "domain": domain,
        "memory_type": memory_type,
        "importance": importance,
        "created_at": created_at,
        "durability": durability,
        "pinned": pinned,
        "access_count": access_count,
        "username": username,
    }


# ---- Task 1: scroll_time_range + endpoint basics ----


@pytest.mark.asyncio
async def test_scroll_time_range_returns_chronological():
    """scroll_time_range returns entries sorted by created_at."""
    from src.storage.qdrant import QdrantStore

    store = QdrantStore.__new__(QdrantStore)
    store.client = MagicMock()
    store.collection = "test_collection"

    now = datetime.utcnow()
    payloads = [
        _make_payload("old memory", created_at=(now - timedelta(hours=2)).isoformat()),
        _make_payload("new memory", created_at=now.isoformat()),
        _make_payload("mid memory", created_at=(now - timedelta(hours=1)).isoformat()),
    ]

    # Mock scroll to return all 3 points
    mock_points = []
    for i, p in enumerate(payloads):
        point = MagicMock()
        point.id = f"id-{i}"
        point.payload = p
        mock_points.append(point)

    store.client.scroll = AsyncMock(return_value=(mock_points, None))

    since = (now - timedelta(hours=3)).isoformat()
    until = (now + timedelta(hours=1)).isoformat()

    results = await store.scroll_time_range(since=since, until=until)

    assert len(results) == 3
    # Should be sorted chronologically
    dates = [r[1]["created_at"] for r in results]
    assert dates == sorted(dates)


@pytest.mark.asyncio
async def test_scroll_time_range_domain_filter():
    """scroll_time_range applies domain filter when provided."""
    from src.storage.qdrant import QdrantStore

    store = QdrantStore.__new__(QdrantStore)
    store.client = MagicMock()
    store.collection = "test_collection"

    store.client.scroll = AsyncMock(return_value=([], None))

    await store.scroll_time_range(
        since="2026-01-01T00:00:00",
        until="2026-01-31T23:59:59",
        domain="infrastructure",
    )

    # Verify scroll was called
    store.client.scroll.assert_called_once()
    call_kwargs = store.client.scroll.call_args
    scroll_filter = call_kwargs.kwargs.get("scroll_filter") or call_kwargs[1].get("scroll_filter")
    # Filter should have conditions for domain + since + until + not-superseded
    assert scroll_filter is not None


@pytest.mark.asyncio
async def test_scroll_time_range_empty():
    """scroll_time_range returns empty list when no memories in range."""
    from src.storage.qdrant import QdrantStore

    store = QdrantStore.__new__(QdrantStore)
    store.client = MagicMock()
    store.collection = "test_collection"

    store.client.scroll = AsyncMock(return_value=([], None))

    results = await store.scroll_time_range(
        since="2099-01-01T00:00:00",
        until="2099-12-31T23:59:59",
    )

    assert results == []


@pytest.mark.asyncio
async def test_scroll_time_range_with_limit():
    """scroll_time_range respects the limit parameter."""
    from src.storage.qdrant import QdrantStore

    store = QdrantStore.__new__(QdrantStore)
    store.client = MagicMock()
    store.collection = "test_collection"

    now = datetime.utcnow()
    mock_points = []
    for i in range(10):
        point = MagicMock()
        point.id = f"id-{i}"
        point.payload = _make_payload(
            f"memory {i}",
            created_at=(now - timedelta(hours=i)).isoformat(),
        )
        mock_points.append(point)

    store.client.scroll = AsyncMock(return_value=(mock_points, None))

    results = await store.scroll_time_range(
        since=(now - timedelta(hours=20)).isoformat(),
        until=(now + timedelta(hours=1)).isoformat(),
        limit=5,
    )

    assert len(results) == 5


def test_rehydrate_models_exist():
    """RehydrateRequest and RehydrateResponse models have expected fields."""
    from src.api.routes.search import (
        RehydrateEntry,
        RehydrateRequest,
        RehydrateResponse,
    )

    req = RehydrateRequest(
        since="2026-01-01T00:00:00",
        until="2026-01-31T23:59:59",
        domain="development",
        max_entries=20,
    )
    assert req.since is not None
    assert req.until is not None
    assert req.domain == "development"
    assert req.max_entries == 20
    assert req.include_narrative is False
    assert req.include_anti_patterns is False

    entry = RehydrateEntry(
        id="test-1",
        summary="A test memory",
        memory_type="semantic",
        domain="development",
        created_at="2026-01-15T12:00:00",
        importance=0.7,
    )
    assert entry.is_anti_pattern is False
    assert entry.pinned is False

    resp = RehydrateResponse(
        entries=[entry],
        total=1,
        window_start="2026-01-01T00:00:00",
        window_end="2026-01-31T23:59:59",
        narrative=None,
    )
    assert resp.total == 1
    assert resp.narrative is None


# ---- Task 2: LLM narrative + Redis cache ----


@pytest.mark.asyncio
async def test_rehydrate_narrative_calls_llm():
    """When include_narrative=True, rehydrate calls LLM for narrative."""
    from src.api.routes.search import RehydrateRequest, rehydrate_context

    body = RehydrateRequest(
        since="2026-01-01T00:00:00",
        until="2026-01-31T23:59:59",
        include_narrative=True,
    )

    mock_qdrant = MagicMock()
    mock_qdrant.scroll_time_range = AsyncMock(
        return_value=[
            ("id-1", _make_payload("Memory about Docker config", created_at="2026-01-15T12:00:00")),
            ("id-2", _make_payload("Redis runs on port 6379", created_at="2026-01-15T13:00:00")),
        ]
    )

    mock_redis = MagicMock()
    mock_redis.client = MagicMock()
    mock_redis.client.get = AsyncMock(return_value=None)  # cache miss
    mock_redis.client.setex = AsyncMock()

    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(
        return_value="This session covered Docker configuration and Redis setup."
    )

    mock_request = MagicMock()

    with (
        patch(
            "src.storage.get_qdrant_store",
            new_callable=AsyncMock,
            return_value=mock_qdrant,
        ),
        patch("src.storage.get_redis_store", new_callable=AsyncMock, return_value=mock_redis),
        patch("src.core.llm.get_llm", new_callable=AsyncMock, return_value=mock_llm),
    ):
        response = await rehydrate_context(request=mock_request, body=body)

    assert response.narrative is not None
    assert "Docker" in response.narrative
    mock_llm.generate.assert_called_once()


@pytest.mark.asyncio
async def test_rehydrate_cache_hit_skips_qdrant():
    """Redis cache hit returns cached response without querying Qdrant."""
    import json

    from src.api.routes.search import RehydrateRequest, rehydrate_context

    body = RehydrateRequest(
        since="2026-01-01T00:00:00",
        until="2026-01-31T23:59:59",
    )

    cached_response = {
        "entries": [],
        "total": 0,
        "window_start": "2026-01-01T00:00:00",
        "window_end": "2026-01-31T23:59:59",
        "narrative": None,
    }

    mock_redis = MagicMock()
    mock_redis.client = MagicMock()
    mock_redis.client.get = AsyncMock(return_value=json.dumps(cached_response))

    mock_qdrant = MagicMock()
    mock_qdrant.scroll_time_range = AsyncMock()

    mock_request = MagicMock()

    with (
        patch(
            "src.storage.get_qdrant_store",
            new_callable=AsyncMock,
            return_value=mock_qdrant,
        ),
        patch("src.storage.get_redis_store", new_callable=AsyncMock, return_value=mock_redis),
    ):
        response = await rehydrate_context(request=mock_request, body=body)

    assert response.total == 0
    mock_qdrant.scroll_time_range.assert_not_called()


@pytest.mark.asyncio
async def test_rehydrate_no_narrative_skips_llm():
    """When include_narrative=False, LLM is not called."""
    from src.api.routes.search import RehydrateRequest, rehydrate_context

    body = RehydrateRequest(
        since="2026-01-01T00:00:00",
        until="2026-01-31T23:59:59",
        include_narrative=False,
    )

    mock_qdrant = MagicMock()
    mock_qdrant.scroll_time_range = AsyncMock(
        return_value=[
            ("id-1", _make_payload("Some memory", created_at="2026-01-15T12:00:00")),
        ]
    )

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
        patch("src.storage.get_redis_store", new_callable=AsyncMock, return_value=mock_redis),
    ):
        response = await rehydrate_context(request=mock_request, body=body)

    assert response.narrative is None
    assert response.total == 1


# ---- Task 3: anti-pattern inclusion ----


@pytest.mark.asyncio
async def test_rehydrate_includes_anti_patterns():
    """When include_anti_patterns=True, anti-pattern entries appear with flag."""
    from src.api.routes.search import RehydrateRequest, rehydrate_context

    body = RehydrateRequest(
        since="2026-01-01T00:00:00",
        until="2026-01-31T23:59:59",
        include_anti_patterns=True,
    )

    mock_qdrant = MagicMock()
    mock_qdrant.scroll_time_range = AsyncMock(
        return_value=[
            ("id-1", _make_payload("Normal memory", created_at="2026-01-15T12:00:00")),
        ]
    )
    # Anti-pattern scroll uses the anti_patterns_collection attribute
    mock_qdrant.anti_patterns_collection = "recall_memories_anti_patterns"
    mock_qdrant.client = MagicMock()
    mock_qdrant.client.scroll = AsyncMock(
        return_value=(
            [
                MagicMock(
                    id="ap-1",
                    payload={
                        **_make_payload(
                            "Never use sudo in containers",
                            domain="infrastructure",
                            memory_type="warning",
                            created_at="2026-01-10T08:00:00",
                        ),
                        "warning": "Never use sudo in containers",
                        "pattern": "sudo usage in Dockerfiles",
                    },
                )
            ],
            None,
        )
    )

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
        patch("src.storage.get_redis_store", new_callable=AsyncMock, return_value=mock_redis),
    ):
        response = await rehydrate_context(request=mock_request, body=body)

    assert response.total == 2
    anti_entries = [e for e in response.entries if e.is_anti_pattern]
    assert len(anti_entries) == 1
    assert "sudo" in anti_entries[0].summary


@pytest.mark.asyncio
async def test_rehydrate_excludes_anti_patterns_by_default():
    """Default include_anti_patterns=False does not query anti-pattern collection."""
    from src.api.routes.search import RehydrateRequest, rehydrate_context

    body = RehydrateRequest(
        since="2026-01-01T00:00:00",
        until="2026-01-31T23:59:59",
    )

    mock_qdrant = MagicMock()
    mock_qdrant.scroll_time_range = AsyncMock(
        return_value=[
            ("id-1", _make_payload("Normal memory", created_at="2026-01-15T12:00:00")),
        ]
    )

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
        patch("src.storage.get_redis_store", new_callable=AsyncMock, return_value=mock_redis),
    ):
        response = await rehydrate_context(request=mock_request, body=body)

    assert response.total == 1
    anti_entries = [e for e in response.entries if e.is_anti_pattern]
    assert len(anti_entries) == 0
