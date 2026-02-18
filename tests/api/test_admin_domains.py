"""
v2.3 Tests — Admin domain normalization migration endpoint.

Source-level verification that the endpoint exists and uses
normalize_domain + scroll_all for migration.
"""

import re
from pathlib import Path


def test_admin_domains_normalize_endpoint_exists():
    """POST /admin/domains/normalize endpoint exists in admin.py."""
    source = Path("src/api/routes/admin.py").read_text()

    assert "domains/normalize" in source, (
        "admin.py must have /domains/normalize endpoint"
    )


def test_admin_domains_uses_scroll_all():
    """Domain normalization uses scroll_all for unbiased iteration."""
    source = Path("src/api/routes/admin.py").read_text()

    # Find the normalize domains function
    match = re.search(
        r'async def normalize_domains\(.*?\n(?=\n@router|\nclass |\Z)',
        source,
        re.DOTALL,
    )
    assert match, "Could not find normalize_domains function"
    func_body = match.group(0)

    assert "scroll_all" in func_body, (
        "Domain normalization must use scroll_all for unbiased iteration"
    )


def test_admin_domains_uses_normalize_domain():
    """Domain normalization calls normalize_domain from domains.py."""
    source = Path("src/api/routes/admin.py").read_text()

    assert "normalize_domain" in source, (
        "admin.py must import and use normalize_domain"
    )
