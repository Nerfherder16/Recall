"""
Phase 9 integration tests — 3-layer search, timeline, sub-embeddings, observer.
"""

import asyncio
import os

import pytest

API_BASE = os.environ.get("RECALL_API_URL", "http://localhost:8200")


# =============================================================
# Pattern 1: 3-Layer Search (browse + timeline)
# =============================================================


class TestBrowseSearch:
    """Test the token-efficient browse endpoint."""

    async def test_browse_returns_summaries(self, api_client, stored_memory, test_domain):
        """Browse should return 120-char summaries, not full content."""
        long_content = "Docker configuration for production deployment. " * 10
        await stored_memory(long_content, domain=test_domain)
        await asyncio.sleep(1)  # Let embedding settle

        r = await api_client.post(
            f"{API_BASE}/search/browse",
            json={"query": "docker configuration", "limit": 5, "domains": [test_domain]},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        # Summary should be truncated to 120 chars max
        for result in data["results"]:
            assert len(result["summary"]) <= 120
            assert "id" in result
            assert "similarity" in result
            assert "memory_type" in result
            assert "tags" in result

    async def test_browse_empty_query(self, api_client):
        """Browse with empty domain filter should work."""
        r = await api_client.post(
            f"{API_BASE}/search/browse",
            json={"query": "something random unique unlikely"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "results" in data
        assert "total" in data


class TestTimeline:
    """Test the chronological timeline endpoint."""

    async def test_timeline_no_anchor(self, api_client, stored_memory, test_domain):
        """Timeline without anchor returns most recent."""
        await stored_memory("first event in timeline", domain=test_domain)
        await stored_memory("second event in timeline", domain=test_domain)
        await asyncio.sleep(0.5)

        r = await api_client.post(
            f"{API_BASE}/search/timeline",
            json={"domain": test_domain, "limit": 10},
        )
        assert r.status_code == 200
        data = r.json()
        assert "entries" in data
        assert data["anchor_id"] is None

    async def test_timeline_with_anchor(self, api_client, stored_memory, test_domain):
        """Timeline with anchor centers around that memory."""
        mem1 = await stored_memory("anchor memory for timeline test", domain=test_domain)
        mem_id = mem1["id"]
        await asyncio.sleep(0.5)

        r = await api_client.post(
            f"{API_BASE}/search/timeline",
            json={"anchor_id": mem_id, "before": 5, "after": 5},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["anchor_id"] == mem_id

    async def test_timeline_invalid_anchor(self, api_client):
        """Timeline with invalid anchor should 404."""
        r = await api_client.post(
            f"{API_BASE}/search/timeline",
            json={"anchor_id": "00000000-0000-0000-0000-000000000000"},
        )
        assert r.status_code == 404


# =============================================================
# Pattern 2: Observer (file change observation)
# =============================================================


class TestObserver:
    """Test the file change observation endpoint."""

    async def test_observe_file_change_queues(self, api_client):
        """File change observation should queue and return immediately."""
        r = await api_client.post(
            f"{API_BASE}/observe/file-change",
            json={
                "file_path": "/test/example.py",
                "content": "def hello(): return 'world'",
                "tool_name": "Write",
            },
        )
        assert r.status_code == 200
        assert r.json()["status"] == "queued"

    async def test_observe_edit_change(self, api_client):
        """Edit observation with old/new strings should queue."""
        r = await api_client.post(
            f"{API_BASE}/observe/file-change",
            json={
                "file_path": "/test/config.py",
                "old_string": "PORT = 8000",
                "new_string": "PORT = 8200",
                "tool_name": "Edit",
            },
        )
        assert r.status_code == 200
        assert r.json()["status"] == "queued"

    async def test_observe_session_snapshot(self, api_client, active_session):
        """Session snapshot should queue."""
        session = await active_session()
        r = await api_client.post(
            f"{API_BASE}/observe/session-snapshot",
            json={"session_id": session["session_id"]},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "queued"


# =============================================================
# Pattern 7: SSE Events
# =============================================================


class TestSSEEvents:
    """Test the SSE events endpoint exists."""

    async def test_events_stream_accessible(self, api_client):
        """Events stream endpoint should be accessible and start streaming."""
        # Use streaming request so we don't hang waiting for the full body
        async with api_client.stream(
            "GET",
            f"{API_BASE}/events/stream",
            headers={"Accept": "text/event-stream"},
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")
            # Read just the first chunk to confirm data is flowing
            async for chunk in response.aiter_bytes():
                assert len(chunk) > 0
                break  # Got data, done


# =============================================================
# Health check includes facts count
# =============================================================


class TestHealthExtended:
    """Test health endpoint works with new collections."""

    async def test_health_still_works(self, api_client):
        """Health check should still work after Phase 9 changes."""
        r = await api_client.get(f"{API_BASE}/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("healthy", "degraded")
        assert "qdrant" in data["checks"]
