"""
Signal-to-memory pipeline.

Called as a FastAPI BackgroundTask after turn ingestion.
Loads recent turns, runs signal detection via LLM, and
auto-stores high-confidence signals as memories.
"""

import structlog

from src.core import (
    Memory,
    MemorySource,
    Relationship,
    RelationshipType,
    get_embedding_service,
    get_settings,
)
from src.core.embeddings import OllamaUnavailableError
from src.core.metrics import get_metrics
from src.core.embeddings import content_hash
from src.core.models import SignalType
from src.core.signal_detector import (
    SIGNAL_IMPORTANCE,
    SIGNAL_TO_MEMORY_TYPE,
    SignalDetector,
)
from src.storage import get_neo4j_store, get_postgres_store, get_qdrant_store, get_redis_store

logger = structlog.get_logger()


async def process_signal_detection(session_id: str):
    """
    Full signal detection pipeline for a session.

    1. Load recent turns from Redis
    2. Run SignalDetector (LLM call)
    3. Auto-store high-confidence signals as memories
    4. Queue medium-confidence signals for review
    5. Discard low-confidence signals

    Wrapped in top-level error handling so BackgroundTask failures
    are always logged via structlog (Starlette only logs to stderr).
    """
    try:
        await _run_signal_detection(session_id)
    except Exception as e:
        logger.error(
            "signal_detection_background_task_failed",
            session_id=session_id,
            error=str(e),
            error_type=type(e).__name__,
        )


async def _run_signal_detection(session_id: str):
    """Inner implementation of signal detection pipeline."""
    settings = get_settings()
    redis = await get_redis_store()

    turns = await redis.get_recent_turns(session_id)
    if not turns:
        logger.debug("signal_detection_no_turns", session_id=session_id)
        return

    detector = SignalDetector()
    signals = await detector.detect(turns)

    if not signals:
        logger.debug("signal_detection_no_signals", session_id=session_id)
        return

    metrics = get_metrics()
    auto_stored = 0
    pending = 0
    discarded = 0

    for signal in signals:
        if signal.confidence >= settings.signal_confidence_auto_store:
            # High confidence — auto-store as memory
            memory_id = await _store_signal_as_memory(session_id, signal)
            if memory_id:
                auto_stored += 1
                metrics.increment("recall_signals_detected_total", {"outcome": "auto"})
                # Handle contradiction signals — find and supersede conflicting memory
                if signal.signal_type == SignalType.CONTRADICTION:
                    await _resolve_contradiction(memory_id, signal)

        elif signal.confidence >= settings.signal_confidence_pending:
            # Medium confidence — queue for review
            await redis.add_pending_signal(session_id, {
                "signal_type": signal.signal_type.value,
                "content": signal.content,
                "confidence": signal.confidence,
                "domain": signal.suggested_domain or "general",
                "tags": signal.suggested_tags,
            })
            pending += 1
            metrics.increment("recall_signals_detected_total", {"outcome": "pending"})

        else:
            # Below pending threshold — discard
            discarded += 1
            metrics.increment("recall_signals_detected_total", {"outcome": "discarded"})

    # Update session stats
    if auto_stored > 0:
        session = await redis.get_session(session_id)
        if session:
            current = int(session.get("signals_detected", 0))
            await redis.update_session(session_id, {
                "signals_detected": current + auto_stored,
            })

    logger.info(
        "signal_detection_complete",
        session_id=session_id,
        total_signals=len(signals),
        auto_stored=auto_stored,
        pending=pending,
        discarded=len(signals) - auto_stored - pending,
    )


