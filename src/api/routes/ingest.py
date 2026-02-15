"""
Ingest routes — conversation turn ingestion and signal detection.
"""

from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from src.core import (
    Memory,
    MemorySource,
    MemoryType,
    get_embedding_service,
    get_settings,
)
from src.core.embeddings import content_hash
from src.core.signal_detector import SIGNAL_IMPORTANCE, SIGNAL_TO_MEMORY_TYPE
from src.storage import get_neo4j_store, get_qdrant_store, get_redis_store
from src.workers.signals import process_signal_detection

logger = structlog.get_logger()
router = APIRouter()


# =============================================================
# REQUEST/RESPONSE MODELS
# =============================================================


class Turn(BaseModel):
    """A single conversation turn."""

    role: str
    content: str
    timestamp: str | None = None


class IngestTurnsRequest(BaseModel):
    """Request to ingest conversation turns."""

    session_id: str
    turns: list[Turn] = Field(..., min_length=1)


class IngestTurnsResponse(BaseModel):
    """Response after ingesting turns."""

    session_id: str
    turns_ingested: int
    total_turns: int
    detection_queued: bool


class PendingSignalResponse(BaseModel):
    """A pending signal awaiting review."""

    index: int
    signal_type: str
    content: str
    confidence: float
    domain: str
    tags: list[str]


class ApproveSignalRequest(BaseModel):
    """Request to approve a pending signal."""

    index: int
    domain: str | None = None
    tags: list[str] | None = None
    importance: float | None = None


class ApproveSignalResponse(BaseModel):
    """Response after approving a signal."""

    memory_id: str
    content: str
    memory_type: str
    stored: bool


# =============================================================
# ROUTES
# =============================================================


@router.post("/turns", response_model=IngestTurnsResponse)
async def ingest_turns(request: IngestTurnsRequest, background_tasks: BackgroundTasks):
    """
    Ingest conversation turns and trigger background signal detection.

    Stores turns in Redis and kicks off async LLM analysis.
    Returns immediately — detection runs in background.
    """
    redis = await get_redis_store()

    # Validate session exists
    session = await redis.get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Store turns
    turn_dicts = [
        {
            "role": t.role,
            "content": t.content,
            "timestamp": t.timestamp or datetime.utcnow().isoformat(),
        }
        for t in request.turns
    ]
    total = await redis.add_turns(request.session_id, turn_dicts)

    # Queue signal detection
    background_tasks.add_task(process_signal_detection, request.session_id)

    logger.info(
        "turns_ingested",
        session_id=request.session_id,
        count=len(request.turns),
        total=total,
    )

    return IngestTurnsResponse(
        session_id=request.session_id,
        turns_ingested=len(request.turns),
        total_turns=total,
        detection_queued=True,
    )


@router.get("/{session_id}/signals", response_model=list[PendingSignalResponse])
async def get_pending_signals(session_id: str):
    """Get pending signals for a session (medium-confidence, awaiting review)."""
    redis = await get_redis_store()

    session = await redis.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    pending = await redis.get_pending_signals(session_id)

    return [
        PendingSignalResponse(
            index=i,
            signal_type=s.get("signal_type", ""),
            content=s.get("content", ""),
            confidence=s.get("confidence", 0.0),
            domain=s.get("domain", "general"),
            tags=s.get("tags", []),
        )
        for i, s in enumerate(pending)
    ]


@router.post("/{session_id}/signals/approve", response_model=ApproveSignalResponse)
async def approve_signal(session_id: str, request: ApproveSignalRequest):
    """Approve a pending signal — stores it as a memory."""
    redis = await get_redis_store()

    session = await redis.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    signal = await redis.remove_pending_signal(session_id, request.index)
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found at that index")

    # Resolve memory type from signal type
    from src.core.models import SignalType

    try:
        sig_type = SignalType(signal["signal_type"])
    except ValueError:
        sig_type = SignalType.FACT

    memory_type = SIGNAL_TO_MEMORY_TYPE.get(sig_type, MemoryType.SEMANTIC)
    importance = request.importance or SIGNAL_IMPORTANCE.get(sig_type, 0.5)
    domain = request.domain or signal.get("domain", "general")
    tags = request.tags if request.tags is not None else signal.get("tags", [])
    tags = [f"signal:{signal['signal_type']}"] + tags

    chash = content_hash(signal["content"])

    # Dedup check
    qdrant = await get_qdrant_store()
    existing = await qdrant.find_by_content_hash(chash)
    if existing:
        return ApproveSignalResponse(
            memory_id=existing,
            content=signal["content"],
            memory_type=memory_type.value,
            stored=False,
        )

    memory = Memory(
        content=signal["content"],
        content_hash=chash,
        memory_type=memory_type,
        source=MemorySource.SYSTEM,
        domain=domain,
        tags=tags,
        importance=importance,
        confidence=signal.get("confidence", 0.5),
        session_id=session_id,
        metadata={"auto_detected": True, "approved": True},
    )

    # Generate embedding and store
    embedding_service = await get_embedding_service()
    embedding = await embedding_service.embed(signal["content"])

    await qdrant.store(memory, embedding)

    # Create graph node — compensating delete on failure
    try:
        neo4j = await get_neo4j_store()
        await neo4j.create_memory_node(memory)
    except Exception as neo4j_err:
        logger.error("neo4j_write_failed_compensating", id=memory.id, error=str(neo4j_err))
        await qdrant.delete(memory.id)
        raise HTTPException(status_code=500, detail="Failed to create graph node")

    logger.info(
        "signal_approved",
        memory_id=memory.id,
        signal_type=signal["signal_type"],
    )

    return ApproveSignalResponse(
        memory_id=memory.id,
        content=signal["content"],
        memory_type=memory_type.value,
        stored=True,
    )


@router.get("/{session_id}/turns")
async def get_turns(session_id: str, count: int = 10):
    """Get stored turns for a session (debug/inspection)."""
    redis = await get_redis_store()

    session = await redis.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    turns = await redis.get_recent_turns(session_id, count=count)

    return {
        "session_id": session_id,
        "turns": turns,
        "count": len(turns),
    }
