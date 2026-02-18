"""
v2.3 Tests — Signal pipeline fixes.

Tests that pending signal dicts include importance and durability fields.
Uses AST parsing to avoid arq import chain.
"""

import ast
import re
from pathlib import Path


def _get_pending_signal_dict_source():
    """Extract the add_pending_signal call from signals.py source."""
    source = Path("src/workers/signals.py").read_text()
    return source


def test_pending_signal_includes_importance():
    """The pending signal dict includes the importance field."""
    source = _get_pending_signal_dict_source()

    # Find the add_pending_signal call and check it includes importance
    # Look for the dict being passed to add_pending_signal
    assert '"importance"' in source or "'importance'" in source, (
        "Pending signal dict should include 'importance' key"
    )

    # Verify it's in the add_pending_signal context, not just anywhere
    # Find the block between add_pending_signal and the closing })
    match = re.search(
        r'add_pending_signal\(session_id,\s*\{(.*?)\}\)',
        source,
        re.DOTALL,
    )
    assert match, "Could not find add_pending_signal call"
    dict_content = match.group(1)
    assert "importance" in dict_content, (
        "add_pending_signal dict must include 'importance' key"
    )


def test_pending_signal_includes_durability():
    """The pending signal dict includes the durability field."""
    source = _get_pending_signal_dict_source()

    match = re.search(
        r'add_pending_signal\(session_id,\s*\{(.*?)\}\)',
        source,
        re.DOTALL,
    )
    assert match, "Could not find add_pending_signal call"
    dict_content = match.group(1)
    assert "durability" in dict_content, (
        "add_pending_signal dict must include 'durability' key"
    )
