"""
Operations endpoints: export, import, reconcile.

All mounted under the /admin prefix (inherits auth from main.py).
"""

import json
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse

from src.api.rate_limit import limiter

from src.core import Memory, MemorySource, MemoryType, get_settings
from src.core.embeddings import OllamaUnavailableError, content_hash, get_embedding_service
from src.storage import get_neo4j_store, get_postgres_store, get_qdrant_store

logger = structlog.get_logger()
router = APIRouter()


# =============================================================
# EXPORT
# =============================================================


@router.get("/export")
async def export_memories(
    include_embeddings: bool = Query(default=False),
    include_superseded: bool = Query(default=False),
):
    """
    Export all memories as streaming JSONL.

    Each line: {"memory": {...}, "embedding": [...], "relationships": [...]}
    """
    settings = get_settings()

    async def _generate():
        qdrant = await get_qdrant_store()
        neo4j = await get_neo4j_store()

        points = await qdrant.scroll_all(
            include_superseded=include_superseded,
            with_vectors=include_embeddings,
        )

        for item in points:
            if include_embeddings:
                memory_id, payload, vector = item
            else:
                memory_id, payload = item
                vector = None

            # Get relationships from Neo4j
            try:
                relationships = await neo4j.get_relationships_for_memory(memory_id)
            except Exception:
                relationships = []

            record = {
                "memory": {
                    "id": memory_id,
                    **payload,
                },
                "relationships": relationships,
            }
            if include_embeddings and vector is not None:
                record["embedding"] = vector

            yield json.dumps(record, default=str) + "\n"

    return StreamingResponse(
        _generate(),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": "attachment; filename=recall-export.jsonl",
        },
    )


# =============================================================
# IMPORT
# =============================================================


@router.post("/import")
async def import_memories(
    file: UploadFile,
    conflict: str = Query(default="skip", pattern="^(skip|overwrite)$"),
    regenerate_embeddings: bool = Query(default=False),
):
    """
    Import memories from a JSONL file.

    Each line must have {"memory": {...}} and optionally {"embedding": [...]}.
    """
    if not file.filename or not file.filename.endswith((".jsonl", ".ndjson")):
        raise HTTPException(status_code=400, detail="File must be .jsonl or .ndjson")

    qdrant = await get_qdrant_store()
    neo4j = await get_neo4j_store()
    settings = get_settings()

    imported = 0
    skipped = 0
    errors = 0

    content = await file.read()
    lines = content.decode("utf-8").strip().split("\n")

    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue

        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("import_bad_json", line=line_num)
            errors += 1
            continue

        mem_data = record.get("memory")
        if not mem_data:
            errors += 1
            continue

        memory_id = mem_data.get("id")
        if not memory_id:
            errors += 1
            continue

        # Check for existing
        existing = await qdrant.get(memory_id)
        if existing:
            if conflict == "skip":
                skipped += 1
                continue
            # overwrite: delete first, then re-insert
            await qdrant.delete(memory_id)
            await neo4j.delete_memory(memory_id)

        # Build Memory object
        try:
            memory = Memory(
                id=memory_id,
                content=mem_data.get("content", ""),
                content_hash=mem_data.get("content_hash") or content_hash(mem_data.get("content", "")),
                memory_type=MemoryType(mem_data.get("memory_type", "semantic")),
                source=MemorySource(mem_data.get("source", "system")),
                domain=mem_data.get("domain", "general"),
                tags=mem_data.get("tags", []),
                importance=float(mem_data.get("importance", 0.5)),
                stability=float(mem_data.get("stability", 0.1)),
                confidence=float(mem_data.get("confidence", 0.8)),
                access_count=int(mem_data.get("access_count", 0)),
                session_id=mem_data.get("session_id"),
                superseded_by=mem_data.get("superseded_by"),
                parent_ids=mem_data.get("parent_ids", []),
                metadata=mem_data.get("metadata", {}),
            )
        except Exception as e:
            logger.warning("import_bad_memory", line=line_num, error=str(e))
            errors += 1
            continue

        # Get or regenerate embedding
        embedding = record.get("embedding")
        if regenerate_embeddings or not embedding:
            try:
                emb_service = await get_embedding_service()
                embedding = await emb_service.embed(memory.content)
            except OllamaUnavailableError as e:
                logger.warning("import_embedding_ollama_unavailable", line=line_num, error=str(e))
                errors += 1
                continue
            except Exception as e:
                logger.warning("import_embedding_failed", line=line_num, error=str(e))
                errors += 1
                continue

        # Store in Qdrant
        try:
            await qdrant.store(memory, embedding)
        except Exception as e:
            logger.warning("import_qdrant_failed", line=line_num, error=str(e))
            errors += 1
            continue

        # Create Neo4j node — compensating delete on failure
        try:
            await neo4j.create_memory_node(memory)
        except Exception as e:
            logger.warning("import_neo4j_failed_compensating", line=line_num, error=str(e))
            await qdrant.delete(memory_id)
            errors += 1
            continue

        # Restore relationships
        for rel in record.get("relationships", []):
            try:
                from src.core import Relationship, RelationshipType

                relationship = Relationship(
                    source_id=rel["source_id"],
                    target_id=rel["target_id"],
                    relationship_type=RelationshipType(rel["rel_type"].lower()),
                    strength=float(rel.get("strength", 0.5)),
                )
                await neo4j.create_relationship(relationship)
            except Exception:
                pass  # Best-effort for relationships

        imported += 1

    logger.info("import_complete", imported=imported, skipped=skipped, errors=errors)

    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
    }


