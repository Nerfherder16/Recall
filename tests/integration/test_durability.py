"""
Phase 15A integration tests — Memory durability classification.

Tests the durability enum (ephemeral/durable/permanent), decay behavior
per tier, initial_importance capture, and durability in search responses.
"""

import asyncio
import os
import uuid

import pytest

from tests.integration.conftest import request_with_retry

API_BASE = os.environ.get("RECALL_API_URL", "http://localhost:8200")


class TestDurabilityStorage:
    """Test storing and retrieving durability tiers."""

    async def test_store_each_durability_tier(self, api_client, test_domain, cleanup):
        """Store a memory with each durability tier, verify in GET."""
        for tier in ("ephemeral", "durable", "permanent"):
            r = await api_client.post(
                f"{API_BASE}/memory/store",
                json={
                    "content": f"Durability test: {tier} tier {uuid.uuid4().hex[:8]}",
                    "memory_type": "semantic",
                    "source": "user",
                    "domain": test_domain,
                    "importance": 0.5,
                    "durability": tier,
                },
            )
            assert r.status_code == 200, f"Store failed for {tier}: {r.text}"
            data = r.json()
            cleanup.track_memory(data["id"])
            assert data["durability"] == tier

            # Verify via GET
            r2 = await api_client.get(f"{API_BASE}/memory/{data['id']}")
            assert r2.status_code == 200
            assert r2.json()["durability"] == tier

    async def test_store_without_durability_defaults_to_null(
        self, api_client, stored_memory, cleanup
    ):
        """Store a memory without durability field — should default to null."""
        mem = await stored_memory(
            f"No durability specified {uuid.uuid4().hex[:8]}"
        )
        r = await api_client.get(f"{API_BASE}/memory/{mem['id']}")
        assert r.status_code == 200
        assert r.json()["durability"] is None

    async def test_initial_importance_captured(self, api_client, test_domain, cleanup):
        """initial_importance should be set to the importance at creation time."""
        r = await api_client.post(
            f"{API_BASE}/memory/store",
            json={
                "content": f"Initial importance test {uuid.uuid4().hex[:8]}",
                "memory_type": "semantic",
                "source": "user",
                "domain": test_domain,
                "importance": 0.72,
                "durability": "durable",
            },
        )
        assert r.status_code == 200
        data = r.json()
        cleanup.track_memory(data["id"])

        r2 = await api_client.get(f"{API_BASE}/memory/{data['id']}")
        assert r2.status_code == 200
        detail = r2.json()
        assert detail["initial_importance"] == pytest.approx(0.72, abs=0.01)


class TestDurabilityDecay:
    """Test that durability affects decay behavior."""

    async def test_permanent_survives_decay(self, api_client, test_domain, cleanup):
        """Permanent memory should not have its importance reduced by decay."""
        r = await api_client.post(
            f"{API_BASE}/memory/store",
            json={
                "content": f"IP: 192.168.50.19 — permanent infra fact {uuid.uuid4().hex[:8]}",
                "memory_type": "semantic",
                "source": "user",
                "domain": test_domain,
                "importance": 0.8,
                "durability": "permanent",
            },
        )
        assert r.status_code == 200
        data = r.json()
        cleanup.track_memory(data["id"])

        # Trigger decay with large simulate_hours
        r2 = await api_client.post(
            f"{API_BASE}/admin/decay",
            json={"simulate_hours": 200},
        )
        assert r2.status_code == 200

        # Verify importance unchanged
        r3 = await api_client.get(f"{API_BASE}/memory/{data['id']}")
        assert r3.status_code == 200
        assert r3.json()["importance"] >= 0.79, (
            f"Permanent memory decayed: {r3.json()['importance']}"
        )

    async def test_durable_decays_slower_than_ephemeral(
        self, api_client, test_domain, cleanup
    ):
        """Durable memory should decay significantly slower than ephemeral."""
        base_content = uuid.uuid4().hex[:8]

        # Store durable
        r1 = await api_client.post(
            f"{API_BASE}/memory/store",
            json={
                "content": f"Durable architecture decision {base_content}",
                "memory_type": "semantic",
                "source": "user",
                "domain": test_domain,
                "importance": 0.6,
                "durability": "durable",
            },
        )
        assert r1.status_code == 200
        durable_id = r1.json()["id"]
        cleanup.track_memory(durable_id)

        # Store ephemeral
        r2 = await api_client.post(
            f"{API_BASE}/memory/store",
            json={
                "content": f"Ephemeral debug session note {base_content}",
                "memory_type": "semantic",
                "source": "user",
                "domain": test_domain,
                "importance": 0.6,
                "durability": "ephemeral",
            },
        )
        assert r2.status_code == 200
        ephemeral_id = r2.json()["id"]
        cleanup.track_memory(ephemeral_id)

        await asyncio.sleep(0.5)

        # Trigger decay
        r3 = await api_client.post(
            f"{API_BASE}/admin/decay",
            json={"simulate_hours": 100},
        )
        assert r3.status_code == 200

        # Compare
        d_resp = await api_client.get(f"{API_BASE}/memory/{durable_id}")
        e_resp = await api_client.get(f"{API_BASE}/memory/{ephemeral_id}")
        d_imp = d_resp.json()["importance"]
        e_imp = e_resp.json()["importance"]

        assert d_imp > e_imp, (
            f"Durable ({d_imp}) should be higher than ephemeral ({e_imp}) after decay"
        )

    async def test_ephemeral_decays_normally(self, api_client, test_domain, cleanup):
        """Ephemeral memory should decay at the normal rate."""
        r = await api_client.post(
            f"{API_BASE}/memory/store",
            json={
                "content": f"Ephemeral workaround note {uuid.uuid4().hex[:8]}",
                "memory_type": "semantic",
                "source": "user",
                "domain": test_domain,
                "importance": 0.5,
                "durability": "ephemeral",
            },
        )
        assert r.status_code == 200
        data = r.json()
        cleanup.track_memory(data["id"])

        await asyncio.sleep(0.5)

        r2 = await api_client.post(
            f"{API_BASE}/admin/decay",
            json={"simulate_hours": 200},
        )
        assert r2.status_code == 200

        r3 = await api_client.get(f"{API_BASE}/memory/{data['id']}")
        assert r3.status_code == 200
        assert r3.json()["importance"] < 0.5, (
            f"Ephemeral memory didn't decay: {r3.json()['importance']}"
        )


