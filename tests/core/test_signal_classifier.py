"""
Unit tests for the signal classifier inference module.
"""

import json
import math
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.signal_classifier import (
    CONV_FEATURE_NAMES,
    SignalClassifier,
    _tokenize,
    extract_conversation_features,
    get_signal_classifier,
    tfidf_transform,
)


def _make_turns(*texts: str, roles: list[str] | None = None) -> list[dict[str, str]]:
    """Create turn dicts from text strings, alternating user/assistant."""
    turns = []
    for i, text in enumerate(texts):
        if roles:
            role = roles[i]
        else:
            role = "user" if i % 2 == 0 else "assistant"
        turns.append({"role": role, "content": text})
    return turns


def _make_classifier(
    vocab: dict[str, int] | None = None,
    idf_weights: list[float] | None = None,
    binary_weights: list[float] | None = None,
    binary_bias: float = 0.0,
    type_classes: list[str] | None = None,
    type_weights: list[list[float]] | None = None,
    type_biases: list[float] | None = None,
) -> SignalClassifier:
    """Create a classifier with sensible defaults for testing."""
    if vocab is None:
        vocab = {"error": 0, "fix": 1, "bug": 2, "hello": 3}
    if idf_weights is None:
        idf_weights = [1.0] * len(vocab)
    n_features = len(vocab) + len(CONV_FEATURE_NAMES)
    if binary_weights is None:
        binary_weights = [0.0] * n_features
    if type_classes is None:
        type_classes = []
    if type_weights is None:
        type_weights = []
    if type_biases is None:
        type_biases = []

    return SignalClassifier(
        vocab=vocab,
        idf_weights=idf_weights,
        binary_weights=binary_weights,
        binary_bias=binary_bias,
        type_classes=type_classes,
        type_weights=type_weights,
        type_biases=type_biases,
    )


class TestTokenize:
    def test_basic(self):
        tokens = _tokenize("Hello World test")
        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens

    def test_filters_single_chars(self):
        tokens = _tokenize("I am a test")
        assert "am" in tokens
        assert "test" in tokens
        # Single-char tokens filtered
        for t in tokens:
            assert len(t) > 1

    def test_empty_string(self):
        assert _tokenize("") == []

    def test_punctuation_split(self):
        tokens = _tokenize("error: fix bug!")
        assert "error" in tokens
        assert "fix" in tokens
        assert "bug" in tokens


class TestTfidfTransform:
    def test_returns_correct_length(self):
        vocab = {"hello": 0, "world": 1, "test": 2}
        idf = [1.0, 1.0, 1.0]
        vec = tfidf_transform("hello world", vocab, idf)
        assert len(vec) == 3

    def test_unknown_tokens_ignored(self):
        vocab = {"hello": 0}
        idf = [1.0]
        vec = tfidf_transform("goodbye world", vocab, idf)
        assert vec == [0.0]

    def test_empty_text(self):
        vocab = {"test": 0}
        idf = [1.0]
        vec = tfidf_transform("", vocab, idf)
        assert vec == [0.0]

    def test_l2_normalized(self):
        vocab = {"hello": 0, "world": 1}
        idf = [1.0, 1.0]
        vec = tfidf_transform("hello world", vocab, idf)
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            assert norm == pytest.approx(1.0, abs=1e-6)

    def test_repeated_term_increases_tf(self):
        vocab = {"error": 0, "fix": 1}
        idf = [1.0, 1.0]
        # "error error fix" should weight error higher than fix
        vec = tfidf_transform("error error fix", vocab, idf)
        # Before normalization, error tf = 1 + log(2), fix tf = 1 + log(1)
        # After L2 norm, error should still be bigger
        assert vec[0] > vec[1]


class TestExtractConversationFeatures:
    def test_returns_correct_length(self):
        turns = _make_turns("hello", "hi there")
        features = extract_conversation_features(turns)
        assert len(features) == len(CONV_FEATURE_NAMES)
        assert len(features) == 8

    def test_empty_turns(self):
        features = extract_conversation_features([])
        assert features == [0.0] * 8

    def test_turn_count(self):
        turns = _make_turns("a", "b", "c")
        features = extract_conversation_features(turns)
        assert features[0] == 3.0  # turn_count

    def test_total_char_count(self):
        turns = _make_turns("hello", "world")
        features = extract_conversation_features(turns)
        assert features[1] == 10.0  # total_char_count

    def test_question_density(self):
        turns = _make_turns("What is this?", "It is a test.", "Why?", "Because.")
        features = extract_conversation_features(turns)
        # 2 out of 4 turns have questions
        assert features[3] == pytest.approx(0.5)

    def test_code_density(self):
        turns = _make_turns(
            "Check `this` code",
            "def foo(): pass",
            "No code here",
        )
        features = extract_conversation_features(turns)
        # 2 out of 3 have code patterns
        assert features[4] == pytest.approx(2 / 3, abs=0.01)

    def test_user_turn_ratio(self):
        turns = _make_turns("user msg", "assistant msg", "user msg")
        features = extract_conversation_features(turns)
        assert features[5] == pytest.approx(2 / 3, abs=0.01)

    def test_error_keywords(self):
        turns = _make_turns("I found a bug in the code")
        features = extract_conversation_features(turns)
        assert features[6] == 1.0  # has_error_keywords

    def test_no_error_keywords(self):
        turns = _make_turns("Everything is running fine")
        features = extract_conversation_features(turns)
        assert features[6] == 0.0

    def test_decision_keywords(self):
        turns = _make_turns("Let's go with option A")
        features = extract_conversation_features(turns)
        assert features[7] == 1.0  # has_decision_keywords

    def test_no_decision_keywords(self):
        turns = _make_turns("Hello there")
        features = extract_conversation_features(turns)
        assert features[7] == 0.0


