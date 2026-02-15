"""
Background worker main entry point.

Workers handle:
- Memory consolidation
- Importance decay
- Pattern extraction
- Event processing
"""

import asyncio
from datetime import timedelta

import structlog
from arq import cron
from arq.connections import RedisSettings

from src.core import get_settings

logger = structlog.get_logger()
settings = get_settings()

# Lock prevents overlapping consolidation runs
_consolidation_lock = asyncio.Lock()


async def startup(ctx: dict):
    """Worker startup - initialize connections."""
    logger.info("worker_starting")

    # Initialize storage connections
    from src.storage import get_neo4j_store, get_qdrant_store, get_redis_store

    ctx["qdrant"] = await get_qdrant_store()
    ctx["neo4j"] = await get_neo4j_store()
    ctx["redis"] = await get_redis_store()

    logger.info("worker_started")


async def shutdown(ctx: dict):
    """Worker shutdown - cleanup."""
    logger.info("worker_shutting_down")

    if ctx.get("qdrant"):
        await ctx["qdrant"].close()
    if ctx.get("neo4j"):
        await ctx["neo4j"].close()
    if ctx.get("redis"):
        await ctx["redis"].close()


async def run_consolidation(ctx: dict):
    """
    Periodic memory consolidation.

    Finds similar memories and merges them into stronger, consolidated memories.
    Uses a lock to prevent overlapping runs.
    """
    if _consolidation_lock.locked():
        logger.info("consolidation_skipped_already_running")
        return

    async with _consolidation_lock:
        logger.info("running_consolidation")

        try:
            from src.core.consolidation import create_consolidator

            consolidator = await create_consolidator()
            results = await consolidator.consolidate()

            logger.info(
                "consolidation_complete",
                clusters_merged=len(results),
                total_memories_merged=sum(len(r.source_memories) for r in results),
            )

        except Exception as e:
            logger.error("consolidation_error", error=str(e))
            raise


async def run_decay(ctx: dict):
    """
    Periodic importance decay.

    Decreases importance of memories that haven't been accessed recently.
    Memories with high stability decay slower.
    """
    logger.info("running_decay")

    try:
        from src.workers.decay import DecayWorker

        worker = DecayWorker(ctx["qdrant"], ctx["neo4j"])
        stats = await worker.run()

        logger.info(
            "decay_complete",
            memories_processed=stats["processed"],
            memories_archived=stats["archived"],
        )

    except Exception as e:
        logger.error("decay_error", error=str(e))
        raise


async def run_pattern_extraction(ctx: dict):
    """
    Daily pattern extraction.

    Analyzes episodic memories to find recurring patterns,
    then creates semantic memories from those patterns.
    """
    logger.info("running_pattern_extraction")

    try:
        from src.workers.patterns import PatternExtractor

        extractor = PatternExtractor(ctx["qdrant"], ctx["neo4j"])
        results = await extractor.extract()

        logger.info(
            "pattern_extraction_complete",
            patterns_found=results["patterns_created"],
        )

    except Exception as e:
        logger.error("pattern_extraction_error", error=str(e))
        raise


class WorkerSettings:
    """ARQ worker settings."""

    functions = [
        run_consolidation,
        run_decay,
        run_pattern_extraction,
    ]

    cron_jobs = [
        # Run consolidation every hour at :00
        cron(
            run_consolidation,
            hour=None,
            minute=0,
        ),
        # Run decay every 30 minutes at :15/:45 (staggered from consolidation)
        cron(
            run_decay,
            hour=None,
            minute={15, 45},
        ),
        # Run pattern extraction daily at 3:30am (staggered from midnight jobs)
        cron(
            run_pattern_extraction,
            hour=3,
            minute=30,
        ),
    ]

    on_startup = startup
    on_shutdown = shutdown

    # Redis connection
    redis_settings = RedisSettings.from_dsn(settings.redis_url)

    # Job settings
    max_jobs = 10
    job_timeout = timedelta(minutes=30)
