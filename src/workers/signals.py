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
    get_embedding_service,
    get_settings,
)
from src.core.embeddings import content_hash
from src.core.signal_detector import (
    SIGNAL_IMPORTANCE,
    SIGNAL_TO_MEMORY_TYPE,
    SignalDetector,
)
from src.storage import get_neo4j_store, get_qdrant_store, get_redis_store

logger = structlog.get_logger()


async def process_signal_detection(session_id: str):
    """
    Full signal detection pipeline for a session.

    1. Load recent turns from Redis
    2. Run SignalDetector (LLM call)
    3. Auto-store high-confidence signals as memories
    4. Queue medium-confidence signals for review
    5. Discard low-confidence signals
    """
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

    auto_stored = 0
    pending = 0

    for signal in signals:
        if signal.confidence >= settings.signal_confidence_auto_store:
            # High confidence — auto-store as memory
            stored = await _store_signal_as_memory(session_id, signal)
            if stored:
                auto_stored += 1

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

        # Below pending threshold — discard

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


async def _store_signal_as_memory(session_id: str, signal) -> bool:
    """
    Store a detected signal as a Memory in Qdrant + Neo4j.

    Returns True if stored, False if duplicate.
    """
    try:
        memory_type = SIGNAL_TO_MEMORY_TYPE.get(signal.signal_type)
        importance = SIGNAL_IMPORTANCE.get(signal.signal_type, 0.5)

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
            return False

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
        embedding_service = await get_embedding_service()
        embedding = await embedding_service.embed(signal.content)

        # Store in Qdrant
        await qdrant.store(memory, embedding)

        # Create graph node
        neo4j = await get_neo4j_store()
        await neo4j.create_memory_node(memory)

        logger.info(
            "signal_auto_stored",
            memory_id=memory.id,
            signal_type=signal.signal_type.value,
            confidence=signal.confidence,
        )
        return True

    except Exception as e:
        logger.error(
            "signal_store_error",
            error=str(e),
            signal_type=signal.signal_type.value,
        )
        return False
