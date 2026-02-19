"""
Signal-to-memory pipeline.

Called as a FastAPI BackgroundTask after turn ingestion.
Loads recent turns, runs signal detection via LLM, and
auto-stores high-confidence signals as memories.
"""

import asyncio

import structlog

from src.core import (
    Memory,
    MemorySource,
    Relationship,
    RelationshipType,
    get_embedding_service,
    get_settings,
)
from src.core.embeddings import OllamaUnavailableError, content_hash
from src.core.metrics import get_metrics
from src.core.models import AntiPattern, Durability, SignalType
from src.core.signal_detector import (
    SIGNAL_DURABILITY,
    SIGNAL_IMPORTANCE,
    SIGNAL_TO_MEMORY_TYPE,
    SignalDetector,
)
from src.storage import get_neo4j_store, get_postgres_store, get_qdrant_store, get_redis_store

logger = structlog.get_logger()

# Serialize LLM calls — single-threaded Ollama can't handle concurrent signal detection
_signal_semaphore = asyncio.Semaphore(1)


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

    # ML pre-filter: skip expensive LLM call if classifier says "no signal"
    from src.core.signal_classifier import get_signal_classifier

    classifier = await get_signal_classifier(redis)
    if classifier is not None:
        prediction = classifier.predict(turns)
        if not prediction["is_signal"]:
            logger.info(
                "signal_ml_skip",
                session_id=session_id,
                probability=round(prediction["signal_probability"], 3),
            )
            return
        logger.debug(
            "signal_ml_pass",
            session_id=session_id,
            probability=round(prediction["signal_probability"], 3),
            predicted_type=prediction.get("predicted_type"),
        )

    # Extract ML hint for LLM prompt (advisory only)
    ml_hint = None
    ml_confidence = None
    if classifier is not None:
        ml_hint = prediction.get("predicted_type")
        ml_confidence = prediction.get("signal_probability")

    detector = SignalDetector()
    async with _signal_semaphore:
        signals = await detector.detect(
            turns,
            ml_hint=ml_hint,
            ml_confidence=ml_confidence,
        )

    if not signals:
        logger.debug("signal_detection_no_signals", session_id=session_id)
        return

    metrics = get_metrics()
    auto_stored = 0
    pending = 0
    discarded = 0

    for signal in signals:
        if signal.confidence >= settings.signal_confidence_auto_store:
            # WARNING signals → AntiPattern storage (not regular Memory)
            if signal.signal_type == SignalType.WARNING:
                stored = await _store_signal_as_anti_pattern(session_id, signal)
                if stored:
                    auto_stored += 1
                    metrics.increment("recall_signals_detected_total", {"outcome": "auto"})
                continue

            # High confidence — auto-store as memory
            memory_id, mem_embedding = await _store_signal_as_memory(session_id, signal)
            if memory_id:
                auto_stored += 1
                metrics.increment("recall_signals_detected_total", {"outcome": "auto"})
                # Handle contradiction signals — pass embedding to avoid re-embed
                if signal.signal_type == SignalType.CONTRADICTION:
                    await _resolve_contradiction(
                        memory_id,
                        signal,
                        embedding=mem_embedding,
                    )

        elif signal.confidence >= settings.signal_confidence_pending:
            # Medium confidence — queue for review
            await redis.add_pending_signal(
                session_id,
                {
                    "signal_type": signal.signal_type.value,
                    "content": signal.content,
                    "confidence": signal.confidence,
                    "domain": signal.suggested_domain or "general",
                    "tags": signal.suggested_tags,
                    "importance": signal.suggested_importance,
                    "durability": signal.suggested_durability,
                },
            )
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
            await redis.update_session(
                session_id,
                {
                    "signals_detected": current + auto_stored,
                },
            )

    logger.info(
        "signal_detection_complete",
        session_id=session_id,
        total_signals=len(signals),
        auto_stored=auto_stored,
        pending=pending,
        discarded=len(signals) - auto_stored - pending,
    )


