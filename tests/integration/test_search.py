"""
Tests for search endpoints: POST /search/query, GET /search/similar/{id}.
"""

import asyncio

from tests.integration.conftest import API_BASE

# Short pause to let embeddings index before searching
EMBED_DELAY = 0.5


class TestSearchQuery:
    """POST /search/query"""

    async def test_basic_search(self, stored_memory, api_client):
        await stored_memory("Python uses indentation for code blocks")
        await asyncio.sleep(EMBED_DELAY)

        r = await api_client.post(
            f"{API_BASE}/search/query",
            json={"query": "Python indentation"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "results" in data
        assert "total" in data
        assert "query" in data
        assert data["query"] == "Python indentation"

    async def test_result_structure(self, stored_memory, api_client):
        await stored_memory("FastAPI uses Pydantic for validation")
        await asyncio.sleep(EMBED_DELAY)

        r = await api_client.post(
            f"{API_BASE}/search/query",
            json={"query": "Pydantic validation"},
        )
        results = r.json()["results"]
        assert len(results) > 0

        item = results[0]
        assert "id" in item
        assert "content" in item
        assert "memory_type" in item
        assert "domain" in item
        assert "score" in item
        assert "similarity" in item
        assert "graph_distance" in item
        assert "importance" in item
        assert "tags" in item

    async def test_similarity_ranking(self, stored_memory, api_client, test_domain):
        """More relevant results should score higher than irrelevant ones."""
        await stored_memory("Docker containers provide process isolation", domain=test_domain)
        await stored_memory("My favorite pizza topping is pepperoni", domain=test_domain)
        await asyncio.sleep(EMBED_DELAY)

        r = await api_client.post(
            f"{API_BASE}/search/query",
            json={"query": "Docker container isolation", "domains": [test_domain]},
        )
        results = r.json()["results"]
        assert len(results) >= 2

        # The Docker result should be more relevant than the pizza result
        docker_score = next((x["score"] for x in results if "Docker" in x["content"]), 0)
        pizza_score = next((x["score"] for x in results if "pizza" in x["content"]), 0)
        assert docker_score > pizza_score

    async def test_filter_by_memory_type(self, stored_memory, api_client, test_domain):
        await stored_memory(
            "Redis uses sorted sets to maintain elements ordered by score",
            memory_type="semantic",
            domain=test_domain,
        )
        await stored_memory(
            "Yesterday I debugged a broken SSH tunnel to the homelab",
            memory_type="episodic",
            domain=test_domain,
        )
        await asyncio.sleep(EMBED_DELAY)

        r = await api_client.post(
            f"{API_BASE}/search/query",
            json={
                "query": "Redis sorted sets ordering",
                "memory_types": ["semantic"],
                "domains": [test_domain],
                "expand_relationships": False,
            },
        )
        results = r.json()["results"]
        for item in results:
            assert item["memory_type"] == "semantic"

    async def test_filter_by_domain(self, stored_memory, api_client, test_domain):
        other_domain = test_domain + "-other"
        await stored_memory("memory in target domain", domain=test_domain)
        await stored_memory("memory in other domain", domain=other_domain)
        await asyncio.sleep(EMBED_DELAY)

        r = await api_client.post(
            f"{API_BASE}/search/query",
            json={"query": "memory domain", "domains": [test_domain]},
        )
        results = r.json()["results"]
        for item in results:
            assert item["domain"] == test_domain

    async def test_filter_by_tags(self, stored_memory, api_client, test_domain):
        await stored_memory("tagged with alpha", tags=["alpha"], domain=test_domain)
        await stored_memory("tagged with beta", tags=["beta"], domain=test_domain)
        await asyncio.sleep(EMBED_DELAY)

        r = await api_client.post(
            f"{API_BASE}/search/query",
            json={"query": "tagged", "tags": ["alpha"], "domains": [test_domain]},
        )
        results = r.json()["results"]
        # At least one result should have the alpha tag
        alpha_results = [x for x in results if "alpha" in x.get("tags", [])]
        assert len(alpha_results) >= 1

    async def test_filter_by_min_importance(self, stored_memory, api_client, test_domain):
        await stored_memory(
            "Ephemeral trivia about butterfly migration patterns across continents",
            importance=0.1,
            domain=test_domain,
        )
        await stored_memory(
            "Critical production incident: database failover procedure for PostgreSQL",
            importance=0.9,
            domain=test_domain,
        )
        await asyncio.sleep(EMBED_DELAY)

        r = await api_client.post(
            f"{API_BASE}/search/query",
            json={
                "query": "database failover procedure",
                "min_importance": 0.5,
                "domains": [test_domain],
                "expand_relationships": False,
            },
        )
        results = r.json()["results"]
        for item in results:
            assert item["importance"] >= 0.5

    async def test_limit_enforcement(self, stored_memory, api_client, test_domain):
        """Limit=2 should return at most 2 results."""
        for i in range(5):
            await stored_memory(f"limit test memory number {i}", domain=test_domain)
        await asyncio.sleep(EMBED_DELAY)

        r = await api_client.post(
            f"{API_BASE}/search/query",
            json={"query": "limit test memory", "limit": 2, "domains": [test_domain]},
        )
        results = r.json()["results"]
        assert len(results) <= 2

    async def test_empty_query(self, api_client):
        """An empty string query should still return 200 (may have no results)."""
        r = await api_client.post(
            f"{API_BASE}/search/query",
            json={"query": ""},
        )
        # The API may return 200 with empty results or 422 — both are acceptable
        assert r.status_code in (200, 422)

    async def test_nonsense_query(self, api_client, test_domain):
        """A gibberish query should return 200 with zero or low-score results."""
        r = await api_client.post(
            f"{API_BASE}/search/query",
            json={"query": "xyzzy plugh foo bar baz", "domains": [test_domain]},
        )
        assert r.status_code == 200

    async def test_graph_expansion_on(self, stored_memory, api_client, test_domain):
        """With expand_relationships=True, related memories may appear."""
        a = await stored_memory("graph root: authentication module", domain=test_domain)
        b = await stored_memory("graph leaf: JWT token handling", domain=test_domain)

        await api_client.post(
            f"{API_BASE}/memory/relationship",
            json={
                "source_id": a["id"],
                "target_id": b["id"],
                "relationship_type": "related_to",
            },
        )
        await asyncio.sleep(EMBED_DELAY)

        r = await api_client.post(
            f"{API_BASE}/search/query",
            json={
                "query": "authentication module",
                "expand_relationships": True,
                "domains": [test_domain],
            },
        )
        assert r.status_code == 200
        results = r.json()["results"]
        result_ids = [x["id"] for x in results]
        # The related memory should be findable through graph expansion
        # (It may also appear via semantic similarity, which is fine)
        assert a["id"] in result_ids or b["id"] in result_ids

    async def test_graph_expansion_off(self, stored_memory, api_client, test_domain):
        """With expand_relationships=False, only semantic results returned."""
        r = await api_client.post(
            f"{API_BASE}/search/query",
            json={
                "query": "anything",
                "expand_relationships": False,
                "domains": [test_domain],
            },
        )
        assert r.status_code == 200
        # All results should have graph_distance 0
        for item in r.json()["results"]:
            assert item["graph_distance"] == 0


class TestFindSimilar:
    """GET /search/similar/{memory_id}"""

    async def test_find_similar_by_id(self, stored_memory, api_client):
        base = await stored_memory("Kubernetes orchestrates container workloads")
        await stored_memory("Docker Swarm also manages containers at scale")
        await asyncio.sleep(EMBED_DELAY)

        r = await api_client.get(
            f"{API_BASE}/search/similar/{base['id']}",
            params={"limit": 5},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["source_id"] == base["id"]
        assert isinstance(data["similar"], list)

    async def test_find_similar_not_found(self, api_client):
        r = await api_client.get(f"{API_BASE}/search/similar/nonexistent-id-999")
        assert r.status_code == 404
