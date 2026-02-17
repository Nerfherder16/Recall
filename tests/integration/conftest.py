"""
Shared fixtures for Recall integration tests.

All tests hit the live API (default http://localhost:8200).
Each test gets a unique domain for isolation, and cleanup
deletes all created resources after each test.
"""

import asyncio
import os
import uuid
from dataclasses import dataclass, field

import httpx
import pytest

API_BASE = os.environ.get("RECALL_API_URL", "http://localhost:8200")
API_KEY = os.environ.get("RECALL_API_KEY", "")


# =============================================================
# Rate-limit retry helper
# =============================================================


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    max_retries: int = 5,
    **kwargs,
) -> httpx.Response:
    """Execute an HTTP request, retrying on 429 with Retry-After backoff."""
    for attempt in range(max_retries + 1):
        r = await getattr(client, method)(url, **kwargs)
        if r.status_code != 429 or attempt == max_retries:
            return r
        # Wait at least 10s — the 30/minute window needs real time to clear
        retry_after = max(int(r.headers.get("Retry-After", 10)), 10)
        await asyncio.sleep(retry_after)
    return r


# =============================================================
# Cleanup tracker
# =============================================================


@dataclass
class CleanupTracker:
    """Tracks resources created during a test for teardown."""

    client: httpx.AsyncClient
    memory_ids: list[str] = field(default_factory=list)
    session_ids: list[str] = field(default_factory=list)

    def track_memory(self, memory_id: str):
        self.memory_ids.append(memory_id)

    def track_session(self, session_id: str):
        self.session_ids.append(session_id)

    async def teardown(self):
        """Delete all tracked resources. Errors are suppressed."""
        for sid in self.session_ids:
            try:
                await self.client.post(
                    f"{API_BASE}/session/end",
                    json={"session_id": sid, "trigger_consolidation": False},
                )
            except Exception:
                pass

        for mid in self.memory_ids:
            try:
                await self.client.delete(f"{API_BASE}/memory/{mid}")
            except Exception:
                pass


# =============================================================
# Markers
# =============================================================


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")


# =============================================================
# Health gate (session-scoped, synchronous to avoid loop issues)
# =============================================================


def _auth_headers() -> dict[str, str]:
    """Return auth headers if API key is configured."""
    if API_KEY:
        return {"Authorization": f"Bearer {API_KEY}"}
    return {}


@pytest.fixture(scope="session", autouse=True)
def ensure_healthy():
    """Skip all tests if the API is not reachable or unhealthy."""
    try:
        r = httpx.get(f"{API_BASE}/health", timeout=10.0)
        data = r.json()
        if data.get("status") not in ("healthy", "degraded"):
            pytest.skip("API not healthy — skipping integration tests")
    except Exception as exc:
        pytest.skip(f"API unreachable ({exc}) — skipping integration tests")


# =============================================================
# Function-scoped: per-test client and isolation
# =============================================================


@pytest.fixture
async def api_client():
    """Function-scoped httpx async client — avoids event loop lifetime issues."""
    async with httpx.AsyncClient(timeout=60.0, headers=_auth_headers()) as client:
        yield client


@pytest.fixture
def test_domain():
    """Return a unique domain string for test isolation."""
    return f"test-integration-{uuid.uuid4().hex[:12]}"


@pytest.fixture
async def cleanup(api_client):
    """Provide a CleanupTracker that tears down after the test."""
    tracker = CleanupTracker(client=api_client)
    yield tracker
    await tracker.teardown()


# =============================================================
# Factory fixtures
# =============================================================


@pytest.fixture
def stored_memory(api_client, test_domain, cleanup):
    """
    Factory fixture: store a memory and auto-register it for cleanup.

    Usage:
        mem = await stored_memory("some content", memory_type="semantic")
    """

    async def _store(
        content: str,
        *,
        memory_type: str = "semantic",
        source: str = "user",
        domain: str | None = None,
        tags: list[str] | None = None,
        importance: float = 0.5,
        confidence: float = 0.8,
        session_id: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        payload = {
            "content": content,
            "memory_type": memory_type,
            "source": source,
            "domain": domain or test_domain,
            "tags": tags or [],
            "importance": importance,
            "confidence": confidence,
            "metadata": metadata or {},
        }
        if session_id:
            payload["session_id"] = session_id

        r = await api_client.post(f"{API_BASE}/memory/store", json=payload)
        assert r.status_code == 200, f"Store failed: {r.text}"
        data = r.json()
        cleanup.track_memory(data["id"])
        return data

    return _store


@pytest.fixture
def active_session(api_client, cleanup):
    """
    Factory fixture: start a session and auto-register it for cleanup.

    Usage:
        session = await active_session()
    """

    async def _start(
        session_id: str | None = None,
        working_directory: str | None = None,
        current_task: str | None = None,
    ) -> dict:
        payload: dict = {}
        if session_id:
            payload["session_id"] = session_id
        if working_directory:
            payload["working_directory"] = working_directory
        if current_task:
            payload["current_task"] = current_task

        r = await api_client.post(f"{API_BASE}/session/start", json=payload)
        assert r.status_code == 200, f"Session start failed: {r.text}"
        data = r.json()
        cleanup.track_session(data["session_id"])
        return data

    return _start
