"""
Unit tests for the retrieval reranker inference module.
"""

import math
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.models import Durability, Memory, MemoryType, MemorySource, RetrievalResult
from src.core.reranker import (
    FEATURE_NAMES,
    RerankerModel,
    extract_features,
    get_reranker,
    sigmoid,
)


def _make_memory(**overrides) -> Memory:
    """Create a test memory with sensible defaults."""
    defaults = {
        "content": "test memory content",
        "memory_type": MemoryType.SEMANTIC,
        "source": MemorySource.USER,
        "domain": "testing",
        "importance": 0.5,
        "stability": 0.5,
        "confidence": 0.8,
        "access_count": 5,
        "pinned": False,
        "durability": Durability.DURABLE,
        "created_at": datetime.utcnow() - timedelta(hours=48),
        "updated_at": datetime.utcnow() - timedelta(hours=24),
        "last_accessed": datetime.utcnow() - timedelta(hours=2),
    }
    defaults.update(overrides)
    return Memory(**defaults)


def _make_result(memory: Memory, similarity: float = 0.7, graph_distance: int = 0) -> RetrievalResult:
    return RetrievalResult(
        memory=memory,
        score=similarity,
        similarity=similarity,
        graph_distance=graph_distance,
    )


class TestExtractFeatures:
    def test_length(self):
        """extract_features returns exactly 11 features."""
        memory = _make_memory()
        features = extract_features(memory, similarity=0.8, has_graph_path=False, retrieval_path_len=0)
        assert len(features) == 11
        assert len(features) == len(FEATURE_NAMES)

    def test_value_ranges(self):
        """All feature values are within expected bounds."""
        memory = _make_memory(
            importance=0.9,
            stability=0.7,
            confidence=0.95,
            access_count=100,
            pinned=True,
            durability=Durability.PERMANENT,
        )
        features = extract_features(memory, similarity=0.85, has_graph_path=True, retrieval_path_len=2)

        # importance (0-1)
        assert 0.0 <= features[0] <= 1.0
        # stability (0-1)
        assert 0.0 <= features[1] <= 1.0
        # confidence (0-1)
        assert 0.0 <= features[2] <= 1.0
        # log1p(access_count) >= 0
        assert features[3] >= 0.0
        assert features[3] == pytest.approx(math.log1p(100))
        # hours_since_last_access (capped at 720)
        assert 0.0 <= features[4] <= 720.0
        # hours_since_creation (capped at 8760)
        assert 0.0 <= features[5] <= 8760.0
        # is_pinned
        assert features[6] == 1.0
        # durability_score
        assert features[7] == 1.0
        # similarity
        assert features[8] == 0.85
        # has_graph_path
        assert features[9] == 1.0
        # retrieval_path_len
        assert features[10] == 2.0

    def test_hours_capped(self):
        """Hours features are capped at their max values."""
        memory = _make_memory(
            created_at=datetime.utcnow() - timedelta(days=400),
            last_accessed=datetime.utcnow() - timedelta(days=60),
        )
        features = extract_features(memory, similarity=0.5, has_graph_path=False, retrieval_path_len=0)
        assert features[4] == 720.0  # hours_since_last_access capped
        assert features[5] == 8760.0  # hours_since_creation capped


class TestDurabilityMapping:
    def test_ephemeral(self):
        memory = _make_memory(durability=Durability.EPHEMERAL)
        features = extract_features(memory, 0.5, False, 0)
        assert features[7] == 0.0

    def test_durable(self):
        memory = _make_memory(durability=Durability.DURABLE)
        features = extract_features(memory, 0.5, False, 0)
        assert features[7] == 0.5

    def test_permanent(self):
        memory = _make_memory(durability=Durability.PERMANENT)
        features = extract_features(memory, 0.5, False, 0)
        assert features[7] == 1.0

    def test_none_defaults_to_durable(self):
        memory = _make_memory(durability=None)
        features = extract_features(memory, 0.5, False, 0)
        assert features[7] == 0.5


class TestPinnedEncoding:
    def test_pinned_true(self):
        memory = _make_memory(pinned=True)
        features = extract_features(memory, 0.5, False, 0)
        assert features[6] == 1.0

    def test_pinned_false(self):
        memory = _make_memory(pinned=False)
        features = extract_features(memory, 0.5, False, 0)
        assert features[6] == 0.0


