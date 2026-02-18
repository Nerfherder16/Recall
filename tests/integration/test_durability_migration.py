"""
Integration tests for POST /admin/migrate/durability.

Tests the one-time migration that classifies pre-v2.2 memories
(null durability) into ephemeral/durable/permanent tiers.
"""

import os
import uuid

import pytest

from tests.integration.conftest import request_with_retry

API_BASE = os.environ.get("RECALL_API_URL", "http://localhost:8200")


class TestDurabilityMigration:
    """Tests for the durability migration endpoint."""

    async def _store_null_durability(self, api_client, cleanup, test_domain, **overrides):
        """Helper: store a memory without durability (null)."""
        payload = {
            "content": f"Migration test {uuid.uuid4().hex[:8]}",
            "memory_type": "semantic",
            "source": "user",
            "domain": test_domain,
            "importance": 0.5,
            **overrides,
        }
        # Explicitly do NOT include "durability" key
        payload.pop("durability", None)
        r = await api_client.post(f"{API_BASE}/memory/store", json=payload)
        assert r.status_code == 200, f"Store failed: {r.text}"
        data = r.json()
        cleanup.track_memory(data["id"])
        return data

    async def test_dry_run_does_not_modify(self, api_client, test_domain, cleanup):
        """Dry run should classify but NOT update durability in storage."""
        mems = []
        for i in range(3):
            m = await self._store_null_durability(
                api_client, cleanup, test_domain,
                content=f"Dry run test memory {i} {uuid.uuid4().hex[:8]}",
            )
            mems.append(m)

        r = await request_with_retry(
            api_client, "post",
            f"{API_BASE}/admin/migrate/durability",
            json={"dry_run": True},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["total_null"] >= 3
        assert data["classified"] >= 3
        assert data["errors"] == 0

        # Verify memories still have null durability
        for m in mems:
            r2 = await api_client.get(f"{API_BASE}/memory/{m['id']}")
            assert r2.status_code == 200
            assert r2.json()["durability"] is None

    async def test_wet_run_classifies_signal_tagged(self, api_client, test_domain, cleanup):
        """Memory with signal:fact tag should be classified as durable."""
        m = await self._store_null_durability(
            api_client, cleanup, test_domain,
            content=f"Redis uses port 6379 {uuid.uuid4().hex[:8]}",
            tags=["signal:fact"],
        )

        r = await request_with_retry(
            api_client, "post",
            f"{API_BASE}/admin/migrate/durability",
            json={"dry_run": False},
        )
        assert r.status_code == 200

        # Verify durability was set
        r2 = await api_client.get(f"{API_BASE}/memory/{m['id']}")
        assert r2.status_code == 200
        assert r2.json()["durability"] == "durable"

    async def test_wet_run_classifies_by_memory_type(self, api_client, test_domain, cleanup):
        """Episodic → ephemeral, procedural → durable."""
        ep = await self._store_null_durability(
            api_client, cleanup, test_domain,
            content=f"Session summary for today {uuid.uuid4().hex[:8]}",
            memory_type="episodic",
        )
        proc = await self._store_null_durability(
            api_client, cleanup, test_domain,
            content=f"Deploy by running docker compose up {uuid.uuid4().hex[:8]}",
            memory_type="procedural",
        )

        r = await request_with_retry(
            api_client, "post",
            f"{API_BASE}/admin/migrate/durability",
            json={"dry_run": False},
        )
        assert r.status_code == 200

        r_ep = await api_client.get(f"{API_BASE}/memory/{ep['id']}")
        assert r_ep.json()["durability"] == "ephemeral"

        r_proc = await api_client.get(f"{API_BASE}/memory/{proc['id']}")
        assert r_proc.json()["durability"] == "durable"

    async def test_permanent_regex_detection(self, api_client, test_domain, cleanup):
        """Content with IP + URL and importance >= 0.4 → permanent."""
        m = await self._store_null_durability(
            api_client, cleanup, test_domain,
            content=f"CasaOS at 192.168.50.19 dashboard http://192.168.50.19:8200 {uuid.uuid4().hex[:8]}",
            importance=0.7,
        )

        r = await request_with_retry(
            api_client, "post",
            f"{API_BASE}/admin/migrate/durability",
            json={"dry_run": False},
        )
        assert r.status_code == 200

        r2 = await api_client.get(f"{API_BASE}/memory/{m['id']}")
        assert r2.json()["durability"] == "permanent"

    async def test_idempotent_second_run(self, api_client, test_domain, cleanup):
        """Second run should find total_null=0 for already-classified memories."""
        await self._store_null_durability(
            api_client, cleanup, test_domain,
            content=f"Idempotent test {uuid.uuid4().hex[:8]}",
        )

        # First wet run
        r1 = await request_with_retry(
            api_client, "post",
            f"{API_BASE}/admin/migrate/durability",
            json={"dry_run": False},
        )
        assert r1.status_code == 200
        first_null = r1.json()["total_null"]
        assert first_null >= 1

        # Second dry run — our memory should no longer show as null
        r2 = await request_with_retry(
            api_client, "post",
            f"{API_BASE}/admin/migrate/durability",
            json={"dry_run": True},
        )
        assert r2.status_code == 200
        assert r2.json()["total_null"] < first_null

    async def test_response_sample_format(self, api_client, test_domain, cleanup):
        """Sample entries should have the expected keys."""
        await self._store_null_durability(
            api_client, cleanup, test_domain,
            content=f"Sample format test {uuid.uuid4().hex[:8]}",
        )

        r = await request_with_retry(
            api_client, "post",
            f"{API_BASE}/admin/migrate/durability",
            json={"dry_run": True},
        )
        assert r.status_code == 200
        data = r.json()

        assert "sample" in data
        assert len(data["sample"]) >= 1
        entry = data["sample"][0]
        assert "id" in entry
        assert "content_preview" in entry
        assert "assigned_tier" in entry
        assert "reason" in entry
        assert entry["assigned_tier"] in ("ephemeral", "durable", "permanent")
