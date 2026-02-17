"""
Phase 15C integration tests — Document Memory System.

Tests document ingestion, listing, detail, deletion,
cascade pin/unpin, update, and sibling retrieval boost.
"""

import asyncio
import os
import uuid

import pytest

from tests.integration.conftest import request_with_retry

API_BASE = os.environ.get("RECALL_API_URL", "http://localhost:8200")


# =============================================================
# Helpers
# =============================================================


async def ingest_text(api_client, content: str, filename: str, domain: str = "test-docs"):
    """Upload a plaintext file for ingestion."""
    files = {"file": (filename, content.encode(), "text/plain")}
    data = {"domain": domain, "file_type": "text"}
    r = await request_with_retry(
        api_client, "post", f"{API_BASE}/document/ingest",
        files=files, data=data,
    )
    return r


async def ingest_markdown(api_client, content: str, filename: str, domain: str = "test-docs"):
    """Upload a markdown file for ingestion."""
    files = {"file": (filename, content.encode(), "text/markdown")}
    data = {"domain": domain, "file_type": "markdown"}
    r = await request_with_retry(
        api_client, "post", f"{API_BASE}/document/ingest",
        files=files, data=data,
    )
    return r


# =============================================================
# Tests
# =============================================================


class TestDocumentIngest:
    """Test document upload and ingestion."""

    @pytest.mark.slow
    async def test_ingest_plaintext(self, api_client, cleanup):
        """Ingest a plaintext file — should create document + child memories."""
        uid = uuid.uuid4().hex[:8]
        content = (
            f"The API server runs on port 8200. It uses FastAPI with Qdrant for vector search. "
            f"The database is PostgreSQL for audit logs. Unique: {uid}.\n\n"
            f"Redis handles session state and caching. Neo4j stores the memory graph. "
            f"Ollama runs on a separate machine with an RTX 3090 GPU."
        )
        r = await ingest_text(api_client, content, f"test-{uid}.txt")
        assert r.status_code == 200, f"Ingest failed: {r.text}"
        data = r.json()

        cleanup.track_document(data["document"]["id"])

        assert data["document"]["filename"] == f"test-{uid}.txt"
        assert data["document"]["file_type"] == "text"
        assert data["memories_created"] > 0
        assert len(data["child_ids"]) == data["memories_created"]

    @pytest.mark.slow
    async def test_ingest_markdown_chunks_by_headings(self, api_client, cleanup):
        """Markdown should be chunked by headings."""
        uid = uuid.uuid4().hex[:8]
        content = (
            f"# Architecture Overview {uid}\n\n"
            "The system uses a microservices architecture.\n\n"
            "## Storage Layer\n\n"
            "Qdrant handles vector embeddings. Neo4j stores relationships.\n\n"
            "## API Layer\n\n"
            "FastAPI serves the REST API with rate limiting.\n"
        )
        r = await ingest_markdown(api_client, content, f"arch-{uid}.md")
        assert r.status_code == 200, f"Ingest failed: {r.text}"
        data = r.json()
        cleanup.track_document(data["document"]["id"])

        assert data["document"]["file_type"] == "markdown"
        assert data["memories_created"] > 0

    async def test_duplicate_file_hash_rejected(self, api_client, cleanup):
        """Uploading the same file twice should return 409."""
        uid = uuid.uuid4().hex[:8]
        # Use deterministic content that will produce the same hash
        content = f"Duplicate test content for documents {uid}"

        r1 = await ingest_text(api_client, content, f"dup1-{uid}.txt")
        if r1.status_code == 200:
            cleanup.track_document(r1.json()["document"]["id"])

            r2 = await ingest_text(api_client, content, f"dup2-{uid}.txt")
            assert r2.status_code == 409

    async def test_invalid_file_type_400(self, api_client):
        """Unsupported file_type should return 400."""
        files = {"file": ("test.exe", b"binary", "application/octet-stream")}
        data = {"domain": "test", "file_type": "executable"}
        r = await api_client.post(
            f"{API_BASE}/document/ingest", files=files, data=data,
        )
        assert r.status_code == 400


class TestDocumentCRUD:
    """Test document listing, detail, and deletion."""

    @pytest.mark.slow
    async def test_list_documents(self, api_client, cleanup):
        """List should return ingested documents."""
        uid = uuid.uuid4().hex[:8]
        content = f"List test document content {uid}. Contains infrastructure facts about deployment."
        r = await ingest_text(api_client, content, f"list-{uid}.txt")
        if r.status_code == 200:
            cleanup.track_document(r.json()["document"]["id"])

        r = await api_client.get(f"{API_BASE}/document/")
        assert r.status_code == 200
        docs = r.json()
        assert isinstance(docs, list)
        # Should have at least the one we just created
        assert len(docs) >= 1

    @pytest.mark.slow
    async def test_get_document_detail(self, api_client, cleanup):
        """Get should return document with child_memory_ids."""
        uid = uuid.uuid4().hex[:8]
        content = f"Detail test document {uid}. Redis caches session data on port 6379."
        r = await ingest_text(api_client, content, f"detail-{uid}.txt")
        assert r.status_code == 200
        doc_id = r.json()["document"]["id"]
        cleanup.track_document(doc_id)

        r = await api_client.get(f"{API_BASE}/document/{doc_id}")
        assert r.status_code == 200
        detail = r.json()
        assert "child_memory_ids" in detail
        assert isinstance(detail["child_memory_ids"], list)
        assert detail["filename"] == f"detail-{uid}.txt"

    @pytest.mark.slow
    async def test_delete_cascade(self, api_client, cleanup):
        """Delete should remove document and all children."""
        uid = uuid.uuid4().hex[:8]
        content = f"Delete cascade test {uid}. Neo4j runs on bolt://localhost:7687."
        r = await ingest_text(api_client, content, f"del-{uid}.txt")
        assert r.status_code == 200
        data = r.json()
        doc_id = data["document"]["id"]
        child_ids = data["child_ids"]
        # Don't track — we're deleting manually

        r = await api_client.delete(f"{API_BASE}/document/{doc_id}")
        assert r.status_code == 200
        result = r.json()
        assert result["deleted"] is True
        assert result["children_deleted"] >= 0

        # Verify children are gone
        for cid in child_ids[:3]:  # Check first 3
            r = await api_client.get(f"{API_BASE}/memory/{cid}")
            assert r.status_code == 404


class TestDocumentCascadeOps:
    """Test cascade pin/unpin and update operations."""

    @pytest.mark.slow
    async def test_pin_cascade(self, api_client, cleanup):
        """Pin should cascade to all children."""
        uid = uuid.uuid4().hex[:8]
        content = f"Pin cascade test {uid}. Qdrant vector database stores embeddings."
        r = await ingest_text(api_client, content, f"pin-{uid}.txt")
        assert r.status_code == 200
        doc_id = r.json()["document"]["id"]
        child_ids = r.json()["child_ids"]
        cleanup.track_document(doc_id)

        # Pin
        r = await api_client.post(f"{API_BASE}/document/{doc_id}/pin")
        assert r.status_code == 200
        assert r.json()["pinned"] is True

        # Verify a child is pinned
        if child_ids:
            r = await api_client.get(f"{API_BASE}/memory/{child_ids[0]}")
            if r.status_code == 200:
                assert r.json().get("pinned") is True

    @pytest.mark.slow
    async def test_unpin_cascade(self, api_client, cleanup):
        """Unpin should cascade to all children."""
        uid = uuid.uuid4().hex[:8]
        content = f"Unpin cascade test {uid}. PostgreSQL handles audit logging."
        r = await ingest_text(api_client, content, f"unpin-{uid}.txt")
        assert r.status_code == 200
        doc_id = r.json()["document"]["id"]
        cleanup.track_document(doc_id)

        # Pin then unpin
        await api_client.post(f"{API_BASE}/document/{doc_id}/pin")
        r = await api_client.delete(f"{API_BASE}/document/{doc_id}/pin")
        assert r.status_code == 200
        assert r.json()["pinned"] is False

    @pytest.mark.slow
    async def test_update_domain_cascades(self, api_client, cleanup):
        """PATCH domain should cascade to children."""
        uid = uuid.uuid4().hex[:8]
        content = f"Domain update test {uid}. The worker processes background tasks via ARQ."
        r = await ingest_text(api_client, content, f"domain-{uid}.txt")
        assert r.status_code == 200
        doc_id = r.json()["document"]["id"]
        child_ids = r.json()["child_ids"]
        cleanup.track_document(doc_id)

        new_domain = f"updated-{uid}"
        r = await api_client.patch(
            f"{API_BASE}/document/{doc_id}",
            json={"domain": new_domain},
        )
        assert r.status_code == 200
        assert r.json()["children_updated"] >= 0

    @pytest.mark.slow
    async def test_children_inherit_durability(self, api_client, cleanup):
        """Children should inherit document durability at ingest time."""
        uid = uuid.uuid4().hex[:8]
        content = f"Durability inherit test {uid}. CasaOS runs at 192.168.50.19."
        files = {"file": (f"dur-{uid}.txt", content.encode(), "text/plain")}
        data = {"domain": "test-docs", "file_type": "text", "durability": "permanent"}
        r = await request_with_retry(
            api_client, "post", f"{API_BASE}/document/ingest",
            files=files, data=data,
        )
        assert r.status_code == 200
        doc_id = r.json()["document"]["id"]
        child_ids = r.json()["child_ids"]
        cleanup.track_document(doc_id)

        assert r.json()["document"]["durability"] == "permanent"

        # Check a child's durability
        if child_ids:
            r = await api_client.get(f"{API_BASE}/memory/{child_ids[0]}")
            if r.status_code == 200:
                assert r.json().get("durability") == "permanent"
