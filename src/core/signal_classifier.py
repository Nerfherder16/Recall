"""
Signal classifier inference module.

Pure-math TF-IDF + logistic regression classifier — no sklearn dependency.
Weights loaded from Redis (trained by signal_classifier_trainer.py).

Two classifiers:
1. Binary: is this conversation a signal? (gates LLM call)
2. Type: what kind of signal? (error_fix, decision, pattern, etc.)
"""

import json
import math
import re
from typing import Any

import structlog

from .reranker import sigmoid

logger = structlog.get_logger()

REDIS_KEY = "recall:ml:signal_classifier_weights"

SIGNAL_TYPES = [
    "error_fix",
    "decision",
    "pattern",
    "preference",
    "fact",
    "workflow",
    "contradiction",
    "warning",
]

CONV_FEATURE_NAMES = [
    "turn_count",
    "total_char_count",
    "avg_turn_length",
    "question_density",
    "code_density",
    "user_turn_ratio",
    "has_error_keywords",
    "has_decision_keywords",
]

_CODE_PATTERNS = re.compile(
    r"`|def\s|function\s|import\s|class\s|const\s|let\s|var\s|=>\s|"
    r"\bif\s*\(|\bfor\s*\(|\breturn\s|\.py\b|\.js\b|\.ts\b"
)
_ERROR_KEYWORDS = re.compile(
    r"\b(error|fix|bug|crash|fail|broke|exception|traceback|stack\s*trace|"
    r"not\s+working|issue|problem|debug)\b",
    re.IGNORECASE,
)
_DECISION_KEYWORDS = re.compile(
    r"\b(decide|decision|let\'?s\s+go\s+with|recommend|choose|prefer|"
    r"approach|strategy|option|trade-?off|we\s+should)\b",
    re.IGNORECASE,
)


def _tokenize(text: str) -> list[str]:
    """Simple whitespace/punctuation tokenizer."""
    return [t for t in re.split(r"\W+", text.lower()) if len(t) > 1]


def tfidf_transform(
    text: str,
    vocab: dict[str, int],
    idf_weights: list[float],
) -> list[float]:
    """
    Pure-math TF-IDF from baked vocabulary and IDF weights.

    Returns L2-normalized TF-IDF vector of len(vocab).
    """
    tokens = _tokenize(text)
    if not tokens:
        return [0.0] * len(vocab)

    # Term frequency
    tf: dict[str, int] = {}
    for token in tokens:
        if token in vocab:
            tf[token] = tf.get(token, 0) + 1

    # TF-IDF with L2 normalization
    vec = [0.0] * len(vocab)
    for token, count in tf.items():
        idx = vocab[token]
        vec[idx] = (1.0 + math.log(count)) * idf_weights[idx]

    # L2 normalize
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]

    return vec


def extract_conversation_features(turns: list[dict[str, str]]) -> list[float]:
    """
    Extract 8 hand-crafted conversation-level features.

    Args:
        turns: list of dicts with 'role' and 'content' keys
    """
    if not turns:
        return [0.0] * len(CONV_FEATURE_NAMES)

    turn_count = len(turns)
    total_chars = sum(len(t.get("content", "")) for t in turns)
    avg_turn_length = total_chars / turn_count if turn_count > 0 else 0.0

    # Question density: fraction of turns containing '?'
    questions = sum(1 for t in turns if "?" in t.get("content", ""))
    question_density = questions / turn_count

    # Code density: fraction of turns with code-like patterns
    code_turns = sum(1 for t in turns if _CODE_PATTERNS.search(t.get("content", "")))
    code_density = code_turns / turn_count

    # User turn ratio
    user_turns = sum(1 for t in turns if t.get("role") == "user")
    user_turn_ratio = user_turns / turn_count

    # Keyword presence (binary, across all turns)
    all_text = " ".join(t.get("content", "") for t in turns)
    has_error = 1.0 if _ERROR_KEYWORDS.search(all_text) else 0.0
    has_decision = 1.0 if _DECISION_KEYWORDS.search(all_text) else 0.0

    return [
        float(turn_count),
        float(total_chars),
        avg_turn_length,
        question_density,
        code_density,
        user_turn_ratio,
        has_error,
        has_decision,
    ]


