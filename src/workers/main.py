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
from src.core.metrics import get_metrics

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
        metrics = get_metrics()
        metrics.increment("recall_consolidation_runs_total")

        try:
            from src.core.consolidation import create_consolidator

            consolidator = await create_consolidator()
            results = await consolidator.consolidate()

            merges = sum(len(r.source_memories) for r in results)
            metrics.increment("recall_consolidation_merges_total", value=merges)

            logger.info(
                "consolidation_complete",
                clusters_merged=len(results),
                total_memories_merged=merges,
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
    metrics = get_metrics()
    metrics.increment("recall_decay_runs_total")

    try:
        from src.workers.decay import DecayWorker

        worker = DecayWorker(ctx["qdrant"], ctx["neo4j"])
        stats = await worker.run()

        metrics.increment("recall_decay_archived_total", value=stats["archived"])

        logger.info(
            "decay_complete",
            memories_processed=stats["processed"],
            memories_archived=stats["archived"],
        )

    except Exception as e:
        logger.error("decay_error", error=str(e))
        raise


async def save_metrics_snapshot(ctx: dict):
    """
    Periodic metrics snapshot to PostgreSQL.

    Saves a point-in-time dump of all counters and gauges
    for historical dashboard views.
    """
    logger.info("saving_metrics_snapshot")
    try:
        from src.storage import get_postgres_store

        pg = await get_postgres_store()
        metrics = get_metrics()
        await pg.save_metrics_snapshot(
            counters=dict(metrics._counters),
            gauges=dict(metrics._gauges),
        )
        logger.info("metrics_snapshot_saved")
    except Exception as e:
        logger.error("metrics_snapshot_error", error=str(e))
        # Don't raise — best-effort, don't retry via ARQ


async def run_ml_retrain(ctx: dict):
    """
    Weekly ML model retraining.

    Retrains the signal classifier and reranker from latest data.
    """
    logger.info("running_ml_retrain")
    try:
        from src.core.signal_classifier import invalidate_classifier_cache
        from src.core.signal_classifier_trainer import train_signal_classifier
        from src.storage import get_postgres_store

        redis = ctx["redis"]
        pg = await get_postgres_store()
        result = await train_signal_classifier(redis, pg)
        invalidate_classifier_cache()
        logger.info(
            "signal_classifier_retrained",
            n_samples=result.get("n_samples"),
            binary_cv_score=result.get("binary_cv_score"),
        )
    except Exception as e:
        logger.error("signal_classifier_retrain_error", error=str(e))

    try:
        from src.core.reranker import invalidate_reranker_cache
        from src.core.reranker_trainer import train_reranker

        redis = ctx["redis"]
        pg = await get_postgres_store()
        result = await train_reranker(redis, pg)
        invalidate_reranker_cache()
        logger.info(
            "reranker_retrained",
            n_samples=result.get("n_samples"),
            cv_score=result.get("cv_score"),
        )
    except Exception as e:
        logger.error("reranker_retrain_error", error=str(e))


async def run_pattern_extraction(ctx: dict):
    """
    Daily pattern extraction.

    Analyzes episodic memories to find recurring patterns,
    then creates semantic memories from those patterns.
    """
    logger.info("running_pattern_extraction")
    metrics = get_metrics()
    metrics.increment("recall_pattern_runs_total")

    try:
        from src.workers.patterns import PatternExtractor

        extractor = PatternExtractor(ctx["qdrant"], ctx["neo4j"])
        results = await extractor.extract()

        metrics.increment("recall_patterns_created_total", value=results["patterns_created"])

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
        save_metrics_snapshot,
        run_ml_retrain,
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
        # Save metrics snapshot every hour at :30 (staggered from consolidation)
        cron(
            save_metrics_snapshot,
            hour=None,
            minute=30,
        ),
        # Run pattern extraction daily at 3:30am (staggered from midnight jobs)
        cron(
            run_pattern_extraction,
            hour=3,
            minute=30,
        ),
        # Retrain ML models weekly Sunday 4am
        cron(
            run_ml_retrain,
            weekday=6,
            hour=4,
            minute=0,
        ),
    ]

    on_startup = startup
    on_shutdown = shutdown

    # Redis connection
    redis_settings = RedisSettings.from_dsn(settings.redis_url)

    # Job settings
    max_jobs = 10
    job_timeout = timedelta(minutes=30)
