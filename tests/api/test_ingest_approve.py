"""
v2.3 Tests — approve_signal sets durability and initial_importance.

Source-level verification that the Memory constructor in approve_signal
includes durability and initial_importance fields.
"""

import re
from pathlib import Path


def _get_approve_memory_constructor():
    """Extract the Memory() constructor call from approve_signal."""
    source = Path("src/api/routes/ingest.py").read_text()

    # Find the Memory constructor in approve_signal context
    # Look for Memory( after the "approved" metadata line
    match = re.search(
        r'metadata=\{"auto_detected": True, "approved": True\}.*?\)',
        source,
        re.DOTALL,
    )
    assert match, "Could not find Memory constructor in approve_signal"
    return match.group(0)


def test_approve_signal_sets_durability():
    """approve_signal Memory constructor includes durability field."""
    source = Path("src/api/routes/ingest.py").read_text()

    # Find the full Memory() call in the approve context
    # The approve function's Memory() is the one with "approved": True
    match = re.search(
        r'memory = Memory\((.*?)"approved": True\}.*?\)',
        source,
        re.DOTALL,
    )
    assert match, "Could not find approve_signal Memory constructor"
    constructor = match.group(0)
    assert "durability=" in constructor, (
        "approve_signal Memory constructor must set durability"
    )


def test_approve_signal_sets_initial_importance():
    """approve_signal Memory constructor includes initial_importance field."""
    source = Path("src/api/routes/ingest.py").read_text()

    match = re.search(
        r'memory = Memory\((.*?)"approved": True\}.*?\)',
        source,
        re.DOTALL,
    )
    assert match, "Could not find approve_signal Memory constructor"
    constructor = match.group(0)
    assert "initial_importance=" in constructor, (
        "approve_signal Memory constructor must set initial_importance"
    )


def test_approve_signal_reads_durability_from_pending():
    """approve_signal reads durability from the pending signal dict."""
    source = Path("src/api/routes/ingest.py").read_text()

    # The approve_signal function should reference signal.get("durability")
    # or SIGNAL_DURABILITY as fallback
    approve_func = _extract_approve_function(source)
    assert "durability" in approve_func, (
        "approve_signal must read durability from pending signal"
    )
    assert "SIGNAL_DURABILITY" in approve_func, (
        "approve_signal must use SIGNAL_DURABILITY as fallback"
    )


def _extract_approve_function(source: str) -> str:
    """Extract the approve_signal function body."""
    match = re.search(
        r'async def approve_signal\(.*?\n(?=\n@|\nclass |\Z)',
        source,
        re.DOTALL,
    )
    if match:
        return match.group(0)
    # Fallback: grab everything from the function def to end of file
    idx = source.find("async def approve_signal")
    if idx >= 0:
        return source[idx:]
    return ""
