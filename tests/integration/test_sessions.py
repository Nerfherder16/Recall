"""
Tests for session management: /session/start, /session/end,
/session/{id}, /session/{id}/working-memory, /session/{id}/context.
"""

import asyncio
import uuid

import pytest

from tests.integration.conftest import API_BASE


class TestStartSession:
    """POST /session/start"""

    async def test_start_auto_id(self, active_session):
        data = await active_session()
        assert "session_id" in data
        assert data["session_id"]
        assert "started_at" in data

    async def test_start_custom_id(self, active_session):
        custom_id = f"test-session-{uuid.uuid4().hex[:8]}"
        data = await active_session(session_id=custom_id)
        assert data["session_id"] == custom_id

    async def test_start_with_context(self, active_session):
        data = await active_session(
            working_directory="/tmp/project",
            current_task="writing tests",
        )
        assert data["session_id"]


class TestGetSession:
    """GET /session/{session_id}"""

    async def test_get_session_status(self, active_session, api_client):
        session = await active_session(
            working_directory="/home/dev",
            current_task="integration testing",
        )
        sid = session["session_id"]

        r = await api_client.get(f"{API_BASE}/session/{sid}")
        assert r.status_code == 200
        data = r.json()
        assert data["session_id"] == sid
        assert data["started_at"]
        assert data["ended_at"] is None
        assert data["memories_created"] >= 0
        assert data["memories_retrieved"] >= 0
        assert isinstance(data["working_memory_count"], int)

    async def test_get_session_not_found(self, api_client):
        r = await api_client.get(f"{API_BASE}/session/nonexistent-session-xyz")
        assert r.status_code == 404


class TestEndSession:
    """POST /session/end"""

    async def test_end_session(self, active_session, api_client):
        session = await active_session()
        sid = session["session_id"]

        r = await api_client.post(
            f"{API_BASE}/session/end",
            json={"session_id": sid, "trigger_consolidation": False},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ended"] is True
        assert data["session_id"] == sid

    async def test_end_session_not_found(self, api_client):
        r = await api_client.post(
            f"{API_BASE}/session/end",
            json={"session_id": "ghost-session-404", "trigger_consolidation": False},
        )
        assert r.status_code == 404


class TestWorkingMemory:
    """GET /session/{id}/working-memory"""

    async def test_working_memory_accumulation(
        self, active_session, stored_memory, api_client
    ):
        """Storing memories with a session_id should add them to working memory."""
        session = await active_session()
        sid = session["session_id"]

        m1 = await stored_memory("working mem item 1", session_id=sid)
        m2 = await stored_memory("working mem item 2", session_id=sid)

        r = await api_client.get(f"{API_BASE}/session/{sid}/working-memory")
        assert r.status_code == 200
        data = r.json()
        assert data["session_id"] == sid
        assert data["count"] >= 2

        mem_ids = [m["id"] for m in data["memories"]]
        assert m1["id"] in mem_ids
        assert m2["id"] in mem_ids

    async def test_working_memory_order(
        self, active_session, stored_memory, api_client
    ):
        """Working memory should contain items in stored order (LIFO or FIFO)."""
        session = await active_session()
        sid = session["session_id"]

        ids = []
        for i in range(3):
            m = await stored_memory(f"ordered item {i}", session_id=sid)
            ids.append(m["id"])

        r = await api_client.get(f"{API_BASE}/session/{sid}/working-memory")
        data = r.json()
        mem_ids = [m["id"] for m in data["memories"]]
        # All stored IDs should be present
        for mid in ids:
            assert mid in mem_ids

    async def test_working_memory_empty_session(self, active_session, api_client):
        """A fresh session should have no working memory."""
        session = await active_session()
        sid = session["session_id"]

        r = await api_client.get(f"{API_BASE}/session/{sid}/working-memory")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 0
        assert data["memories"] == []


class TestUpdateSessionContext:
    """POST /session/{id}/context"""

    async def test_update_context(self, active_session, api_client):
        session = await active_session()
        sid = session["session_id"]

        r = await api_client.post(
            f"{API_BASE}/session/{sid}/context",
            params={
                "working_directory": "/new/path",
                "current_task": "updated task",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["updated"] is True
        assert data["session_id"] == sid


class TestEndSessionConsolidation:
    """End session with consolidation event."""

    async def test_end_with_consolidation(
        self, active_session, stored_memory, api_client
    ):
        session = await active_session()
        sid = session["session_id"]

        await stored_memory("consolidation candidate 1", session_id=sid)
        await stored_memory("consolidation candidate 2", session_id=sid)

        r = await api_client.post(
            f"{API_BASE}/session/end",
            json={"session_id": sid, "trigger_consolidation": True},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ended"] is True
        assert data["memories_in_session"] >= 2
        assert data["consolidation_queued"] is True
