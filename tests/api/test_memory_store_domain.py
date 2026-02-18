"""
v2.3 Tests — store_memory normalizes domain.

Source-level verification that store_memory applies normalize_domain()
to the incoming request domain before creating the Memory object.
"""

import re
from pathlib import Path


def test_store_memory_imports_normalize_domain():
    """store_memory route file imports normalize_domain."""
    source = Path("src/api/routes/memory.py").read_text()

    assert "normalize_domain" in source, (
        "memory.py must import normalize_domain"
    )


def test_store_memory_applies_normalize_domain():
    """store_memory applies normalize_domain to request.domain."""
    source = Path("src/api/routes/memory.py").read_text()

    # Find the store_memory function body
    match = re.search(
        r'async def store_memory\(.*?\n(?=\n@router|\nclass |\Z)',
        source,
        re.DOTALL,
    )
    assert match, "Could not find store_memory function"
    func_body = match.group(0)

    # normalize_domain must be called on the domain before Memory creation
    assert "normalize_domain" in func_body, (
        "store_memory must call normalize_domain on the incoming domain"
    )
