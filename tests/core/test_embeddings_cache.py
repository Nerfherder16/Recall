"""
Tests for embedding LRU cache in EmbeddingService.

Verifies:
- Cache hit returns same vector without Ollama call
- TTL expiration forces re-embed
- LRU eviction at max size
- Cache miss calls Ollama
- Different prefixes produce different cache entries
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.embeddings import EmbeddingService


def _make_service():
    """Create an EmbeddingService with mocked settings and HTTP client."""
    with patch("src.core.embeddings.get_settings") as mock_settings:
        settings = MagicMock()
        settings.ollama_host = "http://localhost:11434"
        settings.embedding_model = "qwen3-embedding:0.6b"
        settings.embedding_dimensions = 4
        mock_settings.return_value = settings
        service = EmbeddingService()
    return service


def _mock_ollama_response(service, vector=None):
    """Mock the HTTP client to return a fake embedding."""
    if vector is None:
        vector = [0.1, 0.2, 0.3, 0.4]

    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"embeddings": [vector]}
    service.client.post = AsyncMock(return_value=response)
    return service


class TestEmbeddingCache:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        """Clear the module-level embedding cache before each test."""
        from src.core.embeddings import clear_embed_cache

        clear_embed_cache()
        yield
        clear_embed_cache()

    @pytest.mark.asyncio
    async def test_cache_hit_skips_ollama(self):
        """Second call with same text returns cached vector, no HTTP call."""
        service = _make_service()
        _mock_ollama_response(service, [1.0, 2.0, 3.0, 4.0])

        with patch("src.core.embeddings.get_metrics", return_value=MagicMock()):
            v1 = await service.embed("hello world")
            v2 = await service.embed("hello world")

        assert v1 == v2
        assert v1 == [1.0, 2.0, 3.0, 4.0]
        # Only one HTTP call — second was cached
        assert service.client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_cache_miss_calls_ollama(self):
        """Different texts produce separate Ollama calls."""
        service = _make_service()
        call_count = 0

        async def mock_post(url, json=None, **kwargs):
            nonlocal call_count
            call_count += 1
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {"embeddings": [[float(call_count)] * 4]}
            return response

        service.client.post = mock_post

        with patch("src.core.embeddings.get_metrics", return_value=MagicMock()):
            v1 = await service.embed("text one")
            v2 = await service.embed("text two")

        assert call_count == 2
        assert v1 != v2

    @pytest.mark.asyncio
    async def test_different_prefix_different_cache_key(self):
        """Same text with different prefix should cache separately."""
        service = _make_service()
        _mock_ollama_response(service, [1.0, 2.0, 3.0, 4.0])

        with patch("src.core.embeddings.get_metrics", return_value=MagicMock()):
            await service.embed("hello", prefix="passage")
            await service.embed("hello", prefix="query")

        # Both should call Ollama (different cache keys)
        assert service.client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_cache_ttl_expiration(self):
        """Expired cache entries should trigger a new Ollama call."""
        service = _make_service()
        _mock_ollama_response(service, [1.0, 2.0, 3.0, 4.0])

        import src.core.embeddings as emb_mod

        with patch("src.core.embeddings.get_metrics", return_value=MagicMock()):
            await service.embed("test text")
            assert service.client.post.call_count == 1

            # Manually expire the cache entry
            for key in emb_mod._embed_cache:
                vec, ts = emb_mod._embed_cache[key]
                emb_mod._embed_cache[key] = (vec, ts - emb_mod._EMBED_CACHE_TTL - 1)

            await service.embed("test text")
            assert service.client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_lru_eviction_at_max_size(self):
        """Cache should evict oldest entry when max size is reached."""
        import src.core.embeddings as emb_mod

        old_max = emb_mod._EMBED_CACHE_MAX
        emb_mod._EMBED_CACHE_MAX = 3  # Small cache for testing

        try:
            service = _make_service()
            call_count = 0

            async def mock_post(url, json=None, **kwargs):
                nonlocal call_count
                call_count += 1
                response = MagicMock()
                response.status_code = 200
                response.json.return_value = {"embeddings": [[float(call_count)] * 4]}
                return response

            service.client.post = mock_post

            with patch("src.core.embeddings.get_metrics", return_value=MagicMock()):
                await service.embed("text-A")  # call 1
                await service.embed("text-B")  # call 2
                await service.embed("text-C")  # call 3
                # Cache full: [A, B, C]

                await service.embed("text-D")  # call 4, evicts A
                # Cache: [B, C, D]

                assert call_count == 4

                # text-A was evicted — should re-embed
                await service.embed("text-A")  # call 5
                assert call_count == 5

                # text-C still cached (B was evicted when A was re-added)
                await service.embed("text-C")  # still cached
                assert call_count == 5

        finally:
            emb_mod._EMBED_CACHE_MAX = old_max
