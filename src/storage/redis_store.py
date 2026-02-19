"""
Redis storage for working memory and event bus.

Redis handles:
- Session working memory (fast, volatile)
- Event publishing for background workers
- Caching for hot memories
"""

import json
from datetime import timedelta
from typing import Any

import redis.asyncio as redis
import structlog

from src.core import Memory, Session, get_settings

logger = structlog.get_logger()


class RedisStore:
    """Redis storage for session state and events."""

    def __init__(self):
        self.settings = get_settings()
        self.client: redis.Redis | None = None

    async def connect(self):
        """Initialize Redis connection."""
        self.client = redis.from_url(
            self.settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        await self.client.ping()
        logger.info("connected_to_redis")

    # =============================================================
    # SESSION MANAGEMENT
    # =============================================================

    def _session_key(self, session_id: str) -> str:
        return f"recall:session:{session_id}"

    def _working_memory_key(self, session_id: str) -> str:
        return f"recall:session:{session_id}:working"

    async def create_session(self, session: Session) -> str:
        """Create a new session."""
        key = self._session_key(session.id)
        await self.client.hset(
            key,
            mapping={
                "id": session.id,
                "started_at": session.started_at.isoformat(),
                "working_directory": session.working_directory or "",
                "current_task": session.current_task or "",
                "memories_created": str(session.memories_created),
                "memories_retrieved": str(session.memories_retrieved),
                "signals_detected": "0",
            },
        )
        await self.client.expire(key, timedelta(hours=self.settings.session_ttl_hours))
        return session.id

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Get session data."""
        key = self._session_key(session_id)
        data = await self.client.hgetall(key)
        return data if data else None

    async def update_session(self, session_id: str, updates: dict[str, Any]):
        """Update session fields."""
        key = self._session_key(session_id)
        string_updates = {k: str(v) for k, v in updates.items()}
        await self.client.hset(key, mapping=string_updates)

    async def end_session(self, session_id: str):
        """Mark session as ended."""
        key = self._session_key(session_id)
        from datetime import datetime

        await self.client.hset(key, "ended_at", datetime.utcnow().isoformat())
        # Keep for a bit for consolidation, then it expires

    # =============================================================
    # WORKING MEMORY
    # =============================================================

    async def add_to_working_memory(self, session_id: str, memory_id: str):
        """Add a memory to session's working memory."""
        key = self._working_memory_key(session_id)
        await self.client.lpush(key, memory_id)
        # Trim to limit
        await self.client.ltrim(key, 0, self.settings.working_memory_limit - 1)
        await self.client.expire(key, timedelta(hours=self.settings.session_ttl_hours))

    async def get_working_memory(self, session_id: str) -> list[str]:
        """Get all memory IDs in working memory."""
        key = self._working_memory_key(session_id)
        return await self.client.lrange(key, 0, -1)

    async def clear_working_memory(self, session_id: str):
        """Clear working memory for a session."""
        key = self._working_memory_key(session_id)
        await self.client.delete(key)

    # =============================================================
    # HOT MEMORY CACHE
    # =============================================================

    def _cache_key(self, memory_id: str) -> str:
        return f"recall:cache:{memory_id}"

    async def cache_memory(self, memory: Memory, ttl_minutes: int = 60):
        """Cache a frequently accessed memory."""
        key = self._cache_key(memory.id)
        await self.client.set(
            key,
            memory.model_dump_json(),
            ex=timedelta(minutes=ttl_minutes),
        )

    async def get_cached_memory(self, memory_id: str) -> Memory | None:
        """Get a memory from cache."""
        key = self._cache_key(memory_id)
        data = await self.client.get(key)
        if data:
            return Memory.model_validate_json(data)
        return None

    async def invalidate_cache(self, memory_id: str):
        """Remove memory from cache."""
        key = self._cache_key(memory_id)
        await self.client.delete(key)

    # =============================================================
    # EVENT BUS (for background workers)
    # =============================================================

    async def publish_event(self, event_type: str, payload: dict[str, Any]):
        """Publish an event for background processing."""
        event = {
            "type": event_type,
            "payload": payload,
        }
        await self.client.xadd(
            "recall:events",
            {"data": json.dumps(event)},
            maxlen=10000,  # Keep last 10k events
        )
        logger.debug("published_event", type=event_type)

    async def get_events(
        self,
        last_id: str = "0",
        count: int = 100,
        block_ms: int = 5000,
    ) -> list[tuple[str, dict[str, Any]]]:
        """
        Get events from the stream.

        Returns list of (event_id, event_data).
        """
        result = await self.client.xread(
            {"recall:events": last_id},
            count=count,
            block=block_ms,
        )

        events = []
        if result:
            for stream_name, messages in result:
                for msg_id, data in messages:
                    event = json.loads(data["data"])
                    events.append((msg_id, event))

        return events

    async def ack_event(self, event_id: str, consumer_group: str = "workers"):
        """Acknowledge an event as processed."""
        # For simple setup, we don't use consumer groups
        # In production, use XACK with consumer groups
        pass

    # =============================================================
    # TURN STORAGE (for signal detection)
    # =============================================================

    def _turns_key(self, session_id: str) -> str:
        return f"recall:session:{session_id}:turns"

    async def add_turns(self, session_id: str, turns: list[dict]) -> int:
        """
        Append conversation turns to a session.

        Stores as JSON strings in a Redis list (newest at head).
        Trims to signal_max_turns_stored.
        Returns total turn count after insert.
        """
        key = self._turns_key(session_id)
        pipe = self.client.pipeline()
        for turn in turns:  # LPUSH puts each at head; last turn ends up leftmost
            pipe.lpush(key, json.dumps(turn))
        pipe.ltrim(key, 0, self.settings.signal_max_turns_stored - 1)
        pipe.expire(key, timedelta(hours=self.settings.session_ttl_hours))
        pipe.llen(key)
        results = await pipe.execute()
        return results[-1]  # llen result

    async def get_recent_turns(self, session_id: str, count: int | None = None) -> list[dict]:
        """
        Get recent turns in chronological order (oldest first).

        Args:
            session_id: Session to fetch turns from
            count: Number of turns to return (default: signal_context_window)
        """
        count = count or self.settings.signal_context_window
        key = self._turns_key(session_id)
        raw = await self.client.lrange(key, 0, count - 1)
        # LPUSH stores newest first, so reverse for chronological
        return [json.loads(item) for item in reversed(raw)]

    async def get_turn_count(self, session_id: str) -> int:
        """Get the number of turns in a session (O(1) via LLEN)."""
        key = self._turns_key(session_id)
        return await self.client.llen(key)

    # =============================================================
    # PENDING SIGNALS
    # =============================================================

    def _pending_key(self, session_id: str) -> str:
        return f"recall:signals:pending:{session_id}"

    async def add_pending_signal(self, session_id: str, signal: dict):
        """Add a medium-confidence signal to the pending review queue."""
        key = self._pending_key(session_id)
        await self.client.lpush(key, json.dumps(signal))
        await self.client.ltrim(key, 0, 99)  # Cap at 100 pending signals
        await self.client.expire(key, timedelta(hours=self.settings.session_ttl_hours))

    async def get_pending_signals(self, session_id: str) -> list[dict]:
        """Get all pending signals for a session."""
        key = self._pending_key(session_id)
        raw = await self.client.lrange(key, 0, -1)
        return [json.loads(item) for item in raw]

    async def remove_pending_signal(self, session_id: str, index: int) -> dict | None:
        """Remove a specific pending signal by index. Returns the signal or None."""
        key = self._pending_key(session_id)
        raw = await self.client.lrange(key, 0, -1)
        if index < 0 or index >= len(raw):
            return None
        signal = json.loads(raw[index])
        # Remove by value (set to sentinel, then remove sentinel)
        sentinel = "__REMOVED__"
        await self.client.lset(key, index, sentinel)
        await self.client.lrem(key, 1, sentinel)
        return signal

    async def clear_pending_signals(self, session_id: str):
        """Delete all pending signals for a session."""
        key = self._pending_key(session_id)
        await self.client.delete(key)

    # =============================================================
    # STATISTICS
    # =============================================================

    async def get_active_sessions(self) -> int:
        """Count active sessions using SCAN (non-blocking, unlike KEYS)."""
        count = 0
        cursor = 0
        while True:
            cursor, keys = await self.client.scan(
                cursor=cursor, match="recall:session:*", count=100
            )
            # Filter out sub-keys (working, turns)
            count += sum(1 for k in keys if ":working" not in k and ":turns" not in k)
            if cursor == 0:
                break
        return count

    async def close(self):
        """Close the connection."""
        if self.client:
            await self.client.close()


# Singleton
_store: RedisStore | None = None


async def get_redis_store() -> RedisStore:
    """Get or create Redis store singleton."""
    global _store
    if _store is None:
        _store = RedisStore()
        await _store.connect()
    return _store