class SignalClassifier:
    """TF-IDF + logistic regression signal classifier with baked-in weights."""

    def __init__(
        self,
        vocab: dict[str, int],
        idf_weights: list[float],
        binary_weights: list[float],
        binary_bias: float,
        type_classes: list[str],
        type_weights: list[list[float]],
        type_biases: list[float],
        metadata: dict[str, Any] | None = None,
    ):
        self.vocab = vocab
        self.idf_weights = idf_weights
        self.binary_weights = binary_weights
        self.binary_bias = binary_bias
        self.type_classes = type_classes
        self.type_weights = type_weights
        self.type_biases = type_biases
        self.metadata = metadata or {}

    def predict(self, turns: list[dict[str, str]]) -> dict[str, Any]:
        """
        Predict whether conversation turns contain a signal.

        Returns dict with:
            is_signal: bool
            signal_probability: float (0-1)
            predicted_type: str | None
            type_probabilities: dict[str, float]
        """
        # Combine all turn content for TF-IDF
        all_text = " ".join(t.get("content", "") for t in turns)
        tfidf_vec = tfidf_transform(all_text, self.vocab, self.idf_weights)
        conv_features = extract_conversation_features(turns)

        # Combined feature vector
        features = tfidf_vec + conv_features

        # Binary classification
        dot = sum(w * f for w, f in zip(self.binary_weights, features)) + self.binary_bias
        signal_prob = sigmoid(dot)
        is_signal = signal_prob > 0.5

        # Type classification (only if signal detected)
        type_probs: dict[str, float] = {}
        predicted_type: str | None = None

        if is_signal and self.type_classes:
            best_score = -float("inf")
            for i, cls in enumerate(self.type_classes):
                score = (
                    sum(w * f for w, f in zip(self.type_weights[i], features)) + self.type_biases[i]
                )
                prob = sigmoid(score)
                type_probs[cls] = round(prob, 4)
                if score > best_score:
                    best_score = score
                    predicted_type = cls

        return {
            "is_signal": is_signal,
            "signal_probability": round(signal_prob, 4),
            "predicted_type": predicted_type,
            "type_probabilities": type_probs,
        }


import time as _time  # noqa: E402 — needed for cache TTL

_CACHE_TTL = 60  # seconds
_cached_classifier: SignalClassifier | None = None
_classifier_cached_at: float = 0.0
_classifier_cache_populated: bool = False


def invalidate_classifier_cache() -> None:
    """Clear the in-process classifier cache, forcing next call to hit Redis."""
    global _cached_classifier, _classifier_cached_at, _classifier_cache_populated
    _cached_classifier = None
    _classifier_cached_at = 0.0
    _classifier_cache_populated = False


async def get_signal_classifier(redis_store) -> SignalClassifier | None:
    """Load signal classifier from Redis with 60s in-process cache."""
    global _cached_classifier, _classifier_cached_at, _classifier_cache_populated

    now = _time.monotonic()
    if _classifier_cache_populated and (now - _classifier_cached_at) < _CACHE_TTL:
        return _cached_classifier

    try:
        raw = await redis_store.client.get(REDIS_KEY)
        if not raw:
            _cached_classifier = None
            _classifier_cached_at = _time.monotonic()
            _classifier_cache_populated = True
            return None

        data = json.loads(raw)

        # Validate required keys
        if not all(k in data for k in ("vocab", "idf_weights", "binary")):
            logger.warning("signal_classifier_missing_keys")
            _cached_classifier = None
            _classifier_cached_at = _time.monotonic()
            _classifier_cache_populated = True
            return None

        binary = data["binary"]
        type_cls = data.get("type_classifier", {})

        model = SignalClassifier(
            vocab=data["vocab"],
            idf_weights=data["idf_weights"],
            binary_weights=binary["weights"],
            binary_bias=binary["bias"],
            type_classes=type_cls.get("classes", []),
            type_weights=type_cls.get("weights", []),
            type_biases=type_cls.get("biases", []),
            metadata={
                "trained_at": data.get("trained_at"),
                "n_samples": data.get("n_samples"),
                "binary_cv_score": data.get("binary_cv_score"),
                "type_cv_score": data.get("type_cv_score"),
                "version": data.get("version"),
            },
        )
        _cached_classifier = model
        _classifier_cached_at = _time.monotonic()
        _classifier_cache_populated = True
        return model
    except Exception as e:
        logger.warning("signal_classifier_load_failed", error=str(e))
        return None