class TestSigmoid:
    def test_zero_maps_to_half(self):
        assert sigmoid(0) == pytest.approx(0.5)

    def test_large_positive(self):
        assert sigmoid(100) == pytest.approx(1.0, abs=1e-6)

    def test_large_negative(self):
        assert sigmoid(-100) == pytest.approx(0.0, abs=1e-6)

    def test_monotonic(self):
        assert sigmoid(-2) < sigmoid(0) < sigmoid(2)

    def test_symmetry(self):
        assert sigmoid(3) + sigmoid(-3) == pytest.approx(1.0)


class TestRerankerModel:
    def test_predict_with_zero_weights(self):
        """Zero weights + zero bias → sigmoid(0) = 0.5."""
        model = RerankerModel(weights=[0.0] * 11, bias=0.0)
        features = [0.5] * 11
        assert model.predict(features) == pytest.approx(0.5)

    def test_predict_with_positive_bias(self):
        """Large positive bias → score near 1.0."""
        model = RerankerModel(weights=[0.0] * 11, bias=10.0)
        features = [0.0] * 11
        assert model.predict(features) > 0.99

    def test_score_results_blending(self):
        """score_results applies 0.7 * ML + 0.3 * similarity blend."""
        # Model always predicts ~0.5 (zero weights, zero bias)
        model = RerankerModel(weights=[0.0] * 11, bias=0.0)

        memory = _make_memory()
        result = _make_result(memory, similarity=1.0, graph_distance=0)

        model.score_results([result])

        # 0.7 * 0.5 + 0.3 * 1.0 = 0.65
        assert result.score == pytest.approx(0.65, abs=0.01)

    def test_score_results_sorting(self):
        """Results are sorted by score descending after reranking."""
        # Positive weight on importance → higher importance = higher score
        weights = [5.0] + [0.0] * 10
        model = RerankerModel(weights=weights, bias=0.0)

        low = _make_result(_make_memory(importance=0.1), similarity=0.5)
        high = _make_result(_make_memory(importance=0.9), similarity=0.5)

        results = model.score_results([low, high])
        assert results[0].memory.importance > results[1].memory.importance


class TestGetReranker:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_model(self):
        """get_reranker returns None when Redis key doesn't exist."""
        redis_store = MagicMock()
        redis_store.client = AsyncMock()
        redis_store.client.get = AsyncMock(return_value=None)

        result = await get_reranker(redis_store)
        assert result is None

    @pytest.mark.asyncio
    async def test_loads_model_from_redis(self):
        """get_reranker deserializes weights from Redis JSON."""
        import json
        model_data = json.dumps({
            "features": FEATURE_NAMES,
            "weights": [0.1] * 11,
            "bias": -0.5,
            "trained_at": "2026-02-18T00:00:00",
            "n_samples": 100,
            "cv_score": 0.82,
        })

        redis_store = MagicMock()
        redis_store.client = AsyncMock()
        redis_store.client.get = AsyncMock(return_value=model_data)

        model = await get_reranker(redis_store)
        assert model is not None
        assert len(model.weights) == 11
        assert model.bias == -0.5
        assert model.metadata["n_samples"] == 100

    @pytest.mark.asyncio
    async def test_returns_none_on_corrupt_json(self):
        """get_reranker returns None gracefully on bad Redis data."""
        redis_store = MagicMock()
        redis_store.client = AsyncMock()
        redis_store.client.get = AsyncMock(return_value="not valid json{{{")

        result = await get_reranker(redis_store)
        assert result is None


class TestFallbackBehavior:
    def test_legacy_formula_when_no_reranker(self):
        """Verify _rank_results uses legacy formula when reranker is None.

        Source-level check: _rank_results accepts reranker param and has
        'if reranker is not None' guard.
        """
        from pathlib import Path
        source = Path("src/core/retrieval.py").read_text()
        assert "def _rank_results(" in source
        assert "reranker=None" in source
        assert "if reranker is not None" in source
        # Legacy formula still present
        assert "recency_factor" in source
        assert "stability_factor" in source
        assert "confidence_factor" in source
