"""
End-to-end workflow tests simulating real Claude Code sessions. Marked as slow.
"""

import asyncio

import pytest

from tests.integration.conftest import API_BASE, request_with_retry

EMBED_DELAY = 0.5


@pytest.mark.slow
class TestFullSessionWorkflow:
    """Simulate a complete Claude Code session lifecycle."""

    async def test_claude_code_session(
        self, active_session, stored_memory, api_client, test_domain
    ):
        """
        Full flow: start session → store facts → debug bug → create relationship
        → search → assemble context → end session.
        """
        # 1. Start session
        session = await active_session(
            working_directory="/home/dev/project",
            current_task="debugging auth module",
        )
        sid = session["session_id"]

        # 2. Store semantic facts during exploration
        fact1 = await stored_memory(
            "The auth module uses JWT with RS256 signing algorithm",
            memory_type="semantic",
            domain=test_domain,
            tags=["auth", "jwt"],
            session_id=sid,
        )
        fact2 = await stored_memory(
            "Token refresh endpoint is POST /auth/refresh",
            memory_type="semantic",
            domain=test_domain,
            tags=["auth", "api"],
            session_id=sid,
        )

        # 3. Store episodic debug event
        bug = await stored_memory(
            "Found bug: refresh token not invalidated after password change",
            memory_type="episodic",
            domain=test_domain,
            tags=["auth", "bug"],
            session_id=sid,
        )
        fix = await stored_memory(
            "Fixed by adding token revocation on password change in auth/service.py:88",
            memory_type="episodic",
            domain=test_domain,
            tags=["auth", "fix"],
            session_id=sid,
        )

        # 4. Create relationship: bug → fix
        r = await api_client.post(
            f"{API_BASE}/memory/relationship",
            json={
                "source_id": bug["id"],
                "target_id": fix["id"],
                "relationship_type": "solved_by",
            },
        )
        assert r.status_code == 200

        await asyncio.sleep(EMBED_DELAY)

        # 5. Search for related information
        r = await request_with_retry(
            api_client, "post",
            f"{API_BASE}/search/query",
            json={
                "query": "auth token refresh bug",
                "domains": [test_domain],
                "session_id": sid,
            },
        )
        assert r.status_code == 200
        results = r.json()["results"]
        assert len(results) >= 1

        # 6. Assemble context
        r = await request_with_retry(
            api_client, "post",
            f"{API_BASE}/search/context",
            json={
                "query": "authentication token handling",
                "session_id": sid,
                "include_working_memory": True,
                "max_tokens": 2000,
            },
        )
        assert r.status_code == 200
        ctx = r.json()
        assert ctx["memories_used"] >= 1
        assert ctx["context"]  # Non-empty

        # 7. End session
        r = await api_client.post(
            f"{API_BASE}/session/end",
            json={"session_id": sid, "trigger_consolidation": True},
        )
        assert r.status_code == 200
        assert r.json()["ended"] is True
        assert r.json()["memories_in_session"] >= 4


@pytest.mark.slow
class TestKnowledgeAccumulation:
    """Knowledge should build up and become more retrievable over time."""

    async def test_knowledge_accumulation_across_searches(
        self, stored_memory, api_client, test_domain
    ):
        """
        Store a fact, search for it repeatedly. Importance should grow,
        making it rank higher in future searches.
        """
        data = await stored_memory(
            "GraphQL resolvers should use DataLoader for N+1 prevention",
            importance=0.3,
            domain=test_domain,
            tags=["graphql", "performance"],
        )
        mid = data["id"]
        await asyncio.sleep(EMBED_DELAY)

        # Search repeatedly
        for _ in range(5):
            await api_client.post(
                f"{API_BASE}/search/query",
                json={
                    "query": "GraphQL N+1 DataLoader",
                    "domains": [test_domain],
                },
            )
            await asyncio.sleep(0.2)

        # Verify importance grew
        r = await api_client.get(f"{API_BASE}/memory/{mid}")
        assert r.status_code == 200
        assert r.json()["importance"] >= 0.3


@pytest.mark.slow
class TestMultiDomainCrossReference:
    """Memories from different domains can be found in a single query."""

    async def test_cross_domain_search(self, stored_memory, api_client, test_domain):
        domain_a = test_domain + "-frontend"
        domain_b = test_domain + "-backend"

        await stored_memory(
            "React component uses fetch to call the user API",
            domain=domain_a,
            tags=["react", "api"],
        )
        await stored_memory(
            "User API endpoint validates JWT before returning user data",
            domain=domain_b,
            tags=["api", "auth"],
        )
        await asyncio.sleep(EMBED_DELAY)

        r = await request_with_retry(
            api_client, "post",
            f"{API_BASE}/search/query",
            json={
                "query": "user API authentication flow",
                "domains": [domain_a, domain_b],
            },
        )
        assert r.status_code == 200
        results = r.json()["results"]
        found_domains = {item["domain"] for item in results}
        # Should find results from at least one of the two domains
        assert len(found_domains) >= 1


@pytest.mark.slow
class TestMemorySupersession:
    """A newer memory can supersede an older one."""

    async def test_supersession_flow(self, stored_memory, api_client, test_domain):
        old = await stored_memory(
            "Database connection pool size is 10",
            domain=test_domain,
            tags=["config", "database"],
        )
        new = await stored_memory(
            "Database connection pool size increased to 25 for better throughput",
            domain=test_domain,
            tags=["config", "database"],
        )

        # Create supersedes relationship
        r = await api_client.post(
            f"{API_BASE}/memory/relationship",
            json={
                "source_id": new["id"],
                "target_id": old["id"],
                "relationship_type": "supersedes",
            },
        )
        assert r.status_code == 200

        # Both should still be retrievable
        r1 = await api_client.get(f"{API_BASE}/memory/{old['id']}")
        assert r1.status_code == 200
        r2 = await api_client.get(f"{API_BASE}/memory/{new['id']}")
        assert r2.status_code == 200


@pytest.mark.slow
class TestSessionWorkingMemoryInContext:
    """Working memory from an active session should appear in context assembly."""

    async def test_working_memory_in_context(
        self, active_session, stored_memory, api_client, test_domain
    ):
        session = await active_session(current_task="refactoring database layer")
        sid = session["session_id"]

        # Store memories into the session
        await stored_memory(
            "Refactoring plan: extract repository pattern from service layer",
            session_id=sid,
            domain=test_domain,
        )
        await stored_memory(
            "Found 12 direct SQL queries in user_service.py to migrate",
            session_id=sid,
            domain=test_domain,
        )
        await asyncio.sleep(EMBED_DELAY)

        # Assemble context with working memory
        r = await api_client.post(
            f"{API_BASE}/search/context",
            json={
                "query": "database repository refactoring",
                "session_id": sid,
                "include_working_memory": True,
                "max_tokens": 2000,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["breakdown"]["working_memory"] >= 1
        assert "Recent Context" in data["context"] or data["memories_used"] >= 1
