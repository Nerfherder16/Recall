"""
Tests for contradiction embedding passthrough in signal pipeline.

Verifies:
- _store_signal_as_memory returns (memory_id, embedding) tuple
- _resolve_contradiction receives embedding without re-embedding
- Only one embed() call total for a contradiction signal
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock drivers not installed locally
for mod in [
    "neo4j",
    "neo4j.exceptions",
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
    sys.modules.setdefault(mod, MagicMock())

from src.core.models import SignalType  # noqa: E402
from src.workers.signals import (  # noqa: E402
    _resolve_contradiction,
    _store_signal_as_memory,
)


def _make_signal(signal_type=SignalType.FACT, content="Test fact content"):
    """Create a mock DetectedSignal."""
    sig = MagicMock()
    sig.signal_type = signal_type
    sig.content = content
    sig.confidence = 0.9
    sig.suggested_domain = "development"
    sig.suggested_tags = ["test"]
    sig.suggested_importance = 0.7
    sig.suggested_durability = "durable"
    return sig


class TestEmbeddingPassthrough:
    @pytest.mark.asyncio
    async def test_store_returns_memory_id_and_embedding(self):
        """_store_signal_as_memory should return (memory_id, embedding) tuple."""
        fake_vec = [0.1, 0.2, 0.3]
        embed_mock = AsyncMock(return_value=fake_vec)
        embed_svc = AsyncMock()
        embed_svc.embed = embed_mock

        qdrant = AsyncMock()
        qdrant.find_by_content_hash = AsyncMock(return_value=None)
        qdrant.search = AsyncMock(return_value=[])
        qdrant.store = AsyncMock()

        neo4j = AsyncMock()
        neo4j.create_memory_node = AsyncMock()

        pg = AsyncMock()
        pg.log_audit = AsyncMock()

        with (
            patch("src.workers.signals.get_embedding_service", return_value=embed_svc),
            patch("src.workers.signals.get_qdrant_store", return_value=qdrant),
            patch("src.workers.signals.get_neo4j_store", return_value=neo4j),
            patch("src.workers.signals.get_postgres_store", return_value=pg),
            patch("src.core.auto_linker.auto_link_memory", new_callable=AsyncMock),
        ):
            signal = _make_signal()
            result = await _store_signal_as_memory("sess-1", signal)

        # Should return a tuple of (memory_id, embedding)
        assert isinstance(result, tuple)
        assert len(result) == 2
        mem_id, embedding = result
        assert mem_id is not None
        assert embedding == fake_vec

    @pytest.mark.asyncio
    async def test_resolve_contradiction_uses_passed_embedding(self):
        """_resolve_contradiction should use the passed embedding, not re-embed."""
        fake_vec = [0.1, 0.2, 0.3]

        embed_svc = AsyncMock()
        embed_svc.embed = AsyncMock()

        qdrant = AsyncMock()
        qdrant.search = AsyncMock(
            return_value=[
                ("other-mem", 0.85, {"superseded_by": None}),
            ]
        )
        qdrant.mark_superseded = AsyncMock()

        neo4j = AsyncMock()
        neo4j.create_relationship = AsyncMock()
        neo4j.mark_superseded = AsyncMock()

        signal = _make_signal(signal_type=SignalType.CONTRADICTION)

        with (
            patch("src.workers.signals.get_embedding_service", return_value=embed_svc),
            patch("src.workers.signals.get_qdrant_store", return_value=qdrant),
            patch("src.workers.signals.get_neo4j_store", return_value=neo4j),
        ):
            await _resolve_contradiction("new-mem", signal, embedding=fake_vec)

        # Should NOT have called embed (embedding was passed in)
        embed_svc.embed.assert_not_called()
        # Should have used the passed embedding for search
        qdrant.search.assert_called_once()
        call_kwargs = qdrant.search.call_args
        assert call_kwargs[1]["query_vector"] == fake_vec or call_kwargs[0][0] == fake_vec

    @pytest.mark.asyncio
    async def test_contradiction_signal_only_embeds_once(self):
        """Full pipeline: contradiction signal should embed content exactly once."""
        fake_vec = [0.1, 0.2, 0.3]
        embed_call_count = 0

        async def counting_embed(text, prefix="passage"):
            nonlocal embed_call_count
            embed_call_count += 1
            return fake_vec

        embed_svc = AsyncMock()
        embed_svc.embed = counting_embed

        qdrant = AsyncMock()
        qdrant.find_by_content_hash = AsyncMock(return_value=None)
        qdrant.store = AsyncMock()
        qdrant.search = AsyncMock(
            return_value=[
                ("old-mem", 0.85, {"superseded_by": None}),
            ]
        )
        qdrant.mark_superseded = AsyncMock()

        neo4j = AsyncMock()
        neo4j.create_memory_node = AsyncMock()
        neo4j.create_relationship = AsyncMock()
        neo4j.mark_superseded = AsyncMock()

        pg = AsyncMock()
        pg.log_audit = AsyncMock()

        signal = _make_signal(signal_type=SignalType.CONTRADICTION)

        with (
            patch("src.workers.signals.get_embedding_service", return_value=embed_svc),
            patch("src.workers.signals.get_qdrant_store", return_value=qdrant),
            patch("src.workers.signals.get_neo4j_store", return_value=neo4j),
            patch("src.workers.signals.get_postgres_store", return_value=pg),
            patch("src.core.auto_linker.auto_link_memory", new_callable=AsyncMock),
        ):
            result = await _store_signal_as_memory("sess-1", signal)
            mem_id, embedding = result
            await _resolve_contradiction(mem_id, signal, embedding=embedding)

        # Only ONE embed call total
        assert embed_call_count == 1