async def _store_signal_as_memory(
    session_id: str,
    signal,
) -> tuple[str | None, list[float] | None]:
    """
    Store a detected signal as a Memory in Qdrant + Neo4j.

    Returns (memory_id, embedding) if stored, (None, None) if duplicate or error.
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
            return None, None

        # Resolve durability: LLM suggestion → signal-type default → ephemeral
        durability_str = signal.suggested_durability or SIGNAL_DURABILITY.get(
            signal.signal_type, "ephemeral"
        )
        try:
            durability = Durability(durability_str)
        except ValueError:
            durability = Durability.EPHEMERAL

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
            durability=durability,
            initial_importance=importance,
        )

        # Generate embedding
        try:
            embedding_service = await get_embedding_service()
            embedding = await embedding_service.embed(signal.content)
        except OllamaUnavailableError:
            logger.warning("signal_store_ollama_unavailable", signal_type=signal.signal_type.value)
            return None, None

        # Store in Qdrant
        await qdrant.store(memory, embedding)

        # Create graph node — compensating delete on failure
        try:
            neo4j = await get_neo4j_store()
            await neo4j.create_memory_node(memory)
        except Exception as neo4j_err:
            logger.error("neo4j_write_failed_compensating", id=memory.id, error=str(neo4j_err))
            await qdrant.delete(memory.id)
            return None, None

        logger.info(
            "signal_auto_stored",
            memory_id=memory.id,
            signal_type=signal.signal_type.value,
            confidence=signal.confidence,
        )

        # Audit log (fire-and-forget)
        pg = await get_postgres_store()
        await pg.log_audit(
            "create",
            memory.id,
            actor="signal",
            session_id=session_id,
            details={"signal_type": signal.signal_type.value, "confidence": signal.confidence},
        )

        # Auto-link to similar memories
        try:
            from src.core.auto_linker import auto_link_memory

            await auto_link_memory(memory.id, embedding, memory.domain)
        except Exception as link_err:
            logger.debug("signal_auto_link_skipped", error=str(link_err))

        return memory.id, embedding

    except Exception as e:
        logger.error(
            "signal_store_error",
            error=str(e),
            signal_type=signal.signal_type.value,
        )
        return None, None


async def _resolve_contradiction(
    new_memory_id: str,
    signal,
    *,
    embedding: list[float] | None = None,
) -> None:
    """
    Handle contradiction signals by finding and superseding the conflicting memory.

    Searches for the most similar existing memory to the contradiction content,
    creates a CONTRADICTS relationship, and marks the old one as superseded.
    """
    try:
        qdrant = await get_qdrant_store()
        neo4j = await get_neo4j_store()

        # Use passed embedding or generate new one
        if embedding is None:
            try:
                embedding_service = await get_embedding_service()
                embedding = await embedding_service.embed(signal.content)
            except OllamaUnavailableError:
                logger.warning(
                    "contradiction_resolution_ollama_unavailable",
                    new_memory=new_memory_id,
                )
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


async def _store_signal_as_anti_pattern(session_id: str, signal) -> bool:
    """
    Store a WARNING signal as an AntiPattern in the anti-patterns collection.

    Returns True if stored, False on error or duplicate.
    """
    try:
        # Parse pattern/warning from content — first sentence is pattern, rest is warning
        content = signal.content.strip()
        parts = content.split(". ", 1)
        pattern = parts[0].strip()
        warning = parts[1].strip() if len(parts) > 1 else content

        anti_pattern = AntiPattern(
            pattern=pattern,
            warning=warning,
            severity="warning",
            domain=signal.suggested_domain or "general",
            tags=[f"signal:{signal.signal_type.value}"] + signal.suggested_tags,
        )

        try:
            embedding_service = await get_embedding_service()
            embedding = await embedding_service.embed(anti_pattern.pattern)
        except OllamaUnavailableError:
            logger.warning("anti_pattern_store_ollama_unavailable")
            return False

        qdrant = await get_qdrant_store()
        await qdrant.store_anti_pattern(anti_pattern, embedding)

        logger.info(
            "anti_pattern_auto_stored",
            id=anti_pattern.id,
            domain=anti_pattern.domain,
        )

        pg = await get_postgres_store()
        await pg.log_audit(
            "create_anti_pattern",
            anti_pattern.id,
            actor="signal",
            session_id=session_id,
            details={"severity": anti_pattern.severity, "domain": anti_pattern.domain},
        )

        return True

    except Exception as e:
        logger.error("anti_pattern_store_error", error=str(e))
        return False
