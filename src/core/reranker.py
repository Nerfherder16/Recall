"""
Reranker inference module.

Pure-math logistic regression scoring — no sklearn dependency.
Weights loaded from Redis (trained by reranker_trainer.py).
"""

import json
import math
from datetime import datetime
from typing import Any

import structlog

from .models import Durability, Memory, RetrievalResult

logger = structlog.get_logger()

REDIS_KEY = "recall:ml:reranker_weights"

DURABILITY_SCORES = {
    Durability.EPHEMERAL: 0.0,
    Durability.DURABLE: 0.5,
    Durability.PERMANENT: 1.0,
}

FEATURE_NAMES = [
    "importance",
    "stability",
    "confidence",
    "log1p_access_count",
    "hours_since_last_access",
    "hours_since_creation",
    "is_pinned",
    "durability_score",
    "similarity",
    "has_graph_path",
    "retrieval_path_len",
]


def extract_features(
    memory: Memory,
    similarity: float,
    has_graph_path: bool,
    retrieval_path_len: int,
) -> list[float]:
    """Extract 11 features from a memory + retrieval context."""
    now = datetime.utcnow()

    hours_since_access = (now - memory.last_accessed).total_seconds() / 3600
    hours_since_creation = (now - memory.created_at).total_seconds() / 3600

    durability = memory.durability or Durability.DURABLE
    durability_score = DURABILITY_SCORES.get(durability, 0.5)

    return [
        memory.importance,
        memory.stability,
        memory.confidence,
        math.log1p(memory.access_count),
        min(hours_since_access, 720.0),
        min(hours_since_creation, 8760.0),
        1.0 if memory.pinned else 0.0,
        durability_score,
        similarity,
        1.0 if has_graph_path else 0.0,
        float(retrieval_path_len),
    ]


def sigmoid(x: float) -> float:
    """Numerically stable sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    exp_x = math.exp(x)
    return exp_x / (1.0 + exp_x)


class RerankerModel:
    """Logistic regression reranker with baked-in scaler weights."""

    def __init__(self, weights: list[float], bias: float, metadata: dict[str, Any] | None = None):
        self.weights = weights
        self.bias = bias
        self.metadata = metadata or {}

    def predict(self, features: list[float]) -> float:
        """Compute P(useful) via sigmoid(w·x + b)."""
        dot = sum(w * f for w, f in zip(self.weights, features)) + self.bias
        return sigmoid(dot)

    def score_results(self, results: list[RetrievalResult]) -> list[RetrievalResult]:
        """Re-score results using ML prediction blended with similarity."""
        for result in results:
            has_graph = len(result.retrieval_path) > 1
            path_len = len(result.retrieval_path)

            features = extract_features(
                result.memory,
                result.similarity,
                has_graph,
                path_len,
            )
            ml_score = self.predict(features)

            # Blend: 70% ML prediction, 30% raw similarity
            result.score = 0.7 * ml_score + 0.3 * result.similarity

        results.sort(key=lambda r: r.score, reverse=True)
        return results


import time as _time  # noqa: E402 — needed for cache TTL

_CACHE_TTL = 60  # seconds
_cached_reranker: RerankerModel | None = None
_reranker_cached_at: float = 0.0
_reranker_cache_populated: bool = False


def invalidate_reranker_cache() -> None:
    """Clear the in-process reranker cache, forcing next call to hit Redis."""
    global _cached_reranker, _reranker_cached_at, _reranker_cache_populated
    _cached_reranker = None
    _reranker_cached_at = 0.0
    _reranker_cache_populated = False


async def get_reranker(redis_store) -> RerankerModel | None:
    """Load reranker from Redis with 60s in-process cache."""
    global _cached_reranker, _reranker_cached_at, _reranker_cache_populated

    now = _time.monotonic()
    if _reranker_cache_populated and (now - _reranker_cached_at) < _CACHE_TTL:
        return _cached_reranker

    try:
        raw = await redis_store.client.get(REDIS_KEY)
        if not raw:
            _cached_reranker = None
            _reranker_cached_at = _time.monotonic()
            _reranker_cache_populated = True
            return None

        data = json.loads(raw)
        model = RerankerModel(
            weights=data["weights"],
            bias=data["bias"],
            metadata={
                "trained_at": data.get("trained_at"),
                "n_samples": data.get("n_samples"),
                "cv_score": data.get("cv_score"),
                "features": data.get("features", FEATURE_NAMES),
            },
        )
        _cached_reranker = model
        _reranker_cached_at = _time.monotonic()
        _reranker_cache_populated = True
        return model
    except Exception as e:
        logger.warning("reranker_load_failed", error=str(e))
        return None
