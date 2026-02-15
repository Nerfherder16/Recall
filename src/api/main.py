"""
Recall API - FastAPI application for living memory.

Main entry point for the memory system.
"""

import secrets
from contextlib import asynccontextmanager
from datetime import datetime

import httpx
import structlog
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core import get_settings
from src.storage import get_neo4j_store, get_qdrant_store, get_redis_store

from .routes import admin, ingest, memory, search, session

logger = structlog.get_logger()
settings = get_settings()


# =============================================================
# AUTH
# =============================================================

_bearer_scheme = HTTPBearer(auto_error=False)


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
):
    """Validate Bearer token if RECALL_API_KEY is configured."""
    if not settings.api_key:
        return  # Auth disabled — dev mode

    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Missing API key")

    # Constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(credentials.credentials, settings.api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")


# =============================================================
# LIFESPAN
# =============================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown."""
    # Startup
    logger.info(
        "starting_recall_api",
        env=settings.env,
        auth_enabled=bool(settings.api_key),
    )

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

        # Reset singleton globals so hot-reload creates fresh connections
        import src.storage.qdrant as _qdrant_mod
        import src.storage.neo4j_store as _neo4j_mod
        import src.storage.redis_store as _redis_mod
        import src.core.embeddings as _embed_mod
        import src.core.llm as _llm_mod

        _qdrant_mod._store = None
        _neo4j_mod._store = None
        _redis_mod._store = None
        _embed_mod._embedding_service = None
        _llm_mod._llm = None


# =============================================================
# APP
# =============================================================

app = FastAPI(
    title="Recall",
    description="Living memory system for AI assistants",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware — configurable via RECALL_ALLOWED_ORIGINS
_origins = [
    o.strip()
    for o in settings.allowed_origins.split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================
# ERROR SANITIZATION
# =============================================================


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions — log details, return generic message."""
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        error_type=type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Include routers — all require auth except /health
app.include_router(
    memory.router, prefix="/memory", tags=["memory"],
    dependencies=[Depends(require_auth)],
)
app.include_router(
    search.router, prefix="/search", tags=["search"],
    dependencies=[Depends(require_auth)],
)
app.include_router(
    session.router, prefix="/session", tags=["session"],
    dependencies=[Depends(require_auth)],
)
app.include_router(
    admin.router, prefix="/admin", tags=["admin"],
    dependencies=[Depends(require_auth)],
)
app.include_router(
    ingest.router, prefix="/ingest", tags=["ingest"],
    dependencies=[Depends(require_auth)],
)


# =============================================================
# PUBLIC ENDPOINTS (no auth required)
# =============================================================


@app.get("/health")
async def health_check():
    """Health check endpoint (always public for monitoring)."""
    checks = {
        "api": "ok",
        "qdrant": "unknown",
        "neo4j": "unknown",
        "redis": "unknown",
        "ollama": "unknown",
    }

    try:
        qdrant = await get_qdrant_store()
        count = await qdrant.count()
        checks["qdrant"] = f"ok ({count} memories)"
    except Exception as e:
        checks["qdrant"] = f"error: {type(e).__name__}"

    try:
        neo4j = await get_neo4j_store()
        stats = await neo4j.get_statistics()
        checks["neo4j"] = f"ok ({stats['memories']} nodes)"
    except Exception as e:
        checks["neo4j"] = f"error: {type(e).__name__}"

    try:
        redis = await get_redis_store()
        sessions = await redis.get_active_sessions()
        checks["redis"] = f"ok ({sessions} sessions)"
    except Exception as e:
        checks["redis"] = f"error: {type(e).__name__}"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{settings.ollama_host}/api/tags")
            if r.status_code == 200:
                models = [m.get("name", "") for m in r.json().get("models", [])]
                checks["ollama"] = f"ok ({len(models)} models)"
            else:
                checks["ollama"] = f"error: status {r.status_code}"
    except Exception as e:
        checks["ollama"] = f"error: {type(e).__name__}"

    healthy = all("ok" in str(v) for v in checks.values())

    return {
        "status": "healthy" if healthy else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": checks,
    }


@app.get("/stats", dependencies=[Depends(require_auth)])
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
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )
