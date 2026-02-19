"""
Tests for concurrent operations. Marked as slow.
"""

import asyncio

import pytest

from tests.integration.conftest import API_BASE

# Semantically distinct content to avoid dedup (cosine > 0.95 threshold)
_DISTINCT_CONTENT = [
    "Python asyncio event loop processes coroutines for concurrent IO-bound tasks",
    "Docker containers isolate processes using Linux namespaces and cgroups",
    "PostgreSQL MVCC enables non-blocking reads during write transactions",
    "Redis pub/sub channels deliver messages to all connected subscribers",
    "Neo4j Cypher queries traverse graph relationships with MATCH patterns",
    "TLS 1.3 handshake completes in one round trip with forward secrecy",
    "Qdrant HNSW index trades memory for logarithmic nearest neighbor search",
    "FastAPI dependency injection resolves request-scoped instances automatically",
    "Git three-way merge finds common ancestor then applies both diffs",
    "Kubernetes horizontal pod autoscaler adjusts replicas based on CPU metrics",
]


@pytest.mark.slow
class TestConcurrentOperations:
    """Verify the API handles concurrent requests without errors."""

    async def test_concurrent_stores(self, api_client, test_domain, cleanup):
        """10 concurrent store requests should all succeed with unique IDs."""

        async def _store(i: int):
            r = await api_client.post(
                f"{API_BASE}/memory/store",
                json={
                    "content": f"{_DISTINCT_CONTENT[i]} ({test_domain})",
                    "domain": test_domain,
                },
            )
            return r

        responses = await asyncio.gather(*[_store(i) for i in range(10)])

        ids = set()
        for r in responses:
            assert r.status_code == 200, f"Store failed: {r.text}"
            data = r.json()
            assert data["created"] is True
            ids.add(data["id"])
            cleanup.track_memory(data["id"])

        # All 10 should have unique IDs
        assert len(ids) == 10

    async def test_concurrent_searches(self, stored_memory, api_client, test_domain):
        """10 concurrent searches should all return 200."""
        await stored_memory("base memory for concurrent search test", domain=test_domain)
        await asyncio.sleep(0.5)

        async def _search(i: int):
            r = await api_client.post(
                f"{API_BASE}/search/query",
                json={
                    "query": f"concurrent search {i}",
                    "domains": [test_domain],
                },
            )
            return r

        responses = await asyncio.gather(*[_search(i) for i in range(10)])

        for r in responses:
            assert r.status_code == 200

    async def test_mixed_store_and_search(self, api_client, test_domain, cleanup):
        """Interleaved stores and searches should not produce 500s."""

        async def _store(i: int):
            r = await api_client.post(
                f"{API_BASE}/memory/store",
                json={
                    "content": f"mixed op {_DISTINCT_CONTENT[i]} ({test_domain})",
                    "domain": test_domain,
                },
            )
            if r.status_code == 200:
                cleanup.track_memory(r.json()["id"])
            return r

        async def _search(i: int):
            r = await api_client.post(
                f"{API_BASE}/search/query",
                json={
                    "query": f"mixed op search {i}",
                    "domains": [test_domain],
                },
            )
            return r

        tasks = []
        for i in range(5):
            tasks.append(_store(i))
            tasks.append(_search(i))

        responses = await asyncio.gather(*tasks)

        for r in responses:
            assert r.status_code != 500, f"Got 500: {r.text}"