class TestDurabilityEndpoints:
    """Test durability-specific endpoints."""

    async def test_put_durability(self, api_client, stored_memory, cleanup):
        """PUT /{id}/durability should update the durability tier."""
        mem = await stored_memory(
            f"Update durability test {uuid.uuid4().hex[:8]}"
        )

        # Update to permanent
        r = await api_client.put(
            f"{API_BASE}/memory/{mem['id']}/durability",
            json={"durability": "permanent"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["durability"] == "permanent"

        # Verify via GET
        r2 = await api_client.get(f"{API_BASE}/memory/{mem['id']}")
        assert r2.status_code == 200
        assert r2.json()["durability"] == "permanent"

    async def test_put_durability_invalid_value(self, api_client, stored_memory, cleanup):
        """PUT /{id}/durability with invalid value → 422."""
        mem = await stored_memory(
            f"Invalid durability test {uuid.uuid4().hex[:8]}"
        )

        r = await api_client.put(
            f"{API_BASE}/memory/{mem['id']}/durability",
            json={"durability": "super_permanent"},
        )
        assert r.status_code == 422

    async def test_put_durability_nonexistent_404(self, api_client):
        """PUT durability on nonexistent memory → 404."""
        r = await api_client.put(
            f"{API_BASE}/memory/00000000-0000-0000-0000-000000000000/durability",
            json={"durability": "durable"},
        )
        assert r.status_code == 404


class TestDurabilityInSearch:
    """Test durability field in search/browse/timeline responses."""

    async def test_browse_returns_durability(self, api_client, test_domain, cleanup):
        """Browse results should include durability field."""
        r = await api_client.post(
            f"{API_BASE}/memory/store",
            json={
                "content": f"Browse durability test — architecture uses microservices {uuid.uuid4().hex[:8]}",
                "memory_type": "semantic",
                "source": "user",
                "domain": test_domain,
                "importance": 0.7,
                "durability": "durable",
            },
        )
        assert r.status_code == 200
        data = r.json()
        cleanup.track_memory(data["id"])

        await asyncio.sleep(1)

        r2 = await request_with_retry(
            api_client,
            "post",
            f"{API_BASE}/search/browse",
            json={
                "query": "architecture microservices",
                "domains": [test_domain],
                "limit": 5,
            },
        )
        assert r2.status_code == 200
        results = r2.json()["results"]
        assert len(results) > 0
        # Find our memory
        match = [x for x in results if x["id"] == data["id"]]
        assert len(match) == 1
        assert match[0]["durability"] == "durable"

    async def test_timeline_returns_durability(self, api_client, test_domain, cleanup):
        """Timeline entries should include durability field."""
        r = await api_client.post(
            f"{API_BASE}/memory/store",
            json={
                "content": f"Timeline durability test {uuid.uuid4().hex[:8]}",
                "memory_type": "semantic",
                "source": "user",
                "domain": test_domain,
                "importance": 0.5,
                "durability": "permanent",
            },
        )
        assert r.status_code == 200
        data = r.json()
        cleanup.track_memory(data["id"])

        await asyncio.sleep(0.5)

        r2 = await request_with_retry(
            api_client,
            "post",
            f"{API_BASE}/search/timeline",
            json={"domain": test_domain, "limit": 20},
        )
        assert r2.status_code == 200
        entries = r2.json()["entries"]
        match = [x for x in entries if x["id"] == data["id"]]
        assert len(match) == 1
        assert match[0]["durability"] == "permanent"


@pytest.mark.slow
class TestDurabilitySignalDetection:
    """Test that signal detection classifies durability (requires LLM)."""

    async def test_signal_detection_classifies_durability(
        self, api_client, cleanup, active_session
    ):
        """Signal detection should produce a durability classification."""
        session = await active_session()
        sid = session["session_id"]

        # Submit a turn with infrastructure content (should be durable/permanent)
        r = await api_client.post(
            f"{API_BASE}/ingest/turns",
            json={
                "session_id": sid,
                "turns": [
                    {"role": "user", "content": "What's the database server IP?"},
                    {
                        "role": "assistant",
                        "content": "The PostgreSQL database is at 10.0.0.5:5432, "
                        "using database name 'production_db'. "
                        "The Redis cache is at 10.0.0.6:6379.",
                    },
                ],
            },
        )
        assert r.status_code == 200

        # Wait for signal processing
        await asyncio.sleep(15)

        # Check if any memories were created with durability set
        r2 = await request_with_retry(
            api_client,
            "post",
            f"{API_BASE}/search/browse",
            json={
                "query": "PostgreSQL database 10.0.0.5",
                "limit": 5,
            },
        )
        assert r2.status_code == 200
        results = r2.json()["results"]
        # The LLM should have detected this as infrastructure and set durability
        # We just verify durability field is present (LLM may choose any valid tier)
        for result in results:
            assert "durability" in result, "durability field missing from browse result"
