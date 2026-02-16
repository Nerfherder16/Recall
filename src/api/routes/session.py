"""
Session management routes.
"""

from datetime import datetime

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from src.core import Session
from src.storage import get_postgres_store, get_redis_store

logger = structlog.get_logger()
router = APIRouter()


# =============================================================
# REQUEST/RESPONSE MODELS
# =============================================================


class StartSessionRequest(BaseModel):
    """Request to start a new session."""

    session_id: str | None = None  # Optional custom ID
    working_directory: str | None = None
    current_task: str | None = None


class StartSessionResponse(BaseModel):
    """Response after starting a session."""

    session_id: str
    started_at: str


class EndSessionRequest(BaseModel):
    """Request to end a session."""

    session_id: str
    trigger_consolidation: bool = True


class SessionStatusResponse(BaseModel):
    """Session status response."""

    session_id: str
    started_at: str
    ended_at: str | None
    working_directory: str | None
    current_task: str | None
    memories_created: int
    memories_retrieved: int
    signals_detected: int
    working_memory_count: int


# =============================================================
# ROUTES
# =============================================================


@router.post("/start", response_model=StartSessionResponse)
async def start_session(request: StartSessionRequest):
    """
    Start a new memory session.

    Sessions provide:
    - Working memory scope
    - Context for memory operations
    - Consolidation boundary
    """
    try:
        session = Session(
            working_directory=request.working_directory,
            current_task=request.current_task,
        )

        if request.session_id:
            session.id = request.session_id

        redis = await get_redis_store()
        await redis.create_session(session)

        logger.info(
            "session_started",
            id=session.id,
            directory=session.working_directory,
        )

        return StartSessionResponse(
            session_id=session.id,
            started_at=session.started_at.isoformat(),
        )

    except Exception as e:
        logger.error("start_session_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/end")
async def end_session(request: EndSessionRequest, background_tasks: BackgroundTasks):
    """
    End a session.

    Cleans up pending signals and optionally triggers consolidation
    of session memories via BackgroundTasks.
    """
    try:
        redis = await get_redis_store()

        # Check session exists
        session_data = await redis.get_session(request.session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="Session not found")

        # Mark as ended
        await redis.end_session(request.session_id)

        # Get working memory for consolidation
        working_memory = await redis.get_working_memory(request.session_id)

        # Clean up pending signals (no longer reviewable after session ends)
        await redis.clear_pending_signals(request.session_id)

        # Trigger consolidation as a BackgroundTask (replaces dead event stream)
        consolidation_queued = False
        if request.trigger_consolidation and len(working_memory) >= 2:
            background_tasks.add_task(
                _run_session_end_consolidation, request.session_id
            )
            consolidation_queued = True

        # Archive session to Postgres (fire-and-forget)
        # Re-fetch session data to get ended_at timestamp
        updated_session = await redis.get_session(request.session_id)
        if updated_session:
            turns_count = len(await redis.get_recent_turns(request.session_id, count=9999))
            pg = await get_postgres_store()
            await pg.archive_session({
                **updated_session,
                "turns_count": turns_count,
            })

        logger.info(
            "session_ended",
            id=request.session_id,
            memories=len(working_memory),
            consolidation_queued=consolidation_queued,
        )

        return {
            "session_id": request.session_id,
            "ended": True,
            "memories_in_session": len(working_memory),
            "consolidation_queued": consolidation_queued,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("end_session_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


async def _run_session_end_consolidation(session_id: str):
    """Background task: consolidate memories from an ended session."""
    try:
        from src.core.consolidation import create_consolidator

        consolidator = await create_consolidator()
        results = await consolidator.consolidate()

        logger.info(
            "session_end_consolidation_complete",
            session_id=session_id,
            clusters_merged=len(results),
        )
    except Exception as e:
        logger.error(
            "session_end_consolidation_failed",
            session_id=session_id,
            error=str(e),
            error_type=type(e).__name__,
        )


@router.get("/{session_id}", response_model=SessionStatusResponse)
async def get_session_status(session_id: str):
    """Get the status of a session."""
    try:
        redis = await get_redis_store()

        session_data = await redis.get_session(session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="Session not found")

        working_memory = await redis.get_working_memory(session_id)

        return SessionStatusResponse(
            session_id=session_id,
            started_at=session_data.get("started_at", ""),
            ended_at=session_data.get("ended_at"),
            working_directory=session_data.get("working_directory") or None,
            current_task=session_data.get("current_task") or None,
            memories_created=int(session_data.get("memories_created", 0)),
            memories_retrieved=int(session_data.get("memories_retrieved", 0)),
            signals_detected=int(session_data.get("signals_detected", 0)),
            working_memory_count=len(working_memory),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_session_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{session_id}/working-memory")
async def get_working_memory(session_id: str):
    """Get the working memory contents for a session."""
    try:
        redis = await get_redis_store()

        session_data = await redis.get_session(session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="Session not found")

        working_memory_ids = await redis.get_working_memory(session_id)

        # Fetch memory contents
        from src.storage import get_qdrant_store

        qdrant = await get_qdrant_store()
        memories = []

        for memory_id in working_memory_ids:
            result = await qdrant.get(memory_id)
            if result:
                _, payload = result
                memories.append({
                    "id": memory_id,
                    "content": payload.get("content", ""),
                    "type": payload.get("memory_type", "semantic"),
                    "importance": payload.get("importance", 0.5),
                })

        return {
            "session_id": session_id,
            "count": len(memories),
            "memories": memories,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_working_memory_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{session_id}/context")
async def update_session_context(
    session_id: str,
    working_directory: str | None = None,
    current_task: str | None = None,
    active_files: list[str] | None = None,
):
    """Update the context for a session."""
    try:
        redis = await get_redis_store()

        session_data = await redis.get_session(session_id)
        if not session_data:
            raise HTTPException(status_code=404, detail="Session not found")

        updates = {}
        if working_directory is not None:
            updates["working_directory"] = working_directory
        if current_task is not None:
            updates["current_task"] = current_task
        if active_files is not None:
            updates["active_files"] = ",".join(active_files)

        if updates:
            await redis.update_session(session_id, updates)

        return {"updated": True, "session_id": session_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("update_context_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")