class TestSignalClassifier:
    def test_predict_returns_expected_keys(self):
        classifier = _make_classifier()
        turns = _make_turns("test message")
        result = classifier.predict(turns)
        assert "is_signal" in result
        assert "signal_probability" in result
        assert "predicted_type" in result
        assert "type_probabilities" in result

    def test_zero_weights_gives_half_probability(self):
        classifier = _make_classifier(binary_bias=0.0)
        turns = _make_turns("test message")
        result = classifier.predict(turns)
        assert result["signal_probability"] == pytest.approx(0.5, abs=0.05)

    def test_large_positive_bias_predicts_signal(self):
        classifier = _make_classifier(binary_bias=10.0)
        turns = _make_turns("anything")
        result = classifier.predict(turns)
        assert result["is_signal"] is True
        assert result["signal_probability"] > 0.99

    def test_large_negative_bias_predicts_no_signal(self):
        classifier = _make_classifier(binary_bias=-10.0)
        turns = _make_turns("anything")
        result = classifier.predict(turns)
        assert result["is_signal"] is False
        assert result["signal_probability"] < 0.01

    def test_type_classification_only_when_signal(self):
        """Type predictions are empty when is_signal is False."""
        classifier = _make_classifier(
            binary_bias=-10.0,
            type_classes=["error_fix", "decision"],
            type_weights=[[0.0] * 12, [0.0] * 12],
            type_biases=[0.0, 0.0],
        )
        result = classifier.predict(_make_turns("hello"))
        assert result["predicted_type"] is None
        assert result["type_probabilities"] == {}

    def test_type_classification_returns_best(self):
        """When signal detected, returns the highest-scoring type."""
        vocab = {"error": 0, "fix": 1, "bug": 2, "decide": 3}

        classifier = _make_classifier(
            vocab=vocab,
            idf_weights=[1.0, 1.0, 1.0, 1.0],
            binary_bias=10.0,  # force is_signal=True
            type_classes=["error_fix", "decision"],
            type_weights=[
                [5.0, 5.0, 5.0, 0.0] + [0.0] * 8,  # error_fix weights
                [0.0, 0.0, 0.0, 5.0] + [0.0] * 8,  # decision weights
            ],
            type_biases=[0.0, 0.0],
        )
        result = classifier.predict(_make_turns("error fix bug crash"))
        assert result["predicted_type"] == "error_fix"

    def test_single_turn(self):
        """Works with a single turn."""
        classifier = _make_classifier()
        result = classifier.predict(_make_turns("single message"))
        assert isinstance(result["is_signal"], bool)

    def test_empty_turns(self):
        """Handles empty turn list gracefully."""
        classifier = _make_classifier()
        result = classifier.predict([])
        assert isinstance(result["is_signal"], bool)
        assert isinstance(result["signal_probability"], float)


