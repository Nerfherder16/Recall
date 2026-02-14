"""
Memory CRUD routes.
"""

from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.core import (
    Memory,
    MemorySource,
    MemoryType,
    Relationship,
    RelationshipType,
    get_embedding_service,
)
from src.core.embeddings import content_hash
from src.storage import get_neo4j_store, get_qdrant_store, get_redis_store

logger = structlog.get_logger()
router = APIRouter()


# =============================================================
# REQUEST/RESPONSE MODELS
# =============================================================


class StoreMemoryRequest(BaseModel):
    """Request to store a new memory."""

    content: str
    memory_type: MemoryType = MemoryType.SEMANTIC
    source: MemorySource = MemorySource.USER
    domain: str = "general"
    tags: list[str] = []
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    session_id: str | None = None
    metadata: dict[str, Any] = {}


class StoreMemoryResponse(BaseModel):
    """Response after storing a memory."""

    id: str
    content_hash: str
    created: bool
    message: str


class MemoryResponse(BaseModel):
    """Response with memory details."""

    id: str
    content: str
    memory_type: str
    source: str
    domain: str
    tags: list[str]
    importance: float
    stability: float
    confidence: float
    access_count: int
    created_at: str
    last_accessed: str


class CreateRelationshipRequest(BaseModel):
    """Request to create a relationship between memories."""

    source_id: str
    target_id: str
    relationship_type: RelationshipType
    strength: float = 0.5
    bidirectional: bool = False


# =============================================================
# ROUTES
# =============================================================


@router.post("/store", response_model=StoreMemoryResponse)
async def store_memory(request: StoreMemoryRequest):
    """
    Store a new memory.

    The memory will be:
    - Embedded using BGE-large
    - Stored in Qdrant (vector) and Neo4j (graph node)
    - Added to working memory if session_id provided
    """
    try:
        # Create memory object
        memory = Memory(
            content=request.content,
            content_hash=content_hash(request.content),
            memory_type=request.memory_type,
            source=request.source,
            domain=request.domain,
            tags=request.tags,
            importance=request.importance,
            confidence=request.confidence,
            session_id=request.session_id,
            metadata=request.metadata,
        )

        # Generate embedding
        embedding_service = await get_embedding_service()
        embedding = await embedding_service.embed(request.content)

        # Store in Qdrant
        qdrant = await get_qdrant_store()
        await qdrant.store(memory, embedding)

        # Create graph node
        neo4j = await get_neo4j_store()
        await neo4j.create_memory_node(memory)

        # Add to working memory if session provided
        if request.session_id:
            redis = await get_redis_store()
            await redis.add_to_working_memory(request.session_id, memory.id)

        logger.info(
            "stored_memory",
            id=memory.id,
            type=memory.memory_type.value,
            domain=memory.domain,
        )

        return StoreMemoryResponse(
            id=memory.id,
            content_hash=memory.content_hash,
            created=True,
            message="Memory stored successfully",
        )

    except Exception as e:
        logger.error("store_memory_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory(memory_id: str):
    """Get a memory by ID."""
    try:
        qdrant = await get_qdrant_store()
        result = await qdrant.get(memory_id)

        if not result:
            raise HTTPException(status_code=404, detail="Memory not found")

        embedding, payload = result

        return MemoryResponse(
            id=memory_id,
            content=payload.get("content", ""),
            memory_type=payload.get("memory_type", "semantic"),
            source=payload.get("source", "system"),
            domain=payload.get("domain", "general"),
            tags=payload.get("tags", []),
            importance=payload.get("importance", 0.5),
            stability=payload.get("stability", 0.1),
            confidence=payload.get("confidence", 0.8),
            access_count=payload.get("access_count", 0),
            created_at=payload.get("created_at", ""),
            last_accessed=payload.get("last_accessed", ""),
        )

    except HTTPException:
        raise
    except Exception as e:
        # Qdrant rejects non-UUID IDs with a client error — surface as 404
        err = str(e).lower()
        if "wrong input" in err or "uuid" in err or "bad request" in err:
            raise HTTPException(status_code=404, detail="Memory not found")
        logger.error("get_memory_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{memory_id}")
async def delete_memory(memory_id: str):
    """Delete a memory."""
    try:
        qdrant = await get_qdrant_store()
        neo4j = await get_neo4j_store()

        # Delete from both stores
        await qdrant.delete(memory_id)
        await neo4j.delete_memory(memory_id)

        logger.info("deleted_memory", id=memory_id)

        return {"deleted": True, "id": memory_id}

    except Exception as e:
        err = str(e).lower()
        if "wrong input" in err or "uuid" in err or "bad request" in err:
            raise HTTPException(status_code=404, detail="Memory not found")
        logger.error("delete_memory_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/relationship")
async def create_relationship(request: CreateRelationshipRequest):
    """Create a relationship between two memories."""
    try:
        relationship = Relationship(
            source_id=request.source_id,
            target_id=request.target_id,
            relationship_type=request.relationship_type,
            strength=request.strength,
            bidirectional=request.bidirectional,
        )

        neo4j = await get_neo4j_store()
        await neo4j.create_relationship(relationship)

        logger.info(
            "created_relationship",
            source=request.source_id,
            target=request.target_id,
            type=request.relationship_type.value,
        )

        return {
            "created": True,
            "relationship_id": relationship.id,
        }

    except Exception as e:
        logger.error("create_relationship_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{memory_id}/related")
async def get_related_memories(
    memory_id: str,
    max_depth: int = 2,
    limit: int = 10,
):
    """Get memories related to a given memory via graph traversal."""
    try:
        neo4j = await get_neo4j_store()
        related = await neo4j.find_related(
            memory_id=memory_id,
            max_depth=max_depth,
            limit=limit,
        )

        return {
            "source_id": memory_id,
            "related": related,
        }

    except Exception as e:
        logger.error("get_related_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
