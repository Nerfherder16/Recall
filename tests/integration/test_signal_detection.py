"""
Integration tests for Phase 2 — Signal Detection Brain.

Tests cover:
- Turn ingestion and storage
- Signal detection pipeline (full round-trip with LLM)
- Pending signal queue and approval
- Deduplication

Note: Slow tests need generous sleeps because Ollama serves one request
at a time — the background LLM generate must finish before the test's
search call (which also needs Ollama for embedding) can proceed.
"""

import asyncio
import uuid

import httpx
import pytest

from .conftest import API_BASE, _auth_headers

# Ollama is single-threaded: LLM generate must finish before embedding calls work.
# These sleeps account for model cold start (~10s) + generation (~15-30s).
LLM_WAIT_SHORT = 35


async def poll_for_signal_memories(
    client: httpx.AsyncClient,
    query: str,
    *,
    max_wait: int = 120,
    interval: int = 10,
) -> list[dict]:
    """Poll search endpoint until signal-tagged memories appear or timeout."""
    elapsed = 0
    while elapsed < max_wait:
        await asyncio.sleep(interval)
        elapsed += interval
        try:
            r = await client.post(
                f"{API_BASE}/search/query",
                json={"query": query, "limit": 10},
            )
            if r.status_code == 200:
                results = r.json().get("results", [])
                signals = [
                    m for m in results
                    if any("signal:" in t for t in m.get("tags", []))
                ]
                if signals:
                    return signals
        except httpx.ReadTimeout:
            # Ollama still busy, keep waiting
            continue
    return []


# =============================================================
# Turn ingestion
# =============================================================


