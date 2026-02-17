"""
Phase 14A integration tests — Memory pinning.
"""

import asyncio
import os

import pytest

API_BASE = os.environ.get("RECALL_API_URL", "http://localhost:8200")


class TestMemoryPinning:
    """Test pin/unpin endpoints and decay immunity."""

    async def test_pin_memory(self, api_client, stored_memory, cleanup):
        """Pin a memory → GET confirms pinned: true."""
        mem = await stored_memory("Architecture: use event sourcing for audit log")

        # Pin it
        r = await api_client.post(f"{API_BASE}/memory/{mem['id']}/pin")
        assert r.status_code == 200
        data = r.json()
        assert data["pinned"] is True
        assert data["id"] == mem["id"]

        # Verify via GET
        r = await api_client.get(f"{API_BASE}/memory/{mem['id']}")
        assert r.status_code == 200
        assert r.json()["pinned"] is True

    async def test_unpin_memory(self, api_client, stored_memory, cleanup):
        """Pin then unpin → GET confirms pinned: false."""
        mem = await stored_memory("Decision: use PostgreSQL for audit")

        # Pin
        await api_client.post(f"{API_BASE}/memory/{mem['id']}/pin")

        # Unpin
        r = await api_client.delete(f"{API_BASE}/memory/{mem['id']}/pin")
        assert r.status_code == 200
        data = r.json()
        assert data["pinned"] is False

        # Verify via GET
        r = await api_client.get(f"{API_BASE}/memory/{mem['id']}")
        assert r.status_code == 200
        assert r.json()["pinned"] is False

    async def test_pin_nonexistent_404(self, api_client):
        """Pin a nonexistent memory → 404."""
        r = await api_client.post(f"{API_BASE}/memory/00000000-0000-0000-0000-000000000000/pin")
        assert r.status_code == 404

    async def test_pinned_memory_survives_decay(self, api_client, stored_memory, cleanup):
        """Pinned memory should not have its importance reduced by decay."""
        mem = await stored_memory(
            "Critical: never use pickle with untrusted data",
            importance=0.8,
        )

        # Pin it
        await api_client.post(f"{API_BASE}/memory/{mem['id']}/pin")

        # Trigger decay with large simulate_hours
        r = await api_client.post(
            f"{API_BASE}/admin/decay",
            json={"simulate_hours": 200},
        )
        assert r.status_code == 200

        # Verify importance unchanged
        r = await api_client.get(f"{API_BASE}/memory/{mem['id']}")
        assert r.status_code == 200
        data = r.json()
        assert data["importance"] >= 0.79, f"Pinned memory decayed: {data['importance']}"

    async def test_unpinned_memory_decays(self, api_client, stored_memory, cleanup):
        """Unpinned memory should decay normally."""
        mem = await stored_memory(
            "Routine: ran npm install yesterday evening",
            importance=0.5,
        )
        await asyncio.sleep(0.5)

        # Trigger decay with large simulate_hours
        r = await api_client.post(
            f"{API_BASE}/admin/decay",
            json={"simulate_hours": 200},
        )
        assert r.status_code == 200

        # Verify importance decreased
        r = await api_client.get(f"{API_BASE}/memory/{mem['id']}")
        assert r.status_code == 200
        data = r.json()
        assert data["importance"] < 0.5, f"Memory didn't decay: {data['importance']}"
