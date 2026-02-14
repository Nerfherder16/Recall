"""
Tests for memory relationships: POST /memory/relationship, GET /memory/{id}/related.
"""

import asyncio

import pytest

from tests.integration.conftest import API_BASE

ALL_RELATIONSHIP_TYPES = [
    "related_to",
    "caused_by",
    "solved_by",
    "supersedes",
    "derived_from",
    "contradicts",
    "requires",
    "part_of",
]


class TestCreateRelationship:
    """POST /memory/relationship"""

    async def test_create_basic_relationship(self, stored_memory, api_client):
        src = await stored_memory("the bug: null pointer in parser")
        tgt = await stored_memory("the fix: added null check in parser.py:42")

        r = await api_client.post(
            f"{API_BASE}/memory/relationship",
            json={
                "source_id": src["id"],
                "target_id": tgt["id"],
                "relationship_type": "solved_by",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["created"] is True
        assert data["relationship_id"]

    @pytest.mark.parametrize("rel_type", ALL_RELATIONSHIP_TYPES)
    async def test_all_relationship_types(self, stored_memory, api_client, rel_type):
        src = await stored_memory(f"source for {rel_type}")
        tgt = await stored_memory(f"target for {rel_type}")

        r = await api_client.post(
            f"{API_BASE}/memory/relationship",
            json={
                "source_id": src["id"],
                "target_id": tgt["id"],
                "relationship_type": rel_type,
            },
        )
        assert r.status_code == 200
        assert r.json()["created"] is True

    async def test_bidirectional_relationship(self, stored_memory, api_client):
        a = await stored_memory("concept A for bidirectional test")
        b = await stored_memory("concept B for bidirectional test")

        r = await api_client.post(
            f"{API_BASE}/memory/relationship",
            json={
                "source_id": a["id"],
                "target_id": b["id"],
                "relationship_type": "related_to",
                "bidirectional": True,
            },
        )
        assert r.status_code == 200
        assert r.json()["created"] is True


class TestGetRelated:
    """GET /memory/{memory_id}/related"""

    async def test_graph_traversal_depth_1(self, stored_memory, api_client):
        a = await stored_memory("root node for depth-1 test")
        b = await stored_memory("child node for depth-1 test")

        await api_client.post(
            f"{API_BASE}/memory/relationship",
            json={
                "source_id": a["id"],
                "target_id": b["id"],
                "relationship_type": "related_to",
            },
        )

        r = await api_client.get(
            f"{API_BASE}/memory/{a['id']}/related",
            params={"max_depth": 1, "limit": 10},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["source_id"] == a["id"]
        related_ids = [rel["id"] if isinstance(rel, dict) else rel for rel in data["related"]]
        assert b["id"] in related_ids

    async def test_graph_traversal_depth_2(self, stored_memory, api_client):
        """A → B → C should be reachable at depth 2."""
        a = await stored_memory("chain root")
        b = await stored_memory("chain middle")
        c = await stored_memory("chain leaf")

        await api_client.post(
            f"{API_BASE}/memory/relationship",
            json={
                "source_id": a["id"],
                "target_id": b["id"],
                "relationship_type": "requires",
            },
        )
        await api_client.post(
            f"{API_BASE}/memory/relationship",
            json={
                "source_id": b["id"],
                "target_id": c["id"],
                "relationship_type": "requires",
            },
        )

        r = await api_client.get(
            f"{API_BASE}/memory/{a['id']}/related",
            params={"max_depth": 2, "limit": 10},
        )
        assert r.status_code == 200
        related_ids = [
            rel["id"] if isinstance(rel, dict) else rel
            for rel in r.json()["related"]
        ]
        assert b["id"] in related_ids
        assert c["id"] in related_ids

    async def test_depth_limiting(self, stored_memory, api_client):
        """A → B → C: at depth 1, C should NOT appear."""
        a = await stored_memory("depth-limit root")
        b = await stored_memory("depth-limit mid")
        c = await stored_memory("depth-limit far")

        await api_client.post(
            f"{API_BASE}/memory/relationship",
            json={
                "source_id": a["id"],
                "target_id": b["id"],
                "relationship_type": "part_of",
            },
        )
        await api_client.post(
            f"{API_BASE}/memory/relationship",
            json={
                "source_id": b["id"],
                "target_id": c["id"],
                "relationship_type": "part_of",
            },
        )

        r = await api_client.get(
            f"{API_BASE}/memory/{a['id']}/related",
            params={"max_depth": 1, "limit": 10},
        )
        related_ids = [
            rel["id"] if isinstance(rel, dict) else rel
            for rel in r.json()["related"]
        ]
        assert b["id"] in related_ids
        assert c["id"] not in related_ids

    async def test_isolated_node_returns_empty(self, stored_memory, api_client):
        """A node with no relationships returns an empty list."""
        loner = await stored_memory("isolated node with no friends")

        r = await api_client.get(
            f"{API_BASE}/memory/{loner['id']}/related",
            params={"max_depth": 2, "limit": 10},
        )
        assert r.status_code == 200
        assert r.json()["related"] == []
