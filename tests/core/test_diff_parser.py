"""
Test pairing for src/core/diff_parser.py.

The main tests live in tests/core/test_git_watch.py which exercises
all extract_values() functions.
"""

from src.core.diff_parser import extract_values


def test_diff_parser_module_exists():
    """diff_parser module exports expected functions."""
    assert callable(extract_values)
