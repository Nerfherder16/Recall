"""
Tests for context assembly: POST /search/context.
"""

import asyncio

import pytest

from tests.integration.conftest import API_BASE

EMBED_DELAY = 0.5


class TestContextAssembly:
    """POST /search/context"""

    async def test_context_returns_markdown(self, stored_memory, api_client, test_domain):
        """Context response should be formatted markdown with sections."""
        await stored_memory(
            "Redis is used for caching to reduce database load",
            memory_type="semantic",
            domain=test_domain,
        )
        await stored_memory(
            "Deployed Redis cluster using Helm chart v6.3",
            memory_type="episodic",
            domain=test_domain,
        )
        await asyncio.sleep(EMBED_DELAY)

        r = await api_client.post(
            f"{API_BASE}/search/context",
            json={"query": "Redis caching", "max_tokens": 2000},
        )
        assert r.status_code == 200
        data = r.json()

        assert "context" in data
        assert isinstance(data["context"], str)
        assert data["memories_used"] > 0
        # Context should contain markdown headers when it has content
        if data["memories_used"] > 0:
            assert "##" in data["context"]

    async def test_breakdown_structure(self, stored_memory, api_client, test_domain):
        """Breakdown should contain expected keys."""
        await stored_memory("fact about testing frameworks", memory_type="semantic", domain=test_domain)
        await stored_memory("workflow: run pytest then deploy", memory_type="procedural", domain=test_domain)
        await asyncio.sleep(EMBED_DELAY)

        r = await api_client.post(
            f"{API_BASE}/search/context",
            json={"query": "testing frameworks", "max_tokens": 2000},
        )
        data = r.json()
        breakdown = data["breakdown"]

        assert "working_memory" in breakdown
        assert "semantic" in breakdown
        assert "episodic" in breakdown
        assert "procedural" in breakdown

        # At least one type should have memories
        assert sum(breakdown.values()) >= 1

    async def test_token_limit_truncation(self, stored_memory, api_client, test_domain):
        """Very low max_tokens should truncate the output."""
        # Store enough content to potentially exceed the token limit
        for i in range(5):
            await stored_memory(
                f"This is a moderately long memory entry number {i} about software architecture "
                f"patterns including microservices, event sourcing, and CQRS for domain {test_domain}",
                domain=test_domain,
            )
        await asyncio.sleep(EMBED_DELAY)

        r = await api_client.post(
            f"{API_BASE}/search/context",
            json={"query": "software architecture", "max_tokens": 50},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["estimated_tokens"] <= 50

    async def test_working_memory_inclusion(
        self, active_session, stored_memory, api_client, test_domain
    ):
        """With a session_id and include_working_memory=True, working memory appears in context."""
        session = await active_session()
        sid = session["session_id"]

        await stored_memory(
            "working memory: current debug target is auth module",
            session_id=sid,
            domain=test_domain,
        )
        await asyncio.sleep(EMBED_DELAY)

        r = await api_client.post(
            f"{API_BASE}/search/context",
            json={
                "query": "auth module debug",
                "session_id": sid,
                "include_working_memory": True,
                "max_tokens": 2000,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["breakdown"]["working_memory"] >= 1

    async def test_working_memory_exclusion(
        self, active_session, stored_memory, api_client, test_domain
    ):
        """With include_working_memory=False, working memory count should be 0."""
        session = await active_session()
        sid = session["session_id"]

        await stored_memory(
            "excluded working memory item",
            session_id=sid,
            domain=test_domain,
        )
        await asyncio.sleep(EMBED_DELAY)

        r = await api_client.post(
            f"{API_BASE}/search/context",
            json={
                "query": "excluded working memory",
                "session_id": sid,
                "include_working_memory": False,
                "max_tokens": 2000,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["breakdown"]["working_memory"] == 0

    async def test_empty_query_returns_200(self, api_client):
        """A context request with no query/session should return 200 with empty context."""
        r = await api_client.post(
            f"{API_BASE}/search/context",
            json={"max_tokens": 2000},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["memories_used"] == 0
        assert data["context"] == ""

    async def test_estimated_tokens(self, stored_memory, api_client, test_domain):
        """estimated_tokens should be a non-negative integer."""
        await stored_memory("token estimation check", domain=test_domain)
        await asyncio.sleep(EMBED_DELAY)

        r = await api_client.post(
            f"{API_BASE}/search/context",
            json={"query": "token estimation", "max_tokens": 2000},
        )
        data = r.json()
        assert isinstance(data["estimated_tokens"], int)
        assert data["estimated_tokens"] >= 0