async def _store_signal_as_memory(session_id: str, signal) -> str | None:
    """
    Store a detected signal as a Memory in Qdrant + Neo4j.

    Returns memory ID if stored, None if duplicate or error.
    """
    try:
        memory_type = SIGNAL_TO_MEMORY_TYPE.get(signal.signal_type)
        # Prefer LLM-scored importance, fall back to flat type-based default
        importance = (
            signal.suggested_importance
            if signal.suggested_importance is not None
            else SIGNAL_IMPORTANCE.get(signal.signal_type, 0.5)
        )

        chash = content_hash(signal.content)

        # Dedup check
        qdrant = await get_qdrant_store()
        existing = await qdrant.find_by_content_hash(chash)
        if existing:
            logger.debug(
                "signal_dedup_hit",
                signal_type=signal.signal_type.value,
                existing_id=existing,
            )
            return None

        memory = Memory(
            content=signal.content,
            content_hash=chash,
            memory_type=memory_type,
            source=MemorySource.SYSTEM,
            domain=signal.suggested_domain or "general",
            tags=[f"signal:{signal.signal_type.value}"] + signal.suggested_tags,
            importance=importance,
            confidence=signal.confidence,
            session_id=session_id,
            metadata={"auto_detected": True},
        )

        # Generate embedding
        try:
            embedding_service = await get_embedding_service()
            embedding = await embedding_service.embed(signal.content)
        except OllamaUnavailableError:
            logger.warning("signal_store_ollama_unavailable", signal_type=signal.signal_type.value)
            return None

        # Store in Qdrant
        await qdrant.store(memory, embedding)

        # Create graph node — compensating delete on failure
        try:
            neo4j = await get_neo4j_store()
            await neo4j.create_memory_node(memory)
        except Exception as neo4j_err:
            logger.error("neo4j_write_failed_compensating", id=memory.id, error=str(neo4j_err))
            await qdrant.delete(memory.id)
            return None

        logger.info(
            "signal_auto_stored",
            memory_id=memory.id,
            signal_type=signal.signal_type.value,
            confidence=signal.confidence,
        )

        # Audit log (fire-and-forget)
        pg = await get_postgres_store()
        await pg.log_audit(
            "create", memory.id, actor="signal",
            session_id=session_id,
            details={"signal_type": signal.signal_type.value, "confidence": signal.confidence},
        )

        return memory.id

    except Exception as e:
        logger.error(
            "signal_store_error",
            error=str(e),
            signal_type=signal.signal_type.value,
        )
        return None


async def _resolve_contradiction(new_memory_id: str, signal) -> None:
    """
    Handle contradiction signals by finding and superseding the conflicting memory.

    Searches for the most similar existing memory to the contradiction content,
    creates a CONTRADICTS relationship, and marks the old one as superseded.
    """
    try:
        qdrant = await get_qdrant_store()
        neo4j = await get_neo4j_store()

        try:
            embedding_service = await get_embedding_service()
            embedding = await embedding_service.embed(signal.content)
        except OllamaUnavailableError:
            logger.warning("contradiction_resolution_ollama_unavailable", new_memory=new_memory_id)
            return

        # Search for the memory being contradicted
        similar = await qdrant.search(
            query_vector=embedding,
            limit=5,
        )

        # Find the best match that isn't the new memory itself
        for mem_id, similarity, payload in similar:
            if mem_id == new_memory_id:
                continue
            if payload.get("superseded_by"):
                continue
            # Must be reasonably similar to be the contradicted memory
            if similarity < 0.5:
                continue

            # Create CONTRADICTS relationship
            relationship = Relationship(
                source_id=new_memory_id,
                target_id=mem_id,
                relationship_type=RelationshipType.CONTRADICTS,
                strength=signal.confidence,
            )
            await neo4j.create_relationship(relationship)

            # Supersede the old memory
            await qdrant.mark_superseded(mem_id, new_memory_id)
            await neo4j.mark_superseded(mem_id, new_memory_id)

            logger.info(
                "contradiction_resolved",
                new_memory=new_memory_id,
                superseded_memory=mem_id,
                similarity=round(similarity, 3),
            )
            return  # Only supersede the single best match

    except Exception as e:
        logger.error(
            "contradiction_resolution_error",
            new_memory=new_memory_id,
            error=str(e),
        )
