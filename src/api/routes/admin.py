"""
Admin endpoints for triggering maintenance operations on-demand.

- POST /admin/consolidate  — merge similar memories
- POST /admin/decay        — apply importance decay
- GET  /admin/ollama       — proxy Ollama model/status info
"""

from typing import Any

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.api.rate_limit import limiter
from src.core.config import get_settings

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
@limiter.limit("10/minute")
async def trigger_consolidation(request: Request, body: ConsolidateRequest):
    """Trigger memory consolidation on-demand."""
    try:
        qdrant = await get_qdrant_store()
        neo4j = await get_neo4j_store()
        embeddings = await get_embedding_service()

        consolidator = MemoryConsolidator(qdrant, neo4j, embeddings)

        memory_type = MemoryType(body.memory_type) if body.memory_type else None

        results = await consolidator.consolidate(
            memory_type=memory_type,
            domain=body.domain,
            min_cluster_size=body.min_cluster_size,
            dry_run=body.dry_run,
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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/decay", response_model=DecayResponse)
@limiter.limit("10/minute")
async def trigger_decay(request: Request, body: DecayRequest):
    """Trigger importance decay on-demand, optionally simulating time passage."""
    try:
        qdrant = await get_qdrant_store()
        neo4j = await get_neo4j_store()

        worker = DecayWorker(qdrant, neo4j)
        stats = await worker.run(hours_offset=body.simulate_hours)

        return DecayResponse(**stats)

    except Exception as e:
        logger.error("decay_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/ollama")
async def ollama_info(request: Request):
    """Proxy Ollama model info, running models, and version."""
    settings = get_settings()
    host = settings.ollama_host
    result: dict[str, Any] = {}

    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            r = await client.get(f"{host}/api/version")
            result["version"] = r.json().get("version", "unknown") if r.status_code == 200 else "error"
        except Exception:
            result["version"] = "unreachable"

        try:
            r = await client.get(f"{host}/api/tags")
            if r.status_code == 200:
                result["models"] = [
                    {
                        "name": m.get("name"),
                        "parameter_size": m.get("details", {}).get("parameter_size"),
                        "quantization": m.get("details", {}).get("quantization_level"),
                        "family": m.get("details", {}).get("family"),
                        "size_bytes": m.get("size", 0),
                    }
                    for m in r.json().get("models", [])
                ]
            else:
                result["models"] = []
        except Exception:
            result["models"] = []

        try:
            r = await client.get(f"{host}/api/ps")
            if r.status_code == 200:
                result["running"] = [
                    {
                        "name": m.get("name"),
                        "size_bytes": m.get("size", 0),
                        "size_vram": m.get("size_vram", 0),
                        "context_length": m.get("context_length", 0),
                        "expires_at": m.get("expires_at"),
                    }
                    for m in r.json().get("models", [])
                ]
            else:
                result["running"] = []
        except Exception:
            result["running"] = []

    return result
