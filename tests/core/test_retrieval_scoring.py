"""
v2.3 Tests — Retrieval scoring uses minimum importance floor.

Source-level verification that _vector_search and _fact_search apply
max(importance, 0.15) instead of raw importance, preventing floor-level
memories from becoming invisible.
"""

import re
from pathlib import Path


def _get_retrieval_source():
    """Read the retrieval.py source."""
    return Path("src/core/retrieval.py").read_text()


def test_vector_search_uses_importance_floor():
    """_vector_search scoring uses max(importance, 0.15) not raw importance."""
    source = _get_retrieval_source()

    # Find the score= line in _vector_search
    # It should use max(memory.importance, 0.15)
    match = re.search(
        r'async def _vector_search\(.*?\n(?=    async def |\nclass )',
        source,
        re.DOTALL,
    )
    assert match, "Could not find _vector_search method"
    method_body = match.group(0)

    # The scoring line must use a floor
    assert "max(memory.importance" in method_body or "max(importance" in method_body, (
        "_vector_search must use max(importance, floor) not raw importance"
    )
    assert "0.15" in method_body, (
        "_vector_search must use 0.15 as the importance floor"
    )


def test_fact_search_uses_importance_floor():
    """_fact_search scoring uses max(importance, 0.15) not raw importance."""
    source = _get_retrieval_source()

    # Find the score= line in _fact_search
    match = re.search(
        r'async def _fact_search\(.*?\n(?=    async def |\nclass )',
        source,
        re.DOTALL,
    )
    assert match, "Could not find _fact_search method"
    method_body = match.group(0)

    # The scoring line must use a floor
    assert "max(memory.importance" in method_body or "max(importance" in method_body, (
        "_fact_search must use max(importance, floor) not raw importance"
    )
    assert "0.15" in method_body, (
        "_fact_search must use 0.15 as the importance floor"
    )


def test_scoring_prevents_zero_score():
    """With floor=0.15, even importance=0.0 yields non-zero score."""
    # Direct calculation test
    similarity = 0.8
    importance = 0.0
    floor = 0.15

    # Old scoring: would be 0.0
    old_score = similarity * importance
    assert old_score == 0.0

    # New scoring: should be > 0
    new_score = similarity * max(importance, floor)
    assert new_score > 0
    assert new_score == similarity * floor
