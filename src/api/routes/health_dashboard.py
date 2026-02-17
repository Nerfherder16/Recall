"""
Health dashboard routes.

Provides system health overview, per-memory force profiles,
and conflict detection.
"""

import json

import structlog
from fastapi import APIRouter, HTTPException, Request

from src.api.rate_limit import limiter
from src.core.health import create_health_computer
from src.storage import get_redis_store

logger = structlog.get_logger()
router = APIRouter()

DASHBOARD_CACHE_KEY = "recall:health:dashboard"
DASHBOARD_CACHE_TTL = 300  # 5 minutes

CONFLICTS_CACHE_KEY = "recall:conflicts"
CONFLICTS_CACHE_TTL = 600  # 10 minutes


@router.get("/health/dashboard")
@limiter.limit("10/minute")
async def get_health_dashboard(request: Request):
    """
    Get system health dashboard.

    Returns feedback metrics, population balance, graph cohesion,
    pin ratio, importance distribution, and feedback similarity.
    Cached for 5 minutes.
    """
    try:
        redis = await get_redis_store()

        # Check cache
        cached = await redis.client.get(DASHBOARD_CACHE_KEY)
        if cached:
            return json.loads(cached)

        computer = await create_health_computer()
        dashboard = await computer.compute_dashboard()

        # Cache result
        await redis.client.setex(
            DASHBOARD_CACHE_KEY,
            DASHBOARD_CACHE_TTL,
            json.dumps(dashboard, default=str),
        )

        return dashboard

    except Exception as e:
        logger.error("health_dashboard_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/conflicts")
@limiter.limit("10/minute")
async def get_conflicts(request: Request):
    """
    Detect potential conflicts in the memory system.

    Returns noisy memories, feedback-starved memories, orphan hubs,
    and other anomalies. Cached for 10 minutes.
    """
    try:
        redis = await get_redis_store()

        # Check cache
        cached = await redis.client.get(CONFLICTS_CACHE_KEY)
        if cached:
            return {"conflicts": json.loads(cached)}

        computer = await create_health_computer()
        conflicts = await computer.compute_conflicts()

        # Cache result
        await redis.client.setex(
            CONFLICTS_CACHE_KEY,
            CONFLICTS_CACHE_TTL,
            json.dumps(conflicts, default=str),
        )

        return {"conflicts": conflicts}

    except Exception as e:
        logger.error("conflicts_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")