class TestGetSignalClassifier:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        from src.core.signal_classifier import invalidate_classifier_cache

        invalidate_classifier_cache()
        yield
        invalidate_classifier_cache()

    @pytest.mark.asyncio
    async def test_returns_none_when_no_model(self):
        redis_store = MagicMock()
        redis_store.client = AsyncMock()
        redis_store.client.get = AsyncMock(return_value=None)

        result = await get_signal_classifier(redis_store)
        assert result is None

    @pytest.mark.asyncio
    async def test_loads_model_from_redis(self):
        model_data = json.dumps(
            {
                "version": 1,
                "vocab": {"test": 0, "hello": 1},
                "idf_weights": [1.5, 0.8],
                "binary": {
                    "weights": [0.1] * 10,
                    "bias": -0.3,
                },
                "type_classifier": {
                    "classes": ["error_fix", "fact"],
                    "weights": [[0.1] * 10, [0.2] * 10],
                    "biases": [-0.1, -0.2],
                },
                "conv_feature_names": CONV_FEATURE_NAMES,
                "trained_at": "2026-02-18T00:00:00",
                "n_samples": 68,
                "binary_cv_score": 0.85,
                "type_cv_score": 0.72,
            }
        )

        redis_store = MagicMock()
        redis_store.client = AsyncMock()
        redis_store.client.get = AsyncMock(return_value=model_data)

        classifier = await get_signal_classifier(redis_store)
        assert classifier is not None
        assert len(classifier.vocab) == 2
        assert classifier.binary_bias == -0.3
        assert len(classifier.type_classes) == 2
        assert classifier.metadata["n_samples"] == 68

    @pytest.mark.asyncio
    async def test_returns_none_on_corrupt_json(self):
        redis_store = MagicMock()
        redis_store.client = AsyncMock()
        redis_store.client.get = AsyncMock(return_value="not valid json{{{")

        result = await get_signal_classifier(redis_store)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_missing_keys(self):
        """Returns None when required keys are missing from Redis data."""
        model_data = json.dumps({"version": 1})  # missing vocab, idf_weights, binary

        redis_store = MagicMock()
        redis_store.client = AsyncMock()
        redis_store.client.get = AsyncMock(return_value=model_data)

        result = await get_signal_classifier(redis_store)
        assert result is None

    @pytest.mark.asyncio
    async def test_loaded_model_can_predict(self):
        """End-to-end: load from Redis and run prediction."""
        n_vocab = 3
        n_features = n_vocab + 8

        model_data = json.dumps(
            {
                "version": 1,
                "vocab": {"error": 0, "fix": 1, "bug": 2},
                "idf_weights": [1.0, 1.0, 1.0],
                "binary": {
                    "weights": [0.5] * n_features,
                    "bias": 0.0,
                },
                "type_classifier": {
                    "classes": [],
                    "weights": [],
                    "biases": [],
                },
                "trained_at": "2026-02-18T00:00:00",
                "n_samples": 50,
                "binary_cv_score": 0.80,
            }
        )

        redis_store = MagicMock()
        redis_store.client = AsyncMock()
        redis_store.client.get = AsyncMock(return_value=model_data)

        classifier = await get_signal_classifier(redis_store)
        assert classifier is not None

        result = classifier.predict(
            _make_turns(
                "I found a bug in the error handler",
                "Let me fix that for you",
            )
        )
        assert isinstance(result["is_signal"], bool)
        assert 0.0 <= result["signal_probability"] <= 1.0


class TestClassifierCache:
    """Tests for in-process model caching in get_signal_classifier()."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        from src.core.signal_classifier import invalidate_classifier_cache

        invalidate_classifier_cache()
        yield
        invalidate_classifier_cache()

    def _model_json(self) -> str:
        return json.dumps(
            {
                "version": 1,
                "vocab": {"test": 0, "hello": 1},
                "idf_weights": [1.5, 0.8],
                "binary": {"weights": [0.1] * 10, "bias": -0.3},
                "type_classifier": {"classes": [], "weights": [], "biases": []},
                "trained_at": "2026-02-18T00:00:00",
                "n_samples": 68,
                "binary_cv_score": 0.85,
            }
        )

    @pytest.mark.asyncio
    async def test_cache_returns_same_object(self):
        """Second call returns cached object without Redis hit."""
        redis_store = MagicMock()
        redis_store.client = AsyncMock()
        redis_store.client.get = AsyncMock(return_value=self._model_json())

        c1 = await get_signal_classifier(redis_store)
        c2 = await get_signal_classifier(redis_store)

        assert c1 is c2
        assert redis_store.client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_cache_expires_after_ttl(self):
        """Cache expires and reloads from Redis after TTL."""
        from unittest.mock import patch

        redis_store = MagicMock()
        redis_store.client = AsyncMock()
        redis_store.client.get = AsyncMock(return_value=self._model_json())

        await get_signal_classifier(redis_store)
        assert redis_store.client.get.call_count == 1

        import src.core.signal_classifier as cls_mod

        with patch.object(cls_mod, "_classifier_cached_at", cls_mod._classifier_cached_at - 120):
            await get_signal_classifier(redis_store)
            assert redis_store.client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_invalidate_forces_reload(self):
        """invalidate_classifier_cache() forces next call to hit Redis."""
        from src.core.signal_classifier import invalidate_classifier_cache

        redis_store = MagicMock()
        redis_store.client = AsyncMock()
        redis_store.client.get = AsyncMock(return_value=self._model_json())

        await get_signal_classifier(redis_store)
        assert redis_store.client.get.call_count == 1

        invalidate_classifier_cache()

        await get_signal_classifier(redis_store)
        assert redis_store.client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_cache_returns_none_when_no_model(self):
        """Cache correctly caches None without repeated Redis hits."""
        redis_store = MagicMock()
        redis_store.client = AsyncMock()
        redis_store.client.get = AsyncMock(return_value=None)

        r1 = await get_signal_classifier(redis_store)
        r2 = await get_signal_classifier(redis_store)

        assert r1 is None
        assert r2 is None
        assert redis_store.client.get.call_count == 1
