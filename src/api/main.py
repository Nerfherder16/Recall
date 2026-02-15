"""
Recall API - FastAPI application for living memory.

Main entry point for the memory system.
"""

from contextlib import asynccontextmanager
from datetime import datetime

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.core import get_settings
from src.storage import get_neo4j_store, get_qdrant_store, get_redis_store

from .routes import admin, ingest, memory, search, session

logger = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown."""
    # Startup
    logger.info("starting_recall_api", env=settings.env)

    qdrant = None
    neo4j = None
    redis = None

    # Initialize storage connections
    try:
        qdrant = await get_qdrant_store()
        neo4j = await get_neo4j_store()
        redis = await get_redis_store()

        logger.info("storage_connections_established")

        yield

    finally:
        # Shutdown
        logger.info("shutting_down_recall_api")

        # Close connections
        if qdrant:
            await qdrant.close()
        if neo4j:
            await neo4j.close()
        if redis:
            await redis.close()


app = FastAPI(
    title="Recall",
    description="Living memory system for AI assistants",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(memory.router, prefix="/memory", tags=["memory"])
app.include_router(search.router, prefix="/search", tags=["search"])
app.include_router(session.router, prefix="/session", tags=["session"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(ingest.router, prefix="/ingest", tags=["ingest"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    checks = {
        "api": "ok",
        "qdrant": "unknown",
        "neo4j": "unknown",
        "redis": "unknown",
    }

    try:
        qdrant = await get_qdrant_store()
        count = await qdrant.count()
        checks["qdrant"] = f"ok ({count} memories)"
    except Exception as e:
        checks["qdrant"] = f"error: {e}"

    try:
        neo4j = await get_neo4j_store()
        stats = await neo4j.get_statistics()
        checks["neo4j"] = f"ok ({stats['memories']} nodes)"
    except Exception as e:
        checks["neo4j"] = f"error: {e}"

    try:
        redis = await get_redis_store()
        sessions = await redis.get_active_sessions()
        checks["redis"] = f"ok ({sessions} sessions)"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    healthy = all("ok" in str(v) for v in checks.values())

    return {
        "status": "healthy" if healthy else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": checks,
    }


@app.get("/stats")
async def get_stats():
    """Get system statistics."""
    try:
        qdrant = await get_qdrant_store()
        neo4j = await get_neo4j_store()
        redis = await get_redis_store()

        memory_count = await qdrant.count()
        graph_stats = await neo4j.get_statistics()
        active_sessions = await redis.get_active_sessions()

        return {
            "memories": {
                "total": memory_count,
                "graph_nodes": graph_stats["memories"],
                "relationships": graph_stats["relationships"],
            },
            "sessions": {
                "active": active_sessions,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error("stats_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )
