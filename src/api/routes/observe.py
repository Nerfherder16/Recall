"""
Observation routes — auto-memory from code edits and session snapshots.
"""

import structlog
from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import BaseModel, Field

from src.api.rate_limit import limiter

logger = structlog.get_logger()
router = APIRouter()


# =============================================================
# REQUEST/RESPONSE MODELS
# =============================================================


class FileChangeObservation(BaseModel):
    """Observation from a file Write/Edit."""

    file_path: str = Field(..., max_length=500)
    content: str | None = Field(None, max_length=10000)
    old_string: str | None = Field(None, max_length=5000)
    new_string: str | None = Field(None, max_length=5000)
    tool_name: str = "Write"
    high_value: bool = False


class GitDiffRequest(BaseModel):
    """Observation from a git commit for memory invalidation."""

    commit_hash: str = Field(..., max_length=40)
    changed_files: list[str] = Field(default_factory=list)
    diff_text: str = Field(..., max_length=50000)


class SessionSnapshotRequest(BaseModel):
    """Snapshot of a session for auto-save."""

    session_id: str = Field(..., max_length=200)
    summary: str | None = Field(None, max_length=2000)


# =============================================================
# ROUTES
# =============================================================


@router.post("/file-change")
@limiter.limit("30/minute")
async def observe_file_change(
    request: Request, body: FileChangeObservation, background_tasks: BackgroundTasks
):
    """
    Observe a file change and extract facts in the background.

    Called by the observe-edit.js PostToolUse hook. Fire-and-forget —
    always returns immediately so it doesn't block Claude.
    """
    from src.workers.observer import extract_and_store_observations

    background_tasks.add_task(extract_and_store_observations, body.model_dump())
    logger.debug("observation_queued", file=body.file_path, tool=body.tool_name)
    return {"status": "queued"}


@router.post("/git-diff")
@limiter.limit("10/minute")
async def observe_git_diff(
    request: Request, body: GitDiffRequest, background_tasks: BackgroundTasks
):
    """
    Observe a git commit and check for memory invalidation.

    Called by the git-watch.js PostToolUse hook. Extracts concrete values
    from the diff and searches for permanent/durable memories that may
    be contradicted. Fire-and-forget.
    """
    from src.core.diff_parser import extract_values
    from src.workers.invalidation import check_invalidations

    extracted = extract_values(body.diff_text)

    if extracted:
        background_tasks.add_task(
            check_invalidations,
            commit_hash=body.commit_hash,
            changed_files=body.changed_files,
            extracted_values=extracted,
        )
        logger.info(
            "git_invalidation_queued",
            commit=body.commit_hash,
            values=len(extracted),
            files=len(body.changed_files),
        )

    return {
        "status": "queued" if extracted else "skipped",
        "extracted_values": len(extracted),
    }


@router.post("/session-snapshot")
@limiter.limit("10/minute")
async def session_snapshot(
    request: Request, body: SessionSnapshotRequest, background_tasks: BackgroundTasks
):
    """
    Capture a session snapshot as a memory.

    Called by the session-save.js Stop hook.
    """
    from src.workers.observer import save_session_snapshot

    background_tasks.add_task(save_session_snapshot, body.session_id, body.summary)
    logger.debug("session_snapshot_queued", session_id=body.session_id)
    return {"status": "queued"}
