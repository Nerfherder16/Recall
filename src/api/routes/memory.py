"""
Memory CRUD routes.
"""

from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from src.core import (
    Memory,
    MemorySource,
    MemoryType,
    Relationship,
    RelationshipType,
    get_embedding_service,
)
from src.core.embeddings import OllamaUnavailableError, content_hash
from src.storage import get_neo4j_store, get_postgres_store, get_qdrant_store, get_redis_store

logger = structlog.get_logger()
router = APIRouter()


# =============================================================
# REQUEST/RESPONSE MODELS
# =============================================================


class StoreMemoryRequest(BaseModel):
    """Request to store a new memory."""

    content: str = Field(..., min_length=1, max_length=50000)
    memory_type: MemoryType = MemoryType.SEMANTIC
    source: MemorySource = MemorySource.USER
    domain: str = Field(default="general", max_length=200)
    tags: list[str] = Field(default=[], max_length=50)
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
async def store_memory(request: StoreMemoryRequest, background_tasks: BackgroundTasks):
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

        # Dedup check: reject if identical content already exists
        qdrant = await get_qdrant_store()
        existing_id = await qdrant.find_by_content_hash(memory.content_hash)
        if existing_id:
            return StoreMemoryResponse(
                id=existing_id,
                content_hash=memory.content_hash,
                created=False,
                message="Duplicate memory — identical content already stored",
            )

        # Generate embedding
        embedding_service = await get_embedding_service()
        embedding = await embedding_service.embed(request.content)

        # Store in Qdrant
        await qdrant.store(memory, embedding)

        # Create graph node — compensating delete on failure
        try:
            neo4j = await get_neo4j_store()
            await neo4j.create_memory_node(memory)
        except Exception as neo4j_err:
            logger.error("neo4j_write_failed_compensating", id=memory.id, error=str(neo4j_err))
            await qdrant.delete(memory.id)
            raise

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

        # Audit log (fire-and-forget)
        pg = await get_postgres_store()
        await pg.log_audit(
            "create", memory.id, actor="user",
            session_id=request.session_id,
            details={"type": memory.memory_type.value, "domain": memory.domain},
        )

        # Trigger sub-embedding extraction in background
        from src.workers.fact_extractor import extract_facts_for_memory

        background_tasks.add_task(
            extract_facts_for_memory, memory.id, request.content, request.domain
        )

        return StoreMemoryResponse(
            id=memory.id,
            content_hash=memory.content_hash,
            created=True,
            message="Memory stored successfully",
        )

    except OllamaUnavailableError:
        raise HTTPException(status_code=503, detail="Embedding service unavailable")
    except Exception as e:
        logger.error("store_memory_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{memory_id}")
async def delete_memory(memory_id: str):
    """Delete a memory."""
    try:
        qdrant = await get_qdrant_store()
        neo4j = await get_neo4j_store()

        # Delete from both stores + facts sub-embeddings
        await qdrant.delete(memory_id)
        await neo4j.delete_memory(memory_id)
        try:
            await qdrant.delete_facts_for_memory(memory_id)
        except Exception:
            pass  # Facts collection might not exist yet

        logger.info("deleted_memory", id=memory_id)

        # Audit log (fire-and-forget)
        pg = await get_postgres_store()
        await pg.log_audit("delete", memory_id, actor="user")

        return {"deleted": True, "id": memory_id}

    except Exception as e:
        err = str(e).lower()
        if "wrong input" in err or "uuid" in err or "bad request" in err:
            raise HTTPException(status_code=404, detail="Memory not found")
        logger.error("delete_memory_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{memory_id}/related")
