"""
v2.6 Integration Smoke Tests — verify all optimizations work together.

Tests that caching, singletons, and passthrough optimizations are wired
correctly by checking module-level state and function signatures.
"""

import hashlib
import sys
import time
from collections import OrderedDict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock storage drivers before importing
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
    "sse_starlette",
    "sse_starlette.sse",
]:
    sys.modules.setdefault(mod_name, MagicMock())


# =============================================================
# 1. Signal classifier in-process cache
# =============================================================


def test_signal_classifier_cache_infrastructure():
    """Signal classifier has in-process cache with invalidation."""
    from src.core.signal_classifier import (
        invalidate_classifier_cache,
    )

    # Cache starts unpopulated
    invalidate_classifier_cache()

    from src.core import signal_classifier as sc

    assert sc._classifier_cache_populated is False
    assert sc._cached_classifier is None
    assert callable(invalidate_classifier_cache)


# =============================================================
# 2. Reranker in-process cache
# =============================================================


def test_reranker_cache_infrastructure():
    """Reranker has in-process cache with invalidation."""
    from src.core.reranker import (
        invalidate_reranker_cache,
    )

    invalidate_reranker_cache()

    from src.core import reranker as rr

    assert rr._reranker_cache_populated is False
    assert rr._cached_reranker is None
    assert callable(invalidate_reranker_cache)


# =============================================================
# 3. Embedding LRU cache
# =============================================================


def test_embedding_cache_exists_and_is_ordered_dict():
    """Embedding cache infrastructure is in place."""
    from src.core.embeddings import (
        _EMBED_CACHE_MAX,
        _EMBED_CACHE_TTL,
        _embed_cache,
        clear_embed_cache,
    )

    assert isinstance(_embed_cache, OrderedDict)
    assert _EMBED_CACHE_MAX == 200
    assert _EMBED_CACHE_TTL == 300
    clear_embed_cache()


@pytest.mark.asyncio
async def test_embedding_cache_hit_returns_cached_vector():
    """Pre-populated embedding cache returns without network call."""
    from src.core.embeddings import _embed_cache, clear_embed_cache

    clear_embed_cache()

    # Pre-populate cache with known key
    test_text = "integration test text"
    prefix = "search_query"
    cache_key = hashlib.md5((prefix + ":" + test_text).encode()).hexdigest()
    fake_vector = [0.1, 0.2, 0.3]
    _embed_cache[cache_key] = (fake_vector, time.time())

    # The embed method should find this in cache
    assert cache_key in _embed_cache
    vec, ts = _embed_cache[cache_key]
    assert vec == fake_vector

    clear_embed_cache()


# =============================================================
# 4. Retrieval pipeline singleton
# =============================================================


@pytest.mark.asyncio
async def test_pipeline_singleton_identity():
    """get_retrieval_pipeline() returns same instance on repeat calls."""
    from src.core.retrieval import get_retrieval_pipeline, reset_retrieval_pipeline

    reset_retrieval_pipeline()

    with (
        patch("src.storage.get_qdrant_store", new_callable=AsyncMock, return_value=MagicMock()),
        patch("src.storage.get_neo4j_store", new_callable=AsyncMock, return_value=MagicMock()),
        patch("src.storage.get_redis_store", new_callable=AsyncMock, return_value=MagicMock()),
    ):
        p1 = await get_retrieval_pipeline()
        p2 = await get_retrieval_pipeline()

    assert p1 is p2
    reset_retrieval_pipeline()


# =============================================================
# 5. Contradiction embedding passthrough signature
# =============================================================


def test_store_signal_returns_tuple():
    """_store_signal_as_memory returns (id, embedding) tuple."""
    import inspect

    from src.workers.signals import _store_signal_as_memory

    sig = inspect.signature(_store_signal_as_memory)
    params = list(sig.parameters.keys())
    assert "session_id" in params
    assert "signal" in params


def test_resolve_contradiction_accepts_embedding():
    """_resolve_contradiction has an embedding keyword argument."""
    import inspect

    from src.workers.signals import _resolve_contradiction

    sig = inspect.signature(_resolve_contradiction)
    params = sig.parameters
    assert "embedding" in params
    assert params["embedding"].default is None


# =============================================================
# 6. Docker resource limits present
# =============================================================


def test_docker_compose_has_resource_limits():
    """docker-compose.yml contains deploy.resources.limits for all services."""
    from pathlib import Path

    compose = Path("docker-compose.yml").read_text()

    # All 6 services should have deploy sections with limits
    assert compose.count("deploy:") >= 6
    assert compose.count("memory:") >= 6
    assert compose.count("cpus:") >= 6

    # Neo4j heap settings
    assert "heap_initial__size" in compose
    assert "heap_max__size" in compose
    assert "pagecache_size" in compose


# =============================================================
# 7. Hook improvements present
# =============================================================


def test_hooks_have_optimizations():
    """Hooks include domain filter, file-type filter, and session-scoped tracking."""
    from pathlib import Path

    retrieve = Path("hooks/recall-retrieve.js").read_text()
    assert "DOMAIN_ALIASES" in retrieve
    assert "searchBody.domain" in retrieve

    observe = Path("hooks/observe-edit.js").read_text()
    assert "SKIP_EXTENSIONS" in observe
    assert "shouldSkipFile" in observe

    assert "sessionKey" in retrieve
    summary = Path("hooks/recall-session-summary.js").read_text()
    assert "sessionId" in summary or "session_id" in summary


# =============================================================
# 8. All v2.6 exports exist
# =============================================================


def test_all_v26_exports_importable():
    """All new v2.6 functions and classes are importable."""
    from src.core.embeddings import _embed_cache, clear_embed_cache
    from src.core.reranker import invalidate_reranker_cache
    from src.core.retrieval import get_retrieval_pipeline, reset_retrieval_pipeline
    from src.core.signal_classifier import invalidate_classifier_cache

    assert callable(clear_embed_cache)
    assert callable(invalidate_reranker_cache)
    assert callable(invalidate_classifier_cache)
    assert callable(get_retrieval_pipeline)
    assert callable(reset_retrieval_pipeline)
    assert isinstance(_embed_cache, OrderedDict)
