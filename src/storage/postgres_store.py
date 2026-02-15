"""
PostgreSQL storage for audit log, session archive, and metrics persistence.

Uses raw asyncpg (no ORM) — consistent with the rest of the codebase.
All write operations are fire-and-forget: Postgres failures never block
the main operation.
"""

import json
from datetime import datetime
from typing import Any

import asyncpg
import structlog

from src.core import get_settings

logger = structlog.get_logger()

# SQL for table creation (run on connect)
_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGSERIAL PRIMARY KEY,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    action      TEXT NOT NULL,
    memory_id   TEXT NOT NULL,
    actor       TEXT NOT NULL DEFAULT 'system',
    details     JSONB,
    session_id  TEXT
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
    ):
        """Append an audit entry. Fire-and-forget — never raises."""
        try:
            await self.pool.execute(
                """
                INSERT INTO audit_log (action, memory_id, actor, details, session_id)
                VALUES ($1, $2, $3, $4::jsonb, $5)
                """,
                action,
                memory_id,
                actor,
                json.dumps(details) if details else None,
                session_id,
            )
        except Exception as e:
            logger.warning("audit_log_write_failed", error=str(e), action=action, memory_id=memory_id)

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

        conditions.append(f"${idx}")
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
            }
            for r in rows
        ]

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
                datetime.fromisoformat(session_data["started_at"]) if session_data.get("started_at") else datetime.utcnow(),
                datetime.fromisoformat(session_data["ended_at"]) if session_data.get("ended_at") else None,
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
                "counters": json.loads(r["counters"]) if isinstance(r["counters"], str) else r["counters"],
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