@pytest.mark.anyio
async def test_ingest_turns(api_client: httpx.AsyncClient, active_session, cleanup):
    """Ingesting turns stores them and queues signal detection."""
    session = await active_session()
    sid = session["session_id"]

    r = await api_client.post(
        f"{API_BASE}/ingest/turns",
        json={
            "session_id": sid,
            "turns": [
                {"role": "user", "content": "How do I fix a Docker permission error?"},
                {"role": "assistant", "content": "Run: sudo chmod 666 /var/run/docker.sock"},
            ],
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["turns_ingested"] == 2
    assert data["total_turns"] == 2
    assert data["detection_queued"] is True


@pytest.mark.anyio
async def test_ingest_requires_valid_session(api_client: httpx.AsyncClient):
    """Ingesting turns for a non-existent session returns 404."""
    r = await api_client.post(
        f"{API_BASE}/ingest/turns",
        json={
            "session_id": str(uuid.uuid4()),
            "turns": [{"role": "user", "content": "test"}],
        },
    )
    assert r.status_code == 404


@pytest.mark.anyio
async def test_ingest_requires_turns(api_client: httpx.AsyncClient, active_session, cleanup):
    """Ingesting with empty turns list is rejected (validation)."""
    session = await active_session()
    sid = session["session_id"]

    r = await api_client.post(
        f"{API_BASE}/ingest/turns",
        json={"session_id": sid, "turns": []},
    )
    assert r.status_code == 422


# =============================================================
# Turn retrieval
# =============================================================


@pytest.mark.anyio
async def test_get_turns(api_client: httpx.AsyncClient, active_session, cleanup):
    """Stored turns are retrievable in chronological order."""
    session = await active_session()
    sid = session["session_id"]

    turns = [
        {"role": "user", "content": "First message"},
        {"role": "assistant", "content": "Second message"},
        {"role": "user", "content": "Third message"},
    ]

    await api_client.post(
        f"{API_BASE}/ingest/turns",
        json={"session_id": sid, "turns": turns},
    )

    r = await api_client.get(f"{API_BASE}/ingest/{sid}/turns?count=10")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 3

    # Verify chronological order
    assert data["turns"][0]["content"] == "First message"
    assert data["turns"][1]["content"] == "Second message"
    assert data["turns"][2]["content"] == "Third message"


@pytest.mark.anyio
async def test_get_turns_invalid_session(api_client: httpx.AsyncClient):
    """Getting turns for non-existent session returns 404."""
    r = await api_client.get(f"{API_BASE}/ingest/{uuid.uuid4()}/turns")
    assert r.status_code == 404


# =============================================================
# Signal detection (full pipeline — requires Ollama)
# =============================================================


@pytest.mark.anyio
@pytest.mark.slow
async def test_signal_detection_produces_memories(
    active_session, cleanup, test_domain
):
    """
    Full pipeline: ingest a clear error_fix turn → wait for detection →
    verify a memory was auto-stored.

    This test is slow because it calls Ollama LLM.
    Uses its own client with a longer timeout since the search call
    needs Ollama for embedding after the LLM generate finishes.
    """
    async with httpx.AsyncClient(timeout=60.0, headers=_auth_headers()) as client:
        session = await active_session()
        sid = session["session_id"]

        # Ingest a conversation with a very clear error fix signal
        turns = [
            {
                "role": "user",
                "content": "I keep getting 'EACCES permission denied' when running npm install globally on Linux.",
            },
            {
                "role": "assistant",
                "content": (
                    "This is a common npm permissions issue. The fix is to change npm's "
                    "default directory. Run: mkdir ~/.npm-global && "
                    "npm config set prefix '~/.npm-global' && "
                    "echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.bashrc && source ~/.bashrc. "
                    "This avoids needing sudo for global installs."
                ),
            },
        ]

        r = await client.post(
            f"{API_BASE}/ingest/turns",
            json={"session_id": sid, "turns": turns},
        )
        assert r.status_code == 200

        # Poll until signal memories appear (handles model cold start)
        signal_memories = await poll_for_signal_memories(
            client,
            "npm EACCES permission denied global install fix",
            max_wait=120,
        )

        # Clean up any created memories
        for m in signal_memories:
            cleanup.track_memory(m["id"])

        assert len(signal_memories) > 0, (
            "Expected at least one auto-stored signal memory after 120s polling"
        )


@pytest.mark.anyio
@pytest.mark.slow
async def test_pending_signals(active_session, cleanup):
    """
    Ingest a mildly interesting conversation → check pending signals queue.

    Note: Whether signals land in pending vs auto-store depends on LLM confidence.
    This test verifies the pending endpoint works.
    """
    async with httpx.AsyncClient(timeout=60.0, headers=_auth_headers()) as client:
        session = await active_session()
        sid = session["session_id"]

        # A less clear-cut conversation that might produce lower-confidence signals
        turns = [
            {"role": "user", "content": "I think I'll use PostgreSQL for the new project."},
            {"role": "assistant", "content": "Good choice. PostgreSQL has excellent JSON support."},
        ]

        await client.post(
            f"{API_BASE}/ingest/turns",
            json={"session_id": sid, "turns": turns},
        )

        # Wait for detection
        await asyncio.sleep(LLM_WAIT_SHORT)

        # Check pending signals endpoint (may or may not have signals)
        r = await client.get(f"{API_BASE}/ingest/{sid}/signals")
        assert r.status_code == 200
        # Endpoint works — list structure returned
        assert isinstance(r.json(), list)


@pytest.mark.anyio
@pytest.mark.slow
async def test_approve_pending_signal(active_session, cleanup):
    """
    Ingest a turn, wait for LLM, then check for pending signals and approve.
    """
    async with httpx.AsyncClient(timeout=60.0, headers=_auth_headers()) as client:
        session = await active_session()
        sid = session["session_id"]

        # Ingest some turns first (so the session has turn data)
        await client.post(
            f"{API_BASE}/ingest/turns",
            json={
                "session_id": sid,
                "turns": [{"role": "user", "content": "test turn for approval flow"}],
            },
        )

        # Wait for the background task to run
        await asyncio.sleep(LLM_WAIT_SHORT)

        # Get pending signals
        r = await client.get(f"{API_BASE}/ingest/{sid}/signals")
        assert r.status_code == 200
        pending = r.json()

        if len(pending) > 0:
            # Approve the first one
            r = await client.post(
                f"{API_BASE}/ingest/{sid}/signals/approve",
                json={"index": 0},
            )
            assert r.status_code == 200
            data = r.json()
            assert data["stored"] is True
            assert data["memory_id"] != ""
            cleanup.track_memory(data["memory_id"])


@pytest.mark.anyio
@pytest.mark.slow
async def test_dedup_prevents_duplicate_signals(active_session, cleanup):
    """Ingesting the same conversation twice doesn't create duplicate memories."""
    async with httpx.AsyncClient(timeout=60.0, headers=_auth_headers()) as client:
        session = await active_session()
        sid = session["session_id"]

        turns = [
            {
                "role": "user",
                "content": "The Redis default port is 6379.",
            },
            {
                "role": "assistant",
                "content": "Correct. Redis runs on port 6379 by default. To change it, edit redis.conf.",
            },
        ]

        # Ingest first time and wait for signal to appear
        await client.post(
            f"{API_BASE}/ingest/turns",
            json={"session_id": sid, "turns": turns},
        )
        first_signals = await poll_for_signal_memories(
            client,
            "Redis default port 6379",
            max_wait=120,
        )

        # Ingest second time (same content)
        await client.post(
            f"{API_BASE}/ingest/turns",
            json={"session_id": sid, "turns": turns},
        )
        # Wait for second detection to finish
        await asyncio.sleep(LLM_WAIT_SHORT)

        # Search again for all signal memories
        r = await client.post(
            f"{API_BASE}/search/query",
            json={"query": "Redis default port 6379", "limit": 10},
        )
        assert r.status_code == 200
        results = r.json()["results"]

        signal_memories = [
            m for m in results
            if any("signal:" in t for t in m.get("tags", []))
        ]

        # Clean up
        for m in signal_memories:
            cleanup.track_memory(m["id"])

        # Due to content_hash dedup, we should have at most 1 auto-stored signal
        assert len(signal_memories) <= 1, (
            f"Expected at most 1 signal memory (dedup), got {len(signal_memories)}"
        )
