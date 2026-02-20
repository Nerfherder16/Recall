"""
Server-Sent Events endpoint for real-time dashboard updates.
"""

import asyncio
import json

import structlog
from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

logger = structlog.get_logger()
router = APIRouter()


@router.get("/stream")
async def event_stream(request: Request):
    """
    SSE endpoint for real-time dashboard updates.

    Streams health and stats data every 5 seconds.
    """

    async def generate():
        while True:
            if await request.is_disconnected():
                break

            try:
                from src.storage import (
                    get_neo4j_store,
                    get_postgres_store,
                    get_qdrant_store,
                    get_redis_store,
                )

                # Gather stats
                data = {}
                try:
                    qdrant = await get_qdrant_store()
                    data["memory_count"] = await qdrant.count()
                    data["fact_count"] = await qdrant.count_facts()
                    data["qdrant"] = "ok"
                except Exception:
                    data["qdrant"] = "error"

                try:
                    neo4j = await get_neo4j_store()
                    stats = await neo4j.get_statistics()
                    data["graph_nodes"] = stats.get("memories", 0)
                    data["relationships"] = stats.get("relationships", 0)
                    data["neo4j"] = "ok"
                except Exception:
                    data["neo4j"] = "error"

                try:
                    redis = await get_redis_store()
                    data["active_sessions"] = await redis.get_active_sessions()
                    data["redis"] = "ok"
                except Exception:
                    data["redis"] = "error"

                try:
                    pg = await get_postgres_store()
                    data["audit_count"] = await pg.pool.fetchval("SELECT count(*) FROM audit_log")
                    data["postgres"] = "ok"
                except Exception:
                    data["postgres"] = "error"

                yield {"event": "health", "data": json.dumps(data)}

            except Exception as e:
                logger.error("sse_error", error=str(e))
                yield {"event": "error", "data": json.dumps({"error": "Internal server error"})}

            await asyncio.sleep(5)

    return EventSourceResponse(generate())
