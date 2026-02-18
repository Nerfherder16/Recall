"""
v2.3 Tests — Auto-linker creates RELATED_TO edges on memory store.

Source-level verification that:
1. auto_linker.py exists with auto_link_memory function
2. It searches for similar memories and creates RELATED_TO edges
3. It's called from store_memory, signal store, and observer store paths
"""

import ast
import re
from pathlib import Path


def test_auto_linker_module_exists():
    """src/core/auto_linker.py exists and has auto_link_memory function."""
    path = Path("src/core/auto_linker.py")
    assert path.exists(), "src/core/auto_linker.py must exist"

    source = path.read_text()
    assert "async def auto_link_memory" in source, (
        "auto_linker.py must define auto_link_memory function"
    )


def test_auto_linker_searches_similar():
    """auto_link_memory searches Qdrant for similar memories."""
    source = Path("src/core/auto_linker.py").read_text()

    # Must use qdrant search to find similar memories
    assert "search(" in source or "search_similar" in source, (
        "auto_link_memory must search for similar memories"
    )


def test_auto_linker_creates_edges():
    """auto_link_memory creates RELATED_TO edges via neo4j."""
    source = Path("src/core/auto_linker.py").read_text()

    assert "strengthen_relationship" in source or "create_relationship" in source, (
        "auto_link_memory must create RELATED_TO edges"
    )


def test_auto_linker_has_similarity_threshold():
    """auto_link_memory filters by similarity threshold."""
    source = Path("src/core/auto_linker.py").read_text()

    # Should have a minimum similarity threshold (spec says 0.5)
    assert "0.5" in source or "threshold" in source.lower(), (
        "auto_link_memory must have a similarity threshold"
    )


def test_store_memory_calls_auto_linker():
    """store_memory route calls auto_link_memory as background task."""
    source = Path("src/api/routes/memory.py").read_text()

    assert "auto_link_memory" in source, (
        "store_memory must call auto_link_memory"
    )


def test_signal_store_calls_auto_linker():
    """_store_signal_as_memory calls auto_link_memory."""
    source = Path("src/workers/signals.py").read_text()

    assert "auto_link_memory" in source, (
        "_store_signal_as_memory must call auto_link_memory"
    )


def test_observer_store_calls_auto_linker():
    """observer _run_extraction calls auto_link_memory."""
    source = Path("src/workers/observer.py").read_text()

    assert "auto_link_memory" in source, (
        "observer must call auto_link_memory"
    )
