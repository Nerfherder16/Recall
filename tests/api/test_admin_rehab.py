"""
v2.3 Tests — Admin importance rehabilitation endpoint.

Source-level verification that the endpoint exists and rehabilitates
floor-level memories based on access_count, pinned, and durability.
"""

import re
from pathlib import Path


def test_admin_rehab_endpoint_exists():
    """POST /admin/importance/rehabilitate endpoint exists."""
    source = Path("src/api/routes/admin.py").read_text()

    assert "importance/rehabilitate" in source, (
        "admin.py must have /importance/rehabilitate endpoint"
    )


def test_admin_rehab_uses_scroll_all():
    """Rehabilitation uses scroll_all for unbiased iteration."""
    source = Path("src/api/routes/admin.py").read_text()

    match = re.search(
        r'async def rehabilitate_importance\(.*?\n(?=\n@router|\nclass |\Z)',
        source,
        re.DOTALL,
    )
    assert match, "Could not find rehabilitate_importance function"
    func_body = match.group(0)

    assert "scroll_all" in func_body, (
        "Rehabilitation must use scroll_all for unbiased iteration"
    )


def test_admin_rehab_checks_access_count():
    """Rehabilitation considers access_count for boost eligibility."""
    source = Path("src/api/routes/admin.py").read_text()

    match = re.search(
        r'async def rehabilitate_importance\(.*?\n(?=\n@router|\nclass |\Z)',
        source,
        re.DOTALL,
    )
    assert match, "Could not find rehabilitate_importance function"
    func_body = match.group(0)

    assert "access_count" in func_body, (
        "Rehabilitation must check access_count"
    )


def test_admin_rehab_checks_durability():
    """Rehabilitation considers durability for boost eligibility."""
    source = Path("src/api/routes/admin.py").read_text()

    match = re.search(
        r'async def rehabilitate_importance\(.*?\n(?=\n@router|\nclass |\Z)',
        source,
        re.DOTALL,
    )
    assert match, "Could not find rehabilitate_importance function"
    func_body = match.group(0)

    assert "durable" in func_body or "durability" in func_body, (
        "Rehabilitation must check durability"
    )
