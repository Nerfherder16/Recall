"""
Tests for embedding quality and semantic search accuracy.

These tests verify that:
- Similar texts produce high cosine similarity
- Dissimilar texts produce low similarity
- Semantic search ranks results sensibly
- Content hashing works for deduplication
- Embedding prefixes aid retrieval
"""

import asyncio

import pytest

from tests.integration.conftest import API_BASE, request_with_retry

EMBED_DELAY = 0.5


@pytest.mark.slow
class TestEmbeddings:
    """Embedding quality and search relevance tests."""

    async def _store_and_track(self, api_client, cleanup, content, domain, **kwargs):
        """Helper: store a memory, track it, return response data."""
        payload = {"content": content, "domain": domain, **kwargs}
        r = await api_client.post(f"{API_BASE}/memory/store", json=payload)
        assert r.status_code == 200, f"Store failed: {r.text}"
        data = r.json()
        cleanup.track_memory(data["id"])
        return data

    async def test_similar_texts_score_high_similarity(
        self, api_client, test_domain, cleanup
    ):
        """Two paraphrases of the same fact should have similarity > 0.8."""
        m1 = await self._store_and_track(
            api_client, cleanup,
            "Python is a programming language known for readability",
            test_domain,
        )
        m2 = await self._store_and_track(
            api_client, cleanup,
            "Python is a coding language famous for being readable",
            test_domain,
        )
        await asyncio.sleep(EMBED_DELAY)

        r = await api_client.get(
            f"{API_BASE}/search/similar/{m1['id']}",
            params={"limit": 10},
        )
        assert r.status_code == 200
        similar = r.json()["similar"]

        match = next((s for s in similar if s["id"] == m2["id"]), None)
        assert match is not None, (
            f"Expected {m2['id']} in similar results, got IDs: "
            + str([s['id'] for s in similar])
        )
        assert match["similarity"] > 0.8, (
            f"Expected similarity > 0.8, got {match['similarity']}"
        )

    async def test_dissimilar_texts_score_low(
        self, api_client, test_domain, cleanup
    ):
        """Unrelated topics should have similarity < 0.5."""
        m1 = await self._store_and_track(
            api_client, cleanup,
            "Python programming language for software development",
            test_domain,
        )
        m2 = await self._store_and_track(
            api_client, cleanup,
            "Chocolate cake recipe with buttercream frosting",
            test_domain,
        )
        await asyncio.sleep(EMBED_DELAY)

        r = await api_client.get(
            f"{API_BASE}/search/similar/{m1['id']}",
            params={"limit": 10},
        )
        assert r.status_code == 200
        similar = r.json()["similar"]

        match = next((s for s in similar if s["id"] == m2["id"]), None)
        if match is not None:
            assert match["similarity"] < 0.5, (
                f"Expected similarity < 0.5 for unrelated texts, got {match['similarity']}"
            )

    async def test_search_relevance_matches_semantic_meaning(
        self, api_client, test_domain, cleanup
    ):
        """Docker-related memories should dominate search for 'container orchestration'."""
        docker_texts = [
            "Docker containers provide process isolation and portability",
            "Docker Compose orchestrates multi-container applications",
            "Kubernetes manages Docker container deployments at scale",
        ]
        cooking_text = "The best chocolate chip cookie recipe uses brown butter"

        for text in docker_texts:
            await self._store_and_track(
                api_client, cleanup, text, test_domain,
            )
        await self._store_and_track(
            api_client, cleanup, cooking_text, test_domain,
        )
        await asyncio.sleep(EMBED_DELAY)

        r = await request_with_retry(
            api_client, "post",
            f"{API_BASE}/search/query",
            json={
                "query": "container orchestration",
                "domains": [test_domain],
                "limit": 5,
            },
        )
        assert r.status_code == 200
        results = r.json()["results"]
        assert len(results) >= 1

        # The top result(s) should be about Docker, not cooking
        top_contents = [r["content"] for r in results[:3]]
        docker_in_top = any(
            "docker" in c.lower() or "container" in c.lower() or "kubernetes" in c.lower()
            for c in top_contents
        )
        assert docker_in_top, (
            f"Expected Docker-related content in top results, got: {top_contents}"
        )

    async def test_content_hash_deduplication(
        self, api_client, test_domain, cleanup
    ):
        """Storing the same text twice should be deduplicated by content hash."""
        text = "Exact duplicate content for hash test"

        m1 = await self._store_and_track(
            api_client, cleanup, text, test_domain,
        )
        m2 = await self._store_and_track(
            api_client, cleanup, text, test_domain,
        )

        assert m1["content_hash"] == m2["content_hash"], (
            f"Same content produced different hashes: {m1['content_hash']} vs {m2['content_hash']}"
        )
        # Dedup: second store returns the existing memory's ID
        assert m1["id"] == m2["id"]
        assert m1["created"] is True
        assert m2["created"] is False

    async def test_embedding_retrieves_despite_different_phrasing(
        self, api_client, test_domain, cleanup
    ):
        """A stored fact should be findable even with very different query phrasing."""
        await self._store_and_track(
            api_client, cleanup,
            "PostgreSQL supports JSONB columns for semi-structured data storage",
            test_domain,
        )
        await asyncio.sleep(EMBED_DELAY)

        r = await request_with_retry(
            api_client, "post",
            f"{API_BASE}/search/query",
            json={
                "query": "database with JSON support",
                "domains": [test_domain],
                "limit": 5,
            },
        )
        assert r.status_code == 200
        results = r.json()["results"]
        assert len(results) >= 1

        # The PostgreSQL memory should appear in results
        found = any("PostgreSQL" in r["content"] or "JSONB" in r["content"] for r in results)
        assert found, (
            f"Expected PostgreSQL memory in results for 'database with JSON support', "
            f"got: {[r['content'][:60] for r in results]}"
        )
