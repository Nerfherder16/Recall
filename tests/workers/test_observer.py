"""
v2.3 Tests — Observer domain constraint.

Verifies that the observer prompt includes the canonical domain list.
Reads the source file directly to avoid arq import chain.
"""

import ast
from pathlib import Path


def _get_observer_prompt():
    """Extract OBSERVER_PROMPT from source without importing (avoids arq)."""
    source = Path("src/workers/observer.py").read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "OBSERVER_PROMPT":
                    return ast.literal_eval(node.value)
    raise RuntimeError("OBSERVER_PROMPT not found in observer.py")


def test_observer_prompt_contains_canonical_domains():
    """The OBSERVER_PROMPT includes the canonical domain list."""
    prompt = _get_observer_prompt()
    from src.core.domains import CANONICAL_DOMAINS

    for domain in CANONICAL_DOMAINS:
        assert domain in prompt, (
            f"Canonical domain '{domain}' not found in OBSERVER_PROMPT"
        )


def test_observer_prompt_constrains_domain():
    """The prompt explicitly tells the LLM to use canonical domains."""
    prompt = _get_observer_prompt()

    assert "must be one of" in prompt.lower() or "one of:" in prompt.lower(), (
        "OBSERVER_PROMPT should constrain domain to canonical list"
    )
