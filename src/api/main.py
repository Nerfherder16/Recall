"""
Recall API - FastAPI application for living memory.

Main entry point for the memory system.
"""

from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import httpx
import structlog
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from src.core import get_settings
from src.core.metrics import get_metrics
from src.storage import get_neo4j_store, get_postgres_store, get_qdrant_store, get_redis_store

from .auth import require_auth
from .rate_limit import limiter
from .routes import admin, documents, events, health_dashboard, ingest, memory, observe, ops, search, session

logger = structlog.get_logger()
settings = get_settings()


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
    postgres = None

    # Initialize storage connections
    try:
        qdrant = await get_qdrant_store()
        neo4j = await get_neo4j_store()
        redis = await get_redis_store()
        postgres = await get_postgres_store()

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
        if postgres:
            await postgres.close()

        # Reset singleton globals so hot-reload creates fresh connections
        import src.storage.qdrant as _qdrant_mod
        import src.storage.neo4j_store as _neo4j_mod
        import src.storage.redis_store as _redis_mod
        import src.storage.postgres_store as _postgres_mod
        import src.core.embeddings as _embed_mod
        import src.core.llm as _llm_mod
        import src.core.metrics as _metrics_mod

        _qdrant_mod._store = None
        _neo4j_mod._store = None
        _redis_mod._store = None
        _postgres_mod._store = None
        _embed_mod._embedding_service = None
        _llm_mod._llm = None
        _metrics_mod._collector = None


# =============================================================
# APP
# =============================================================

app = FastAPI(
    title="Recall",
    description="Living memory system for AI assistants",
    version="0.1.0",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
app.include_router(
    ops.router, prefix="/admin", tags=["ops"],
    dependencies=[Depends(require_auth)],
)
app.include_router(
    observe.router, prefix="/observe", tags=["observe"],
    dependencies=[Depends(require_auth)],
)
app.include_router(
    events.router, prefix="/events", tags=["events"],
    dependencies=[Depends(require_auth)],
)
app.include_router(
    health_dashboard.router, prefix="/admin", tags=["health"],
    dependencies=[Depends(require_auth)],
)
app.include_router(
    documents.router, prefix="/document", tags=["documents"],
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
        "postgres": "unknown",
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
        pg = await get_postgres_store()
        audit_count = await pg.pool.fetchval("SELECT count(*) FROM audit_log")
        checks["postgres"] = f"ok ({audit_count} audit entries)"
    except Exception as e:
        checks["postgres"] = f"error: {type(e).__name__}"

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


@app.get("/stats/domains", dependencies=[Depends(require_auth)])
async def get_domain_stats():
    """Get per-domain memory statistics."""
    try:
        qdrant = await get_qdrant_store()
        all_points = await qdrant.scroll_all(include_superseded=False)

        domain_data = defaultdict(lambda: {"count": 0, "total_importance": 0.0})

        for memory_id, payload in all_points:
            domain = payload.get("domain", "general")
            importance = payload.get("importance", 0.5)
            domain_data[domain]["count"] += 1
            domain_data[domain]["total_importance"] += importance

        domains = []
        for domain, data in sorted(domain_data.items(), key=lambda x: x[1]["count"], reverse=True):
            domains.append({
                "domain": domain,
                "count": data["count"],
                "avg_importance": round(data["total_importance"] / data["count"], 4) if data["count"] > 0 else 0,
            })

        return {"domains": domains}

    except Exception as e:
        logger.error("domain_stats_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus metrics endpoint (public, no auth — standard for scraping)."""
    metrics = get_metrics()

    # Update gauges from live store counts
    try:
        qdrant = await get_qdrant_store()
        count = await qdrant.count()
        metrics.set_gauge("recall_memories_total", value=float(count))
    except Exception:
        pass

    return PlainTextResponse(
        content=metrics.prometheus_format(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@app.get("/dashboard-legacy", dependencies=[Depends(require_auth)])
async def dashboard_legacy():
    """Serve the legacy ops dashboard."""
    html_path = Path(__file__).parent / "static" / "dashboard.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


# Serve React SPA dashboard if built, otherwise fall back to legacy
_dashboard_dir = Path(__file__).parent / "static" / "dashboard"
if _dashboard_dir.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount(
        "/dashboard",
        StaticFiles(directory=str(_dashboard_dir), html=True),
        name="dashboard",
    )
else:
    @app.get("/dashboard", dependencies=[Depends(require_auth)])
    async def dashboard():
        """Serve the ops dashboard (legacy HTML fallback)."""
        html_path = Path(__file__).parent / "static" / "dashboard.html"
        if not html_path.exists():
            raise HTTPException(status_code=404, detail="Dashboard not found")
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )
