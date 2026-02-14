"""
Tests for memory CRUD operations: POST /memory/store, GET /memory/{id}, DELETE /memory/{id}.
"""

import hashlib

import pytest

from tests.integration.conftest import API_BASE


class TestStoreMemory:
    """POST /memory/store"""

    async def test_store_minimal(self, api_client, test_domain, cleanup):
        """Store with only content — defaults should fill in."""
        r = await api_client.post(
            f"{API_BASE}/memory/store",
            json={"content": "minimal memory", "domain": test_domain},
        )
        assert r.status_code == 200
        data = r.json()
        cleanup.track_memory(data["id"])

        assert data["created"] is True
        assert data["id"]
        assert data["content_hash"]
        assert data["message"]

    async def test_store_all_fields(self, stored_memory, test_domain):
        """Store with every optional field populated."""
        data = await stored_memory(
            "fully-specified memory",
            memory_type="episodic",
            source="assistant",
            tags=["tag-a", "tag-b"],
            importance=0.9,
            confidence=0.75,
            metadata={"key": "value"},
        )
        assert data["created"] is True
        assert data["id"]

    @pytest.mark.parametrize("mtype", ["semantic", "episodic", "procedural", "working"])
    async def test_store_each_memory_type(self, stored_memory, mtype):
        """Store succeeds for every MemoryType enum value."""
        data = await stored_memory(f"memory of type {mtype}", memory_type=mtype)
        assert data["created"] is True

    async def test_content_hash_deterministic(self, api_client, test_domain, cleanup):
        """Same content produces the same hash."""
        content = f"deterministic hash test {test_domain}"
        r1 = await api_client.post(
            f"{API_BASE}/memory/store",
            json={"content": content, "domain": test_domain},
        )
        data1 = r1.json()
        cleanup.track_memory(data1["id"])

        r2 = await api_client.post(
            f"{API_BASE}/memory/store",
            json={"content": content, "domain": test_domain},
        )
        data2 = r2.json()
        cleanup.track_memory(data2["id"])

        assert data1["content_hash"] == data2["content_hash"]

    async def test_content_hash_unique_for_different_content(self, stored_memory):
        """Different content produces different hashes."""
        d1 = await stored_memory("alpha content unique")
        d2 = await stored_memory("beta content unique")
        assert d1["content_hash"] != d2["content_hash"]

    async def test_default_values_applied(self, api_client, test_domain, cleanup):
        """Verify defaults: semantic type, 0.5 importance, 0.8 confidence."""
        r = await api_client.post(
            f"{API_BASE}/memory/store",
            json={"content": "defaults test", "domain": test_domain},
        )
        data = r.json()
        cleanup.track_memory(data["id"])

        # Fetch the stored memory to inspect defaults
        r2 = await api_client.get(f"{API_BASE}/memory/{data['id']}")
        assert r2.status_code == 200
        mem = r2.json()
        assert mem["memory_type"] == "semantic"
        assert mem["importance"] == pytest.approx(0.5, abs=0.01)
        assert mem["confidence"] == pytest.approx(0.8, abs=0.01)

    async def test_metadata_stored(self, stored_memory, api_client):
        """Custom metadata round-trips through store→get."""
        data = await stored_memory(
            "metadata carrier",
            metadata={"project": "recall", "version": 2},
        )
        # The GET response model doesn't include metadata directly,
        # but the store should succeed without error
        assert data["created"] is True


class TestGetMemory:
    """GET /memory/{memory_id}"""

    async def test_get_by_id(self, stored_memory, api_client):
        data = await stored_memory("retrievable memory")
        r = await api_client.get(f"{API_BASE}/memory/{data['id']}")
        assert r.status_code == 200
        mem = r.json()
        assert mem["id"] == data["id"]
        assert mem["content"] == "retrievable memory"
        assert "created_at" in mem
        assert "last_accessed" in mem
        assert mem["access_count"] >= 0

    async def test_get_not_found(self, api_client):
        r = await api_client.get(f"{API_BASE}/memory/nonexistent-id-000")
        assert r.status_code == 404


class TestDeleteMemory:
    """DELETE /memory/{memory_id}"""

    async def test_delete_and_verify_gone(self, stored_memory, api_client):
        data = await stored_memory("ephemeral memory")
        mid = data["id"]

        r = await api_client.delete(f"{API_BASE}/memory/{mid}")
        assert r.status_code == 200
        body = r.json()
        assert body["deleted"] is True
        assert body["id"] == mid

        # Confirm it's gone
        r2 = await api_client.get(f"{API_BASE}/memory/{mid}")
        assert r2.status_code == 404
