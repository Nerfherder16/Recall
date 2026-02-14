"""
Admin endpoints for triggering maintenance operations on-demand.

- POST /admin/consolidate  — merge similar memories
- POST /admin/decay        — apply importance decay
"""

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.core.consolidation import MemoryConsolidator
from src.core.embeddings import get_embedding_service
from src.core.models import MemoryType
from src.storage import get_neo4j_store, get_qdrant_store
from src.workers.decay import DecayWorker

logger = structlog.get_logger()
router = APIRouter()


# =============================================================
# REQUEST / RESPONSE MODELS
# =============================================================


class ConsolidateRequest(BaseModel):
    domain: str | None = None
    memory_type: str | None = None
    min_cluster_size: int = Field(default=2, ge=2)
    dry_run: bool = False


class ConsolidateResponse(BaseModel):
    clusters_merged: int
    memories_merged: int
    results: list[dict[str, Any]]


class DecayRequest(BaseModel):
    simulate_hours: float = Field(default=0.0, ge=0.0)


class DecayResponse(BaseModel):
    processed: int
    decayed: int
    archived: int
    stable: int


# =============================================================
# ROUTES
# =============================================================


@router.post("/consolidate", response_model=ConsolidateResponse)
async def trigger_consolidation(request: ConsolidateRequest):
    """Trigger memory consolidation on-demand."""
    try:
        qdrant = await get_qdrant_store()
        neo4j = await get_neo4j_store()
        embeddings = await get_embedding_service()

        consolidator = MemoryConsolidator(qdrant, neo4j, embeddings)

        memory_type = MemoryType(request.memory_type) if request.memory_type else None

        results = await consolidator.consolidate(
            memory_type=memory_type,
            domain=request.domain,
            min_cluster_size=request.min_cluster_size,
            dry_run=request.dry_run,
        )

        formatted = []
        memories_merged = 0
        for r in results:
            memories_merged += len(r.source_memories)
            formatted.append({
                "merged_id": r.merged_memory.id,
                "source_ids": r.source_memories,
                "content_preview": r.merged_memory.content[:100],
                "relationships_created": r.relationships_created,
                "memories_superseded": r.memories_superseded,
            })

        return ConsolidateResponse(
            clusters_merged=len(results),
            memories_merged=memories_merged,
            results=formatted,
        )

    except Exception as e:
        logger.error("consolidation_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/decay", response_model=DecayResponse)
async def trigger_decay(request: DecayRequest):
    """Trigger importance decay on-demand, optionally simulating time passage."""
    try:
        qdrant = await get_qdrant_store()
        neo4j = await get_neo4j_store()

        worker = DecayWorker(qdrant, neo4j)
        stats = await worker.run(hours_offset=request.simulate_hours)

        return DecayResponse(**stats)

    except Exception as e:
        logger.error("decay_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
