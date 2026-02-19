"""
Git-aware memory invalidation worker.

Searches permanent/durable memories for content matching extracted
values from git diffs. Flags matches with invalidation_flag payload
and writes audit log entries.
"""

import re
from datetime import datetime

import structlog

logger = structlog.get_logger()


async def check_invalidations(
    commit_hash: str,
    changed_files: list[str],
    extracted_values: list[dict],
) -> dict:
    """
    Search for permanent/durable memories that may be invalidated by a git commit.

    Scrolls Qdrant for durable/permanent memories, checks if their content
    matches any extracted value (word-boundary match), and flags matches.

    Returns: {"flagged_count": int, "scanned_count": int}
    """
    from qdrant_client.models import FieldCondition, Filter, MatchAny

    from src.storage import get_postgres_store, get_qdrant_store

    qdrant = await get_qdrant_store()
    postgres = await get_postgres_store()

    # Build the set of values to search for
    search_values = [v["value"] for v in extracted_values]
    if not search_values:
        return {"flagged_count": 0, "scanned_count": 0}

    # Scroll only permanent/durable memories (skip ephemeral/superseded)
    all_points = []
    offset = None
    while True:
        points, next_offset = await qdrant.client.scroll(
            collection_name=qdrant.collection,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="durability",
                        match=MatchAny(
                            any=["permanent", "durable"],
                        ),
                    ),
                ],
            ),
            limit=100,
            offset=offset,
            with_payload=True,
        )
        all_points.extend(points)
        if next_offset is None or not points:
            break
        offset = next_offset

    flagged_count = 0

    for point in all_points:
        payload = point.payload or {}
        content = payload.get("content", "")

        # Skip superseded memories
        if payload.get("superseded_by"):
            continue

        # Word-boundary match to avoid false positives
        matched_values = [
            v
            for v in search_values
            if re.search(
                r"\b" + re.escape(v) + r"\b",
                content,
                re.IGNORECASE,
            )
        ]
        if not matched_values:
            continue

        # Flag the memory
        flag = {
            "reason": (f"Values {matched_values[:3]} found in commit {commit_hash[:7]}"),
            "commit_hash": commit_hash,
            "changed_files": changed_files[:5],
            "matched_values": matched_values[:5],
            "flagged_at": datetime.utcnow().isoformat(),
        }

        await qdrant.client.set_payload(
            collection_name=qdrant.collection,
            payload={"invalidation_flag": flag},
            points=[str(point.id)],
        )

        # Audit log
        await postgres.log_audit(
            action="memory_invalidation_flagged",
            memory_id=str(point.id),
            actor="git-watch",
            details={
                "commit_hash": commit_hash,
                "matched_values": matched_values[:5],
                "changed_files": changed_files[:5],
            },
        )

        flagged_count += 1
        logger.info(
            "memory_flagged_stale",
            memory_id=str(point.id),
            commit=commit_hash[:7],
            matched=matched_values[:3],
        )

    logger.info(
        "invalidation_check_complete",
        commit=commit_hash[:7],
        scanned=len(all_points),
        flagged=flagged_count,
    )

    return {"flagged_count": flagged_count, "scanned_count": len(all_points)}
