"""
v2.3 Tests — Admin graph bootstrap endpoint.

Source-level verification that the endpoint exists and uses
scroll_all + similarity search + edge creation.
"""

import re
from pathlib import Path


def test_admin_graph_bootstrap_endpoint_exists():
    """POST /admin/graph/bootstrap endpoint exists in admin.py."""
    source = Path("src/api/routes/admin.py").read_text()

    assert "graph/bootstrap" in source, (
        "admin.py must have /graph/bootstrap endpoint"
    )


def test_admin_graph_uses_scroll_all():
    """Graph bootstrap uses scroll_all for unbiased iteration."""
    source = Path("src/api/routes/admin.py").read_text()

    # Find the bootstrap function
    match = re.search(
        r'async def bootstrap_graph\(.*?\n(?=\n@router|\nclass |\Z)',
        source,
        re.DOTALL,
    )
    assert match, "Could not find bootstrap_graph function"
    func_body = match.group(0)

    assert "scroll_all" in func_body, (
        "Graph bootstrap must use scroll_all for unbiased iteration"
    )


def test_admin_graph_creates_edges():
    """Graph bootstrap creates RELATED_TO edges."""
    source = Path("src/api/routes/admin.py").read_text()

    match = re.search(
        r'async def bootstrap_graph\(.*?\n(?=\n@router|\nclass |\Z)',
        source,
        re.DOTALL,
    )
    assert match, "Could not find bootstrap_graph function"
    func_body = match.group(0)

    assert "strengthen_relationship" in func_body or "auto_link_memory" in func_body, (
        "Graph bootstrap must create RELATED_TO edges"
    )


def test_admin_graph_has_batch_processing():
    """Graph bootstrap processes in batches to avoid overwhelming Neo4j."""
    source = Path("src/api/routes/admin.py").read_text()

    match = re.search(
        r'async def bootstrap_graph\(.*?\n(?=\n@router|\nclass |\Z)',
        source,
        re.DOTALL,
    )
    assert match, "Could not find bootstrap_graph function"
    func_body = match.group(0)

    # Should have batch or sleep/delay logic
    assert "batch" in func_body.lower() or "sleep" in func_body or "asyncio" in func_body, (
        "Graph bootstrap must process in batches with delays"
    )