async def get_related_memories(
    memory_id: str,
    max_depth: int = Query(default=2, ge=1, le=10),
    limit: int = Query(default=10, ge=1, le=100),
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
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================
# BATCH OPERATIONS
# =============================================================


class BatchStoreRequest(BaseModel):
    """Request to store multiple memories at once."""

    memories: list[StoreMemoryRequest] = Field(..., min_length=1, max_length=50)


class BatchStoreResult(BaseModel):
    """Result for a single item in a batch store."""

    id: str
    content_hash: str
    created: bool
    message: str


class BatchStoreResponse(BaseModel):
    """Response from batch store."""

    results: list[BatchStoreResult]
    created: int
    duplicates: int
    errors: int


class BatchDeleteRequest(BaseModel):
    """Request to delete multiple memories at once."""

    ids: list[str] = Field(..., min_length=1, max_length=100)


class BatchDeleteResponse(BaseModel):
    """Response from batch delete."""

    deleted: int
    not_found: int
    errors: int


@router.post("/batch/store", response_model=BatchStoreResponse)
async def batch_store_memories(request: BatchStoreRequest):
    """
    Store multiple memories in one request.

    Each item goes through the same dedup + embed + dual-write pipeline
    as single store. Max 50 items per request.
    """
    try:
        qdrant = await get_qdrant_store()
        neo4j = await get_neo4j_store()
        embedding_service = await get_embedding_service()
        pg = await get_postgres_store()

        results = []
        created = 0
        duplicates = 0
        errors = 0

        for item in request.memories:
            try:
                memory = Memory(
                    content=item.content,
                    content_hash=content_hash(item.content),
                    memory_type=item.memory_type,
                    source=item.source,
                    domain=item.domain,
                    tags=item.tags,
                    importance=item.importance,
                    confidence=item.confidence,
                    session_id=item.session_id,
                    metadata=item.metadata,
                )

                # Dedup check
                existing_id = await qdrant.find_by_content_hash(memory.content_hash)
                if existing_id:
                    results.append(BatchStoreResult(
                        id=existing_id,
                        content_hash=memory.content_hash,
                        created=False,
                        message="Duplicate",
                    ))
                    duplicates += 1
                    continue

                # Embed
                embedding = await embedding_service.embed(item.content)

                # Store in Qdrant
                await qdrant.store(memory, embedding)

                # Create graph node — compensating delete on failure
                try:
                    await neo4j.create_memory_node(memory)
                except Exception as neo4j_err:
                    logger.error("batch_neo4j_failed_compensating", id=memory.id, error=str(neo4j_err))
                    await qdrant.delete(memory.id)
                    results.append(BatchStoreResult(
                        id=memory.id,
                        content_hash=memory.content_hash,
                        created=False,
                        message=f"Neo4j error",
                    ))
                    errors += 1
                    continue

                # Add to working memory if session provided
                if item.session_id:
                    redis = await get_redis_store()
                    await redis.add_to_working_memory(item.session_id, memory.id)

                # Audit (fire-and-forget)
                await pg.log_audit(
                    "create", memory.id, actor="user",
                    session_id=item.session_id,
                    details={"type": memory.memory_type.value, "domain": memory.domain, "batch": True},
                )

                results.append(BatchStoreResult(
                    id=memory.id,
                    content_hash=memory.content_hash,
                    created=True,
                    message="Stored",
                ))
                created += 1

            except OllamaUnavailableError:
                raise  # Propagate to outer handler for 503
            except Exception as e:
                logger.error("batch_store_item_error", error=str(e))
                results.append(BatchStoreResult(
                    id="",
                    content_hash="",
                    created=False,
                    message="Error",
                ))
                errors += 1

        return BatchStoreResponse(
            results=results,
            created=created,
            duplicates=duplicates,
            errors=errors,
        )

    except OllamaUnavailableError:
        raise HTTPException(status_code=503, detail="Embedding service unavailable")
    except Exception as e:
        logger.error("batch_store_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/batch/delete", response_model=BatchDeleteResponse)
async def batch_delete_memories(request: BatchDeleteRequest):
    """
    Delete multiple memories in one request.

    Each item is deleted from Qdrant + Neo4j and audited. Max 100 IDs.
    """
    try:
        qdrant = await get_qdrant_store()
        neo4j = await get_neo4j_store()
        pg = await get_postgres_store()

        deleted = 0
        not_found = 0
        errors = 0

        for memory_id in request.ids:
            try:
                # Check existence
                existing = await qdrant.get(memory_id)
                if not existing:
                    not_found += 1
                    continue

                await qdrant.delete(memory_id)
                await neo4j.delete_memory(memory_id)

                await pg.log_audit("delete", memory_id, actor="user", details={"batch": True})
                deleted += 1

            except Exception as e:
                err = str(e).lower()
                if "wrong input" in err or "uuid" in err or "bad request" in err:
                    not_found += 1
                else:
                    logger.error("batch_delete_item_error", id=memory_id, error=str(e))
                    errors += 1

        return BatchDeleteResponse(
            deleted=deleted,
            not_found=not_found,
            errors=errors,
        )

    except Exception as e:
        logger.error("batch_delete_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")
