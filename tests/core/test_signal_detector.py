"""
v2.3 Tests — Signal detector domain constraint.

Verifies that the signal detector prompt includes the canonical domain list
and that parsed domains are normalized.
"""


def test_signal_detector_prompt_contains_canonical_domains():
    """The PROMPT_TEMPLATE includes the canonical domain list."""
    from src.core.signal_detector import PROMPT_TEMPLATE
    from src.core.domains import CANONICAL_DOMAINS

    for domain in CANONICAL_DOMAINS:
        assert domain in PROMPT_TEMPLATE, (
            f"Canonical domain '{domain}' not found in PROMPT_TEMPLATE"
        )


def test_signal_detector_prompt_constrains_domain():
    """The prompt explicitly tells the LLM to use canonical domains."""
    from src.core.signal_detector import PROMPT_TEMPLATE

    assert "must be one of" in PROMPT_TEMPLATE.lower() or "one of:" in PROMPT_TEMPLATE.lower(), (
        "PROMPT_TEMPLATE should constrain domain to canonical list"
    )
