"""
Integration tests for Phase 7 — Observability & Operations.

Tests: export, import, reconcile, metrics, dashboard.
"""

import json
import uuid

import httpx
import pytest

from .conftest import API_BASE

pytestmark = pytest.mark.asyncio


# =============================================================
# METRICS
# =============================================================


async def test_metrics_endpoint(api_client: httpx.AsyncClient):
    """GET /metrics returns Prometheus text format."""
    r = await api_client.get(f"{API_BASE}/metrics")
    assert r.status_code == 200
    text = r.text
    assert "recall_uptime_seconds" in text
    assert "# TYPE" in text


# =============================================================
# DASHBOARD
# =============================================================


async def test_dashboard_loads(api_client: httpx.AsyncClient):
    """GET /dashboard/ returns the React SPA HTML."""
    r = await api_client.get(f"{API_BASE}/dashboard/", follow_redirects=True)
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "Recall Dashboard" in r.text


# =============================================================
# EXPORT
# =============================================================


async def test_export_returns_jsonl(api_client: httpx.AsyncClient, stored_memory, test_domain):
    """Export produces valid JSONL with memory data."""
    mem = await stored_memory("Export test memory for ops", domain=test_domain)

    r = await api_client.get(f"{API_BASE}/admin/export")
    assert r.status_code == 200
    assert "application/x-ndjson" in r.headers.get("content-type", "")

    lines = [l for l in r.text.strip().split("\n") if l.strip()]
    assert len(lines) >= 1

    # Find our memory in the export
    found = False
    for line in lines:
        record = json.loads(line)
        assert "memory" in record
        assert "relationships" in record
        if record["memory"]["id"] == mem["id"]:
            found = True
            assert record["memory"]["domain"] == test_domain
            # No embedding by default
            assert "embedding" not in record
    assert found, "Exported memory not found in JSONL"


async def test_export_with_embeddings(api_client: httpx.AsyncClient, stored_memory, test_domain):
    """Export with include_embeddings=true includes embedding vectors."""
    mem = await stored_memory("Embedding export test", domain=test_domain)

    r = await api_client.get(f"{API_BASE}/admin/export?include_embeddings=true")
    assert r.status_code == 200

    lines = [l for l in r.text.strip().split("\n") if l.strip()]
    found = False
    for line in lines:
        record = json.loads(line)
        if record["memory"]["id"] == mem["id"]:
            found = True
            assert "embedding" in record
            assert isinstance(record["embedding"], list)
            assert len(record["embedding"]) > 0
    assert found, "Exported memory with embedding not found"


# =============================================================
# IMPORT
# =============================================================


async def test_import_creates_memories(api_client: httpx.AsyncClient, stored_memory, test_domain, cleanup):
    """Round-trip: export a memory, delete it, import it back."""
    mem = await stored_memory("Round trip import test", domain=test_domain)
    mem_id = mem["id"]

    # Export with embeddings so we can re-import without regenerating
    r = await api_client.get(f"{API_BASE}/admin/export?include_embeddings=true")
    assert r.status_code == 200

    # Find our memory line
    our_line = None
    for line in r.text.strip().split("\n"):
        if not line.strip():
            continue
        record = json.loads(line)
        if record["memory"]["id"] == mem_id:
            our_line = line
            break
    assert our_line, "Memory not found in export"

    # Delete the original
    dr = await api_client.delete(f"{API_BASE}/memory/{mem_id}")
    assert dr.status_code == 200

    # Import it back
    import_file = our_line.encode("utf-8")
    files = {"file": ("test.jsonl", import_file, "application/x-ndjson")}
    ir = await api_client.post(f"{API_BASE}/admin/import", files=files)
    assert ir.status_code == 200
    data = ir.json()
    assert data["imported"] == 1
    assert data["errors"] == 0

    # Re-track for cleanup
    cleanup.track_memory(mem_id)

    # Verify it exists
    vr = await api_client.get(f"{API_BASE}/memory/{mem_id}")
    assert vr.status_code == 200


async def test_import_skip_duplicates(api_client: httpx.AsyncClient, stored_memory, test_domain):
    """Import with conflict=skip doesn't overwrite existing memories."""
    mem = await stored_memory("Skip duplicate test", domain=test_domain)

    # Build a JSONL line for the same ID
    line = json.dumps({
        "memory": {
            "id": mem["id"],
            "content": "OVERWRITTEN CONTENT",
            "memory_type": "semantic",
            "domain": test_domain,
        },
        "relationships": [],
    })

    files = {"file": ("test.jsonl", line.encode(), "application/x-ndjson")}
    r = await api_client.post(f"{API_BASE}/admin/import?conflict=skip", files=files)
    assert r.status_code == 200
    data = r.json()
    assert data["skipped"] == 1
    assert data["imported"] == 0

    # Original content unchanged
    vr = await api_client.get(f"{API_BASE}/memory/{mem['id']}")
    assert vr.status_code == 200
    assert "Skip duplicate test" in vr.json().get("content", "")


async def test_import_overwrite_mode(api_client: httpx.AsyncClient, stored_memory, test_domain, cleanup):
    """Import with conflict=overwrite replaces existing memories."""
    mem = await stored_memory("Original content here", domain=test_domain)

    line = json.dumps({
        "memory": {
            "id": mem["id"],
            "content": "Overwritten content here",
            "memory_type": "semantic",
            "domain": test_domain,
        },
        "relationships": [],
    })

    files = {"file": ("test.jsonl", line.encode(), "application/x-ndjson")}
    r = await api_client.post(
        f"{API_BASE}/admin/import?conflict=overwrite&regenerate_embeddings=true",
        files=files,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["imported"] == 1

    # Content should be updated
    vr = await api_client.get(f"{API_BASE}/memory/{mem['id']}")
    assert vr.status_code == 200
    assert "Overwritten content" in vr.json().get("content", "")


# =============================================================
# RECONCILE
# =============================================================


async def test_reconcile_report_only(api_client: httpx.AsyncClient, stored_memory, test_domain):
    """Reconcile without repair returns a report."""
    await stored_memory("Reconcile test memory", domain=test_domain)

    r = await api_client.post(f"{API_BASE}/admin/reconcile?repair=false")
    assert r.status_code == 200
    data = r.json()

    assert "qdrant_total" in data
    assert "neo4j_total" in data
    assert "qdrant_orphans" in data
    assert "neo4j_orphans" in data
    assert "importance_mismatches" in data
    assert "superseded_mismatches" in data
    assert data["repairs_applied"] == 0


async def test_reconcile_repair(api_client: httpx.AsyncClient, stored_memory, test_domain):
    """Reconcile with repair=true applies fixes (even if 0 needed)."""
    await stored_memory("Reconcile repair test", domain=test_domain)

    r = await api_client.post(f"{API_BASE}/admin/reconcile?repair=true")
    assert r.status_code == 200
    data = r.json()

    assert "repairs_applied" in data
    # After repair, orphans should be resolved
    assert isinstance(data["repairs_applied"], int)
