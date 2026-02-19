"""
PostgreSQL storage for audit log, session archive, metrics persistence,
and user management.

Uses raw asyncpg (no ORM) — consistent with the rest of the codebase.
All write operations are fire-and-forget: Postgres failures never block
the main operation.
"""

import json
import secrets
from datetime import datetime
from typing import Any

import asyncpg
import structlog

from src.core import get_settings

logger = structlog.get_logger()

# SQL for table creation (run on connect)
_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE,
    api_key         TEXT NOT NULL UNIQUE,
    display_name    TEXT,
    is_admin        BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_active_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_users_api_key ON users(api_key);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGSERIAL PRIMARY KEY,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    action      TEXT NOT NULL,
    memory_id   TEXT NOT NULL,
    actor       TEXT NOT NULL DEFAULT 'system',
    details     JSONB,
    session_id  TEXT,
    user_id     INTEGER
);
CREATE INDEX IF NOT EXISTS idx_audit_log_memory_id ON audit_log(memory_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);

CREATE TABLE IF NOT EXISTS session_archive (
    session_id          TEXT PRIMARY KEY,
    started_at          TIMESTAMPTZ NOT NULL,
    ended_at            TIMESTAMPTZ,
    working_directory   TEXT,
    current_task        TEXT,
    memories_created    INTEGER NOT NULL DEFAULT 0,
    memories_retrieved  INTEGER NOT NULL DEFAULT 0,
    signals_detected    INTEGER NOT NULL DEFAULT 0,
    turns_count         INTEGER NOT NULL DEFAULT 0,
    archived_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_session_archive_started ON session_archive(started_at);

CREATE TABLE IF NOT EXISTS metrics_snapshot (
    id          BIGSERIAL PRIMARY KEY,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    counters    JSONB NOT NULL,
    gauges      JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metrics_snapshot_timestamp ON metrics_snapshot(timestamp);
"""

# Migration: add user_id column to audit_log if it doesn't exist yet
_MIGRATE_AUDIT_USER_ID = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'audit_log' AND column_name = 'user_id'
    ) THEN
        ALTER TABLE audit_log ADD COLUMN user_id INTEGER;
    END IF;
END $$;
"""


def _parse_dsn(dsn: str) -> str:
    """Convert SQLAlchemy-style DSN to raw asyncpg DSN.

    'postgresql+asyncpg://user:pass@host/db' → 'postgresql://user:pass@host/db'
    """
    return dsn.replace("postgresql+asyncpg://", "postgresql://")


class PostgresStore:
    """PostgreSQL storage for audit, sessions, and metrics."""

    def __init__(self):
        self.settings = get_settings()
        self.pool: asyncpg.Pool | None = None

    async def connect(self):
        """Create connection pool and ensure tables exist."""
        dsn = _parse_dsn(self.settings.postgres_dsn)
        self.pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)

        async with self.pool.acquire() as conn:
            await conn.execute(_CREATE_TABLES)
            await conn.execute(_MIGRATE_AUDIT_USER_ID)

        logger.info("connected_to_postgres")

    async def close(self):
        """Close the connection pool."""
        if self.pool:
            await self.pool.close()

    # =============================================================
    # AUDIT LOG
    # =============================================================

    async def log_audit(
        self,
        action: str,
        memory_id: str,
        *,
        actor: str = "system",
        details: dict[str, Any] | None = None,
        session_id: str | None = None,
        user_id: int | None = None,
    ):
        """Append an audit entry. Fire-and-forget — never raises."""
        try:
            await self.pool.execute(
                """
                INSERT INTO audit_log (action, memory_id, actor, details, session_id, user_id)
                VALUES ($1, $2, $3, $4::jsonb, $5, $6)
                """,
                action,
                memory_id,
                actor,
                json.dumps(details) if details else None,
                session_id,
                user_id,
            )
        except Exception as e:
            logger.warning(
                "audit_log_write_failed", error=str(e), action=action, memory_id=memory_id
            )

    async def get_audit_log(
        self,
        memory_id: str | None = None,
        action: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query the audit log with optional filters."""
        conditions = []
        params = []
        idx = 1

        if memory_id:
            conditions.append(f"memory_id = ${idx}")
            params.append(memory_id)
            idx += 1

        if action:
            conditions.append(f"action = ${idx}")
            params.append(action)
            idx += 1

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        params.append(limit)

        rows = await self.pool.fetch(
            f"SELECT * FROM audit_log {where} ORDER BY timestamp DESC LIMIT ${idx}",
            *params,
        )
        return [
            {
                "id": r["id"],
                "timestamp": r["timestamp"].isoformat(),
                "action": r["action"],
                "memory_id": r["memory_id"],
                "actor": r["actor"],
                "details": json.loads(r["details"]) if r["details"] else None,
                "session_id": r["session_id"],
                "user_id": r["user_id"] if "user_id" in r.keys() else None,
            }
            for r in rows
        ]

    # =============================================================
    # USER MANAGEMENT
    # =============================================================

    async def create_user(
        self,
        username: str,
        display_name: str | None = None,
        is_admin: bool = False,
    ) -> dict[str, Any]:
        """Create a new user with a generated API key. Returns full user dict including api_key."""
        api_key = f"rc_{secrets.token_urlsafe(32)}"
        row = await self.pool.fetchrow(
            """
            INSERT INTO users (username, api_key, display_name, is_admin)
            VALUES ($1, $2, $3, $4)
            RETURNING id, username, api_key, display_name, is_admin, created_at, last_active_at
            """,
            username,
            api_key,
            display_name,
            is_admin,
        )
        return {
            "id": row["id"],
            "username": row["username"],
            "api_key": row["api_key"],
            "display_name": row["display_name"],
            "is_admin": row["is_admin"],
            "created_at": row["created_at"].isoformat(),
            "last_active_at": None,
        }

    async def get_user_by_api_key(self, api_key: str) -> dict[str, Any] | None:
        """Look up a user by API key. Returns user dict or None."""
        row = await self.pool.fetchrow(
            """
            SELECT id, username, display_name, is_admin, created_at, last_active_at
            FROM users WHERE api_key = $1
            """,
            api_key,
        )
        if not row:
            return None
        return {
            "id": row["id"],
            "username": row["username"],
            "display_name": row["display_name"],
            "is_admin": row["is_admin"],
            "created_at": row["created_at"].isoformat(),
            "last_active_at": row["last_active_at"].isoformat() if row["last_active_at"] else None,
        }

    async def list_users(self) -> list[dict[str, Any]]:
        """List all users (without API keys)."""
        rows = await self.pool.fetch(
            """
            SELECT id, username, display_name, is_admin, created_at, last_active_at
            FROM users ORDER BY created_at ASC
            """
        )
        return [
            {
                "id": r["id"],
                "username": r["username"],
                "display_name": r["display_name"],
                "is_admin": r["is_admin"],
                "created_at": r["created_at"].isoformat(),
                "last_active_at": r["last_active_at"].isoformat() if r["last_active_at"] else None,
            }
            for r in rows
        ]

    async def delete_user(self, user_id: int) -> bool:
        """Delete a user by ID. Returns True if deleted, False if not found."""
        result = await self.pool.execute("DELETE FROM users WHERE id = $1", user_id)
        return result == "DELETE 1"

    async def update_user_last_active(self, user_id: int):
        """Touch last_active_at. Fire-and-forget — never raises."""
        try:
            await self.pool.execute(
                "UPDATE users SET last_active_at = now() WHERE id = $1",
                user_id,
            )
        except Exception as e:
            logger.warning("user_last_active_update_failed", user_id=user_id, error=str(e))

    # =============================================================
    # SESSION ARCHIVE
    # =============================================================

    async def archive_session(self, session_data: dict[str, Any]):
        """Persist session metadata. Fire-and-forget — never raises."""
        try:
            await self.pool.execute(
                """
                INSERT INTO session_archive
                    (session_id, started_at, ended_at, working_directory, current_task,
                     memories_created, memories_retrieved, signals_detected, turns_count)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (session_id) DO UPDATE SET
                    ended_at = EXCLUDED.ended_at,
                    memories_created = EXCLUDED.memories_created,
                    memories_retrieved = EXCLUDED.memories_retrieved,
                    signals_detected = EXCLUDED.signals_detected,
                    turns_count = EXCLUDED.turns_count,
                    archived_at = now()
                """,
                session_data.get("id") or session_data.get("session_id"),
                datetime.fromisoformat(session_data["started_at"])
                if session_data.get("started_at")
                else datetime.utcnow(),
                datetime.fromisoformat(session_data["ended_at"])
                if session_data.get("ended_at")
                else None,
                session_data.get("working_directory") or None,
                session_data.get("current_task") or None,
                int(session_data.get("memories_created", 0)),
                int(session_data.get("memories_retrieved", 0)),
                int(session_data.get("signals_detected", 0)),
                int(session_data.get("turns_count", 0)),
            )
        except Exception as e:
            logger.warning("session_archive_write_failed", error=str(e))

    async def get_session_history(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get archived sessions, most recent first."""
        rows = await self.pool.fetch(
            """
            SELECT * FROM session_archive
            ORDER BY started_at DESC
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )
        return [
            {
                "session_id": r["session_id"],
                "started_at": r["started_at"].isoformat(),
                "ended_at": r["ended_at"].isoformat() if r["ended_at"] else None,
                "working_directory": r["working_directory"],
                "current_task": r["current_task"],
                "memories_created": r["memories_created"],
                "memories_retrieved": r["memories_retrieved"],
                "signals_detected": r["signals_detected"],
                "turns_count": r["turns_count"],
                "archived_at": r["archived_at"].isoformat(),
            }
            for r in rows
        ]

    # =============================================================
    # METRICS SNAPSHOTS
    # =============================================================

    async def save_metrics_snapshot(self, counters: dict, gauges: dict):
        """Save a point-in-time snapshot of all metrics. Fire-and-forget."""
        try:
            await self.pool.execute(
                """
                INSERT INTO metrics_snapshot (counters, gauges)
                VALUES ($1::jsonb, $2::jsonb)
                """,
                json.dumps(counters),
                json.dumps(gauges),
            )
        except Exception as e:
            logger.warning("metrics_snapshot_write_failed", error=str(e))

    # =============================================================
    # HEALTH DASHBOARD QUERIES
    # =============================================================

    async def get_feedback_stats(self, days: int = 30) -> dict[str, Any]:
        """Get daily feedback stats (useful/not_useful) for the last N days."""
        rows = await self.pool.fetch(
            """
            SELECT
                date_trunc('day', timestamp) AS day,
                COUNT(*) FILTER (WHERE details->>'useful' = 'true') AS positive,
                COUNT(*) FILTER (WHERE details->>'useful' = 'false') AS negative,
                COUNT(*) AS total
            FROM audit_log
            WHERE action = 'feedback'
              AND timestamp > now() - make_interval(days => $1)
            GROUP BY day
            ORDER BY day ASC
            """,
            days,
        )
        daily = [
            {
                "date": r["day"].isoformat(),
                "positive": r["positive"],
                "negative": r["negative"],
                "total": r["total"],
            }
            for r in rows
        ]
        total_pos = sum(d["positive"] for d in daily)
        total_neg = sum(d["negative"] for d in daily)
        total_all = total_pos + total_neg
        return {
            "positive_rate": round(total_pos / total_all, 4) if total_all > 0 else 0.0,
            "total_positive": total_pos,
            "total_negative": total_neg,
            "daily": daily,
        }

    async def get_action_counts(self, days: int = 30) -> dict[str, int]:
        """Get action type breakdown for the last N days."""
        rows = await self.pool.fetch(
            """
            SELECT action, COUNT(*) AS cnt
            FROM audit_log
            WHERE timestamp > now() - make_interval(days => $1)
            GROUP BY action
            ORDER BY cnt DESC
            """,
            days,
        )
        return {r["action"]: r["cnt"] for r in rows}

    async def get_feedback_for_memory(self, memory_id: str) -> list[dict[str, Any]]:
        """Get per-memory feedback history."""
        rows = await self.pool.fetch(
            """
            SELECT timestamp, action, details
            FROM audit_log
            WHERE memory_id = $1 AND action = 'feedback'
            ORDER BY timestamp ASC
            """,
            memory_id,
        )
        return [
            {
                "timestamp": r["timestamp"].isoformat(),
                "details": json.loads(r["details"]) if r["details"] else {},
            }
            for r in rows
        ]

    async def get_feedback_similarity_distribution(self, days: int = 30) -> list[dict[str, Any]]:
        """Get similarity score histogram for feedback entries."""
        rows = await self.pool.fetch(
            """
            SELECT
                width_bucket(
                    COALESCE((details->>'similarity')::float, 0),
                    0, 1, 10
                ) AS bucket,
                COUNT(*) AS cnt
            FROM audit_log
            WHERE action = 'feedback'
              AND timestamp > now() - make_interval(days => $1)
              AND details->>'similarity' IS NOT NULL
            GROUP BY bucket
            ORDER BY bucket
            """,
            days,
        )
        return [
            {
                "bucket": r["bucket"],
                "range_start": round((r["bucket"] - 1) * 0.1, 1),
                "range_end": round(r["bucket"] * 0.1, 1),
                "count": r["cnt"],
            }
            for r in rows
        ]

    async def get_noisy_memories(
        self, min_negative: int = 3, days: int = 7
    ) -> list[dict[str, Any]]:
        """Find memories with excessive negative feedback."""
        rows = await self.pool.fetch(
            """
            SELECT
                memory_id,
                COUNT(*) FILTER (WHERE details->>'useful' = 'false') AS negative_count,
                COUNT(*) AS total_feedback
            FROM audit_log
            WHERE action = 'feedback'
              AND timestamp > now() - make_interval(days => $1)
            GROUP BY memory_id
            HAVING COUNT(*) FILTER (WHERE details->>'useful' = 'false') >= $2
            ORDER BY negative_count DESC
            LIMIT 50
            """,
            days,
            min_negative,
        )
        return [
            {
                "memory_id": r["memory_id"],
                "negative_count": r["negative_count"],
                "total_feedback": r["total_feedback"],
            }
            for r in rows
        ]

    async def get_all_memory_feedback_stats(
        self,
    ) -> dict[str, dict[str, int]]:
        """Get per-memory feedback useful/not_useful counts.

        Returns a dict mapping memory_id to {useful, not_useful}.
        Used by decay worker for feedback-aware decay.
        One query for all memories — avoids N+1.
        """
        rows = await self.pool.fetch(
            """
            SELECT
                memory_id,
                COUNT(*) FILTER (
                    WHERE details->>'useful' = 'true'
                ) AS useful,
                COUNT(*) FILTER (
                    WHERE details->>'useful' = 'false'
                ) AS not_useful
            FROM audit_log
            WHERE action = 'feedback'
            GROUP BY memory_id
            """,
        )
        return {
            r["memory_id"]: {
                "useful": r["useful"],
                "not_useful": r["not_useful"],
            }
            for r in rows
        }

    async def get_feedback_starved_memories(self, **_kwargs) -> list[dict[str, Any]]:
        """Find memories created but never given feedback.

        Uses 'create' audit entries (not 'access' — no access audit exists).
        Returns memory_ids that have been created but have zero feedback entries.
        Note: min_accesses cannot be enforced (access_count lives in Qdrant, not audit_log).
        """
        rows = await self.pool.fetch(
            """
            SELECT DISTINCT memory_id
            FROM audit_log
            WHERE action = 'create'
              AND memory_id IS NOT NULL
              AND memory_id NOT IN (
                  SELECT DISTINCT memory_id
                  FROM audit_log
                  WHERE action = 'feedback'
                    AND memory_id IS NOT NULL
              )
            LIMIT 50
            """,
        )
        return [{"memory_id": r["memory_id"]} for r in rows]

    async def get_importance_timeline(self, memory_id: str) -> list[dict[str, Any]]:
        """Reconstruct importance timeline for a memory from audit entries."""
        rows = await self.pool.fetch(
            """
            SELECT timestamp, action, details
            FROM audit_log
            WHERE memory_id = $1
              AND action IN ('create', 'feedback', 'decay',
                             'update_importance', 'update_durability')
            ORDER BY timestamp ASC
            """,
            memory_id,
        )
        events = []
        for r in rows:
            details = json.loads(r["details"]) if r["details"] else {}
            events.append(
                {
                    "timestamp": r["timestamp"].isoformat(),
                    "action": r["action"],
                    "importance": details.get("importance"),
                    "details": details,
                }
            )
        return events

    async def get_metrics_history(self, hours: int = 24) -> list[dict[str, Any]]:
        """Get metrics snapshots from the last N hours."""
        rows = await self.pool.fetch(
            """
            SELECT * FROM metrics_snapshot
            WHERE timestamp > now() - make_interval(hours => $1)
            ORDER BY timestamp ASC
            """,
            hours,
        )
        return [
            {
                "timestamp": r["timestamp"].isoformat(),
                "counters": json.loads(r["counters"])
                if isinstance(r["counters"], str)
                else r["counters"],
                "gauges": json.loads(r["gauges"]) if isinstance(r["gauges"], str) else r["gauges"],
            }
            for r in rows
        ]


# Singleton
_store: PostgresStore | None = None


async def get_postgres_store() -> PostgresStore:
    """Get or create PostgreSQL store singleton."""
    global _store
    if _store is None:
        _store = PostgresStore()
        await _store.connect()
    return _store
