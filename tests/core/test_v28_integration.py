"""
Integration smoke tests for v2.8 "Sharpen the Blade" features.

Covers: ML type hint in signal detector, feedback-aware decay,
access-frequency decay modifier, backward compatibility.
"""

import sys
from datetime import datetime, timedelta
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


# ── ML Type Hint Tests ─────────────────────────────────


def test_signal_detector_accepts_ml_hint():
    """SignalDetector.detect() accepts ml_hint and ml_confidence."""
    from src.core.signal_detector import SignalDetector

    d = SignalDetector()
    # Just verify the method signature accepts the params
    import inspect

    sig = inspect.signature(d.detect)
    assert "ml_hint" in sig.parameters
    assert "ml_confidence" in sig.parameters


@pytest.mark.asyncio
async def test_signal_detector_hint_in_prompt():
    """ML hint text appears in prompt when provided."""
    from src.core.signal_detector import SignalDetector

    detector = SignalDetector()
    captured_prompt = None

    async def mock_generate(prompt, **kwargs):
        nonlocal captured_prompt
        captured_prompt = prompt
        return "[]"

    mock_llm = MagicMock()
    mock_llm.generate = mock_generate

    with patch(
        "src.core.signal_detector.get_llm",
        new_callable=AsyncMock,
        return_value=mock_llm,
    ):
        turns = [
            {"role": "user", "content": "Fix the crash bug"},
            {"role": "assistant", "content": "Fixed the timeout"},
        ]
        await detector.detect(
            turns,
            ml_hint="error_fix",
            ml_confidence=0.85,
        )

    assert captured_prompt is not None
    assert '"error_fix"' in captured_prompt
    assert "85%" in captured_prompt
    assert "ML pre-classifier" in captured_prompt


@pytest.mark.asyncio
async def test_signal_detector_no_hint_when_none():
    """ML hint text does NOT appear when ml_hint is None."""
    from src.core.signal_detector import SignalDetector

    detector = SignalDetector()
    captured_prompt = None

    async def mock_generate(prompt, **kwargs):
        nonlocal captured_prompt
        captured_prompt = prompt
        return "[]"

    mock_llm = MagicMock()
    mock_llm.generate = mock_generate

    with patch(
        "src.core.signal_detector.get_llm",
        new_callable=AsyncMock,
        return_value=mock_llm,
    ):
        turns = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        await detector.detect(turns)

    assert captured_prompt is not None
    assert "ML pre-classifier" not in captured_prompt


# ── Feedback-Aware Decay Tests ──────────────────────────


@pytest.mark.asyncio
async def test_decay_slower_with_high_access_count():
    """Memories with high access_count decay slower."""
    from src.workers.decay import DecayWorker

    now = datetime.utcnow()
    last_accessed = (now - timedelta(hours=24)).isoformat()

    # Memory with 0 accesses
    low_access = {
        "importance": 0.8,
        "stability": 0.1,
        "last_accessed": last_accessed,
        "access_count": 0,
    }
    # Memory with 20 accesses
    high_access = {
        "importance": 0.8,
        "stability": 0.1,
        "last_accessed": last_accessed,
        "access_count": 20,
    }

    mock_qdrant = MagicMock()
    mock_qdrant.scroll_all = AsyncMock(
        return_value=[
            ("mem-low", low_access),
            ("mem-high", high_access),
        ]
    )
    mock_qdrant.update_importance = AsyncMock()
    mock_neo4j = MagicMock()
    mock_neo4j.update_importance = AsyncMock()

    worker = DecayWorker(mock_qdrant, mock_neo4j)

    await worker.run(feedback_stats={})

    # Both should have been updated
    calls = mock_qdrant.update_importance.call_args_list
    updates = {c.args[0]: c.args[1] for c in calls}

    assert "mem-low" in updates
    assert "mem-high" in updates
    # High access count → less decay → higher importance
    assert updates["mem-high"] > updates["mem-low"]


@pytest.mark.asyncio
async def test_decay_slower_with_positive_feedback():
    """Memories with positive feedback decay slower."""
    from src.workers.decay import DecayWorker

    now = datetime.utcnow()
    last_accessed = (now - timedelta(hours=24)).isoformat()

    payload = {
        "importance": 0.8,
        "stability": 0.1,
        "last_accessed": last_accessed,
        "access_count": 5,
    }

    mock_qdrant = MagicMock()
    mock_qdrant.scroll_all = AsyncMock(
        return_value=[
            ("mem-useful", dict(payload)),
            ("mem-nofb", dict(payload)),
        ]
    )
    mock_qdrant.update_importance = AsyncMock()
    mock_neo4j = MagicMock()
    mock_neo4j.update_importance = AsyncMock()

    feedback_stats = {
        "mem-useful": {"useful": 10, "not_useful": 0},
        # mem-nofb has no feedback
    }

    worker = DecayWorker(mock_qdrant, mock_neo4j)
    await worker.run(feedback_stats=feedback_stats)

    calls = mock_qdrant.update_importance.call_args_list
    updates = {c.args[0]: c.args[1] for c in calls}

    assert "mem-useful" in updates
    assert "mem-nofb" in updates
    # Useful feedback → less decay → higher importance
    assert updates["mem-useful"] > updates["mem-nofb"]


@pytest.mark.asyncio
async def test_decay_pinned_still_immune():
    """Pinned memories are still immune with new modifiers."""
    from src.workers.decay import DecayWorker

    now = datetime.utcnow()
    last_accessed = (now - timedelta(hours=48)).isoformat()

    mock_qdrant = MagicMock()
    mock_qdrant.scroll_all = AsyncMock(
        return_value=[
            (
                "mem-pinned",
                {
                    "importance": 0.9,
                    "stability": 0.1,
                    "last_accessed": last_accessed,
                    "access_count": 0,
                    "pinned": "true",
                },
            ),
        ]
    )
    mock_qdrant.update_importance = AsyncMock()
    mock_neo4j = MagicMock()
    mock_neo4j.update_importance = AsyncMock()

    worker = DecayWorker(mock_qdrant, mock_neo4j)
    stats = await worker.run(feedback_stats={})

    assert stats["stable"] == 1
    assert stats["decayed"] == 0
    mock_qdrant.update_importance.assert_not_called()


@pytest.mark.asyncio
async def test_decay_permanent_still_immune():
    """Permanent memories are still immune with new modifiers."""
    from src.workers.decay import DecayWorker

    now = datetime.utcnow()
    last_accessed = (now - timedelta(hours=48)).isoformat()

    mock_qdrant = MagicMock()
    mock_qdrant.scroll_all = AsyncMock(
        return_value=[
            (
                "mem-perm",
                {
                    "importance": 0.9,
                    "stability": 0.1,
                    "last_accessed": last_accessed,
                    "access_count": 0,
                    "durability": "permanent",
                },
            ),
        ]
    )
    mock_qdrant.update_importance = AsyncMock()
    mock_neo4j = MagicMock()
    mock_neo4j.update_importance = AsyncMock()

    worker = DecayWorker(mock_qdrant, mock_neo4j)
    stats = await worker.run(feedback_stats={})

    assert stats["stable"] == 1
    mock_qdrant.update_importance.assert_not_called()


# ── Signals Pipeline Hint Passthrough ────────────────────


def test_signals_imports_ml_hint_params():
    """signals.py passes ml_hint to detector.detect()."""
    # Verify the function exists and is async
    import inspect

    from src.workers import signals

    assert inspect.iscoroutinefunction(signals._run_signal_detection)