# =============================================================
# RECONCILE
# =============================================================


@router.post("/reconcile")
@limiter.limit("10/minute")
async def reconcile_stores(
    request: Request,
    repair: bool = Query(default=False),
):
    """
    Compare Qdrant and Neo4j to find and optionally heal inconsistencies.

    Qdrant is treated as source of truth.
    """
    qdrant = await get_qdrant_store()
    neo4j = await get_neo4j_store()

    # Collect all IDs from both stores
    qdrant_points = await qdrant.scroll_all(include_superseded=True)
    qdrant_ids = {point[0] for point in qdrant_points}
    qdrant_data = {point[0]: point[1] for point in qdrant_points}

    neo4j_ids = await neo4j.get_all_memory_ids()

    # Find discrepancies
    qdrant_orphans = qdrant_ids - neo4j_ids  # In Qdrant but not Neo4j
    neo4j_orphans = neo4j_ids - qdrant_ids  # In Neo4j but not Qdrant
    common_ids = qdrant_ids & neo4j_ids

    # Check importance and superseded mismatches
    importance_mismatches: list[dict[str, Any]] = []
    superseded_mismatches: list[dict[str, Any]] = []

    for memory_id in common_ids:
        neo4j_data = await neo4j.get_memory_data(memory_id)
        if neo4j_data is None:
            continue

        qdrant_payload = qdrant_data[memory_id]
        q_importance = qdrant_payload.get("importance")
        n_importance = neo4j_data.get("importance")

        if q_importance is not None and n_importance is not None:
            if abs(q_importance - n_importance) > 0.001:
                importance_mismatches.append({
                    "id": memory_id,
                    "qdrant": q_importance,
                    "neo4j": n_importance,
                })

        q_superseded = qdrant_payload.get("superseded_by")
        n_superseded = neo4j_data.get("superseded_by")
        if q_superseded != n_superseded:
            superseded_mismatches.append({
                "id": memory_id,
                "qdrant": q_superseded,
                "neo4j": n_superseded,
            })

    repairs_applied = 0

    if repair:
        # Create missing Neo4j nodes for Qdrant orphans
        for memory_id in qdrant_orphans:
            payload = qdrant_data[memory_id]
            try:
                memory = Memory(
                    id=memory_id,
                    content=payload.get("content", ""),
                    content_hash=payload.get("content_hash", ""),
                    memory_type=MemoryType(payload.get("memory_type", "semantic")),
                    source=MemorySource(payload.get("source", "system")),
                    domain=payload.get("domain", "general"),
                    tags=payload.get("tags", []),
                    importance=float(payload.get("importance", 0.5)),
                )
                await neo4j.create_memory_node(memory)
                repairs_applied += 1
            except Exception as e:
                logger.warning("reconcile_repair_failed", id=memory_id, error=str(e))

        # Sync importance mismatches (Qdrant → Neo4j)
        for mismatch in importance_mismatches:
            try:
                await neo4j.update_importance(mismatch["id"], mismatch["qdrant"])
                repairs_applied += 1
            except Exception as e:
                logger.warning("reconcile_importance_sync_failed", id=mismatch["id"], error=str(e))

        # Sync superseded mismatches (Qdrant → Neo4j)
        for mismatch in superseded_mismatches:
            try:
                q_val = mismatch["qdrant"]
                if q_val:
                    await neo4j.mark_superseded(mismatch["id"], q_val)
                # If Qdrant has no superseded_by, clear it in Neo4j
                else:
                    async with neo4j.driver.session() as session:
                        await session.run(
                            "MATCH (m:Memory {id: $id}) REMOVE m.superseded_by",
                            id=mismatch["id"],
                        )
                repairs_applied += 1
            except Exception as e:
                logger.warning("reconcile_superseded_sync_failed", id=mismatch["id"], error=str(e))

    logger.info(
        "reconcile_complete",
        qdrant_orphans=len(qdrant_orphans),
        neo4j_orphans=len(neo4j_orphans),
        importance_mismatches=len(importance_mismatches),
        superseded_mismatches=len(superseded_mismatches),
        repairs=repairs_applied,
    )

    return {
        "qdrant_total": len(qdrant_ids),
        "neo4j_total": len(neo4j_ids),
        "qdrant_orphans": len(qdrant_orphans),
        "neo4j_orphans": len(neo4j_orphans),
        "importance_mismatches": len(importance_mismatches),
        "superseded_mismatches": len(superseded_mismatches),
        "repairs_applied": repairs_applied,
        "details": {
            "qdrant_orphan_ids": sorted(qdrant_orphans)[:50],
            "neo4j_orphan_ids": sorted(neo4j_orphans)[:50],
            "importance_mismatches": importance_mismatches[:50],
            "superseded_mismatches": superseded_mismatches[:50],
        },
    }


# =============================================================
# AUDIT LOG
# =============================================================


@router.get("/audit")
async def get_audit_log(
    memory_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
):
    """Query the audit log with optional filters."""
    pg = await get_postgres_store()
    entries = await pg.get_audit_log(memory_id=memory_id, action=action, limit=limit)
    return {"entries": entries, "count": len(entries)}


# =============================================================
# SESSION HISTORY
# =============================================================


@router.get("/sessions")
async def get_session_history(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Get archived session history."""
    pg = await get_postgres_store()
    sessions = await pg.get_session_history(limit=limit, offset=offset)
    return {"sessions": sessions, "count": len(sessions)}
