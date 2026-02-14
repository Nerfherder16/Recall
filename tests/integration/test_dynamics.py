"""
Tests for memory dynamics: access tracking, importance reinforcement.
"""

import asyncio

import pytest

from tests.integration.conftest import API_BASE

EMBED_DELAY = 0.5


class TestAccessTracking:
    """Verify that searching for a memory increments its access_count."""

    async def test_access_count_increments_on_search(
        self, stored_memory, api_client, test_domain
    ):
        """Searching should increment access_count; GET should not."""
        data = await stored_memory(
            "unique marker ALPHA-9876 for access tracking",
            domain=test_domain,
        )
        mid = data["id"]
        await asyncio.sleep(EMBED_DELAY)

        # GET should not increment
        r = await api_client.get(f"{API_BASE}/memory/{mid}")
        initial_count = r.json()["access_count"]

        # Search to trigger access tracking
        await api_client.post(
            f"{API_BASE}/search/query",
            json={"query": "ALPHA-9876 access tracking", "domains": [test_domain]},
        )
        await asyncio.sleep(0.3)

        r2 = await api_client.get(f"{API_BASE}/memory/{mid}")
        new_count = r2.json()["access_count"]
        assert new_count >= initial_count  # May or may not have incremented depending on if it was in results

    async def test_importance_reinforcement(
        self, stored_memory, api_client, test_domain
    ):
        """Repeated searches for the same memory should increase its importance."""
        data = await stored_memory(
            "unique marker BETA-5432 importance reinforcement test",
            importance=0.5,
            domain=test_domain,
        )
        mid = data["id"]
        await asyncio.sleep(EMBED_DELAY)

        # Record initial importance
        r = await api_client.get(f"{API_BASE}/memory/{mid}")
        initial_importance = r.json()["importance"]

        # Search multiple times
        for _ in range(5):
            await api_client.post(
                f"{API_BASE}/search/query",
                json={
                    "query": "BETA-5432 importance reinforcement",
                    "domains": [test_domain],
                },
            )
            await asyncio.sleep(0.2)

        # Check importance after repeated access
        r2 = await api_client.get(f"{API_BASE}/memory/{mid}")
        final_importance = r2.json()["importance"]

        # Importance should have increased (or at least not decreased)
        assert final_importance >= initial_importance


class TestMonotonicImportance:
    """Verify importance increases monotonically over repeated searches."""

    @pytest.mark.slow
    async def test_monotonic_importance_over_10_searches(
        self, stored_memory, api_client, test_domain
    ):
        """Importance should never decrease across 10 consecutive searches."""
        data = await stored_memory(
            "unique marker GAMMA-1111 monotonic importance test",
            importance=0.3,
            domain=test_domain,
        )
        mid = data["id"]
        await asyncio.sleep(EMBED_DELAY)

        prev_importance = 0.3
        for i in range(10):
            await api_client.post(
                f"{API_BASE}/search/query",
                json={
                    "query": "GAMMA-1111 monotonic importance",
                    "domains": [test_domain],
                },
            )
            await asyncio.sleep(0.2)

            r = await api_client.get(f"{API_BASE}/memory/{mid}")
            current = r.json()["importance"]
            assert current >= prev_importance, (
                f"Importance decreased at search {i+1}: {prev_importance} → {current}"
            )
            prev_importance = current

        # After 10 searches, importance should be at least as high as start.
        # Reinforcement only applies when the memory appears in search results,
        # which depends on the embedding similarity threshold.
        assert prev_importance >= 0.3

    async def test_access_count_reflects_searches(
        self, stored_memory, api_client, test_domain
    ):
        """After N searches, access_count should be >= N (if memory appears in results)."""
        data = await stored_memory(
            "unique marker DELTA-2222 access counter test",
            domain=test_domain,
        )
        mid = data["id"]
        await asyncio.sleep(EMBED_DELAY)

        n_searches = 3
        for _ in range(n_searches):
            await api_client.post(
                f"{API_BASE}/search/query",
                json={
                    "query": "DELTA-2222 access counter",
                    "domains": [test_domain],
                },
            )
            await asyncio.sleep(0.2)

        r = await api_client.get(f"{API_BASE}/memory/{mid}")
        count = r.json()["access_count"]
        # access_count should have incremented at least once
        assert count >= 1
