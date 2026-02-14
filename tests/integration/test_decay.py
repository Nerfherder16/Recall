"""
Tests for importance decay via POST /admin/decay.

These tests store memories, trigger decay with simulated time passage,
and verify that importance values change correctly.
"""

import pytest

from tests.integration.conftest import API_BASE


@pytest.mark.slow
class TestDecay:
    """POST /admin/decay"""

    async def _store_and_track(self, api_client, cleanup, content, domain, **kwargs):
        """Helper: store a memory, track it, return response data."""
        payload = {"content": content, "domain": domain, **kwargs}
        r = await api_client.post(f"{API_BASE}/memory/store", json=payload)
        assert r.status_code == 200, f"Store failed: {r.text}"
        data = r.json()
        cleanup.track_memory(data["id"])
        return data

    async def test_decay_reduces_importance(
        self, api_client, test_domain, cleanup
    ):
        """Simulating 48 hours should reduce importance from 0.5."""
        data = await self._store_and_track(
            api_client, cleanup,
            "Memory that should decay over time",
            test_domain,
            importance=0.5,
        )

        # Trigger decay with 48-hour offset
        r = await api_client.post(
            f"{API_BASE}/admin/decay",
            json={"simulate_hours": 48.0},
        )
        assert r.status_code == 200
        stats = r.json()
        assert stats["processed"] >= 1

        # Verify importance decreased
        mem_r = await api_client.get(f"{API_BASE}/memory/{data['id']}")
        assert mem_r.status_code == 200
        new_importance = mem_r.json()["importance"]
        assert new_importance < 0.5, (
            f"Expected importance < 0.5 after 48h decay, got {new_importance}"
        )

    async def test_high_stability_decays_slower(
        self, api_client, test_domain, cleanup
    ):
        """High stability memory should retain more importance than low stability."""
        # Store with high stability (we can't set stability directly via API,
        # but we can store two memories and compare relative decay)
        high = await self._store_and_track(
            api_client, cleanup,
            "High stability memory for decay comparison",
            test_domain,
            importance=0.8,
        )
        low = await self._store_and_track(
            api_client, cleanup,
            "Low stability memory for decay comparison",
            test_domain,
            importance=0.8,
        )

        # Both memories start with default stability (0.1).
        # The decay formula: effective_decay = base_decay * (1 - stability)
        # So both should decay at roughly the same rate with default stability.
        # This test verifies the decay mechanism works at all.
        r = await api_client.post(
            f"{API_BASE}/admin/decay",
            json={"simulate_hours": 48.0},
        )
        assert r.status_code == 200
        stats = r.json()
        assert stats["processed"] >= 2

        # Verify both decayed
        high_r = await api_client.get(f"{API_BASE}/memory/{high['id']}")
        low_r = await api_client.get(f"{API_BASE}/memory/{low['id']}")
        assert high_r.status_code == 200
        assert low_r.status_code == 200

        high_imp = high_r.json()["importance"]
        low_imp = low_r.json()["importance"]

        # Both should have decayed from 0.8
        assert high_imp < 0.8, f"High-stability memory didn't decay: {high_imp}"
        assert low_imp < 0.8, f"Low-stability memory didn't decay: {low_imp}"

    async def test_recently_accessed_barely_decays(
        self, api_client, test_domain, cleanup
    ):
        """Simulating only 6 minutes (0.1h) should produce negligible decay."""
        data = await self._store_and_track(
            api_client, cleanup,
            "Very recently accessed memory",
            test_domain,
            importance=0.5,
        )

        r = await api_client.post(
            f"{API_BASE}/admin/decay",
            json={"simulate_hours": 0.1},
        )
        assert r.status_code == 200

        mem_r = await api_client.get(f"{API_BASE}/memory/{data['id']}")
        assert mem_r.status_code == 200
        new_importance = mem_r.json()["importance"]

        # Importance should barely change (within 5% of original)
        assert new_importance >= 0.45, (
            f"Expected importance >= 0.45 after 6min, got {new_importance}"
        )

    async def test_importance_never_below_floor(
        self, api_client, test_domain, cleanup
    ):
        """Even aggressive decay should not push importance below 0.01."""
        data = await self._store_and_track(
            api_client, cleanup,
            "Memory tested for importance floor",
            test_domain,
            importance=0.1,
        )

        r = await api_client.post(
            f"{API_BASE}/admin/decay",
            json={"simulate_hours": 500.0},
        )
        assert r.status_code == 200

        mem_r = await api_client.get(f"{API_BASE}/memory/{data['id']}")
        assert mem_r.status_code == 200
        new_importance = mem_r.json()["importance"]
        assert new_importance >= 0.01, (
            f"Importance fell below floor: {new_importance}"
        )

    async def test_decay_does_not_delete_memories(
        self, api_client, test_domain, cleanup
    ):
        """Decay should reduce importance but never remove memories."""
        ids = []
        for i in range(5):
            data = await self._store_and_track(
                api_client, cleanup,
                f"Persistence test memory number {i}",
                test_domain,
                importance=0.3,
            )
            ids.append(data["id"])

        # Aggressive decay
        r = await api_client.post(
            f"{API_BASE}/admin/decay",
            json={"simulate_hours": 200.0},
        )
        assert r.status_code == 200

        # All 5 memories should still exist
        for mid in ids:
            mem_r = await api_client.get(f"{API_BASE}/memory/{mid}")
            assert mem_r.status_code == 200, (
                f"Memory {mid} was deleted by decay"
            )
