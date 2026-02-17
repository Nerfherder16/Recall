"""
Memory CRUD routes.
"""

from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.auth import require_auth
from src.core import (
    Durability,
    Memory,
    MemorySource,
    MemoryType,
    Relationship,
    RelationshipType,
    User,
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
    durability: str | None = Field(default=None, pattern="^(ephemeral|durable|permanent)$")
    session_id: str | None = None
    metadata: dict[str, Any] = {}


class StoreMemoryResponse(BaseModel):
    """Response after storing a memory."""

    id: str
    content_hash: str
    created: bool
    message: str
    durability: str | None = None
    initial_importance: float | None = None


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
    stored_by: str | None = None
    pinned: bool = False
    durability: str | None = None
    initial_importance: float | None = None


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
async def store_memory(
    request: StoreMemoryRequest,
    background_tasks: BackgroundTasks,
    user: User | None = Depends(require_auth),
):
    """
    Store a new memory.

    The memory will be:
    - Embedded using BGE-large
    - Stored in Qdrant (vector) and Neo4j (graph node)
    - Added to working memory if session_id provided
    """
    try:
        # Resolve durability
        durability = Durability(request.durability) if request.durability else None

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
            user_id=user.id if user else None,
            username=user.username if user else None,
            durability=durability,
            initial_importance=request.importance,
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
                durability=request.durability,
                initial_importance=request.importance,
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
            "create", memory.id,
            actor=user.username if user else "user",
            session_id=request.session_id,
            details={
                "type": memory.memory_type.value,
                "domain": memory.domain,
                "importance": request.importance,
                "durability": request.durability,
            },
            user_id=user.id if user else None,
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
            durability=request.durability,
            initial_importance=memory.initial_importance,
        )

    except OllamaUnavailableError:
        raise HTTPException(status_code=503, detail="Embedding service unavailable")
    except Exception as e:
        logger.error("store_memory_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================
# ANTI-PATTERN ENDPOINTS (must be before /{memory_id} catch-all)
# =============================================================


class CreateAntiPatternRequest(BaseModel):
    """Request to create an anti-pattern."""

    pattern: str = Field(..., min_length=1, max_length=5000)
    warning: str = Field(..., min_length=1, max_length=5000)
    alternative: str | None = None
    severity: str = Field(default="warning")
    domain: str = Field(default="general", max_length=200)
    tags: list[str] = Field(default=[], max_length=50)


class AntiPatternResponse(BaseModel):
    """Response with anti-pattern details."""

    id: str
    pattern: str
    warning: str
    alternative: str | None
    severity: str
    domain: str
    tags: list[str]
    times_triggered: int
    created_at: str


@router.post("/anti-pattern", response_model=AntiPatternResponse)
async def create_anti_pattern(
    request: CreateAntiPatternRequest,
    user: User | None = Depends(require_auth),
):
    """Create an anti-pattern — a warning about something to avoid."""
    try:
        from src.core.models import AntiPattern

        anti_pattern = AntiPattern(
            pattern=request.pattern,
            warning=request.warning,
            alternative=request.alternative,
            severity=request.severity,
            domain=request.domain,
            tags=request.tags,
            user_id=user.id if user else None,
            username=user.username if user else None,
        )

        embedding_service = await get_embedding_service()
        embedding = await embedding_service.embed(request.pattern)

        qdrant = await get_qdrant_store()
        await qdrant.store_anti_pattern(anti_pattern, embedding)

        pg = await get_postgres_store()
        await pg.log_audit(
            "create_anti_pattern", anti_pattern.id,
            actor=user.username if user else "user",
            user_id=user.id if user else None,
            details={"severity": request.severity, "domain": request.domain},
        )

        return AntiPatternResponse(
            id=anti_pattern.id,
            pattern=anti_pattern.pattern,
            warning=anti_pattern.warning,
            alternative=anti_pattern.alternative,
            severity=anti_pattern.severity,
            domain=anti_pattern.domain,
            tags=anti_pattern.tags,
            times_triggered=0,
            created_at=anti_pattern.created_at.isoformat(),
        )

    except OllamaUnavailableError:
        raise HTTPException(status_code=503, detail="Embedding service unavailable")
    except Exception as e:
        logger.error("create_anti_pattern_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/anti-patterns")
async def list_anti_patterns(domain: str | None = Query(default=None)):
    """List all anti-patterns, optionally filtered by domain."""
    try:
        qdrant = await get_qdrant_store()
        results = await qdrant.scroll_anti_patterns(domain=domain)

        return {
            "anti_patterns": [
                AntiPatternResponse(
                    id=ap_id,
                    pattern=payload.get("pattern", ""),
                    warning=payload.get("warning", ""),
                    alternative=payload.get("alternative"),
                    severity=payload.get("severity", "warning"),
                    domain=payload.get("domain", "general"),
                    tags=payload.get("tags", []),
                    times_triggered=payload.get("times_triggered", 0),
                    created_at=payload.get("created_at", ""),
                ).model_dump()
                for ap_id, payload in results
            ],
            "total": len(results),
        }

    except Exception as e:
        logger.error("list_anti_patterns_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/anti-pattern/{anti_pattern_id}", response_model=AntiPatternResponse)
async def get_anti_pattern(anti_pattern_id: str):
    """Get an anti-pattern by ID."""
    try:
        qdrant = await get_qdrant_store()
        result = await qdrant.get_anti_pattern(anti_pattern_id)

        if not result:
            raise HTTPException(status_code=404, detail="Anti-pattern not found")

        _, payload = result
        return AntiPatternResponse(
            id=anti_pattern_id,
            pattern=payload.get("pattern", ""),
            warning=payload.get("warning", ""),
            alternative=payload.get("alternative"),
            severity=payload.get("severity", "warning"),
            domain=payload.get("domain", "general"),
            tags=payload.get("tags", []),
            times_triggered=payload.get("times_triggered", 0),
            created_at=payload.get("created_at", ""),
        )

    except HTTPException:
        raise
    except Exception as e:
        err = str(e).lower()
        if "wrong input" in err or "uuid" in err or "bad request" in err:
            raise HTTPException(status_code=404, detail="Anti-pattern not found")
        logger.error("get_anti_pattern_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/anti-pattern/{anti_pattern_id}")
async def delete_anti_pattern(anti_pattern_id: str, user: User | None = Depends(require_auth)):
    """Delete an anti-pattern."""
    try:
        qdrant = await get_qdrant_store()
        result = await qdrant.get_anti_pattern(anti_pattern_id)
        if not result:
            raise HTTPException(status_code=404, detail="Anti-pattern not found")

        await qdrant.delete_anti_pattern(anti_pattern_id)

        pg = await get_postgres_store()
        await pg.log_audit(
            "delete_anti_pattern", anti_pattern_id,
            actor=user.username if user else "user",
            user_id=user.id if user else None,
        )

        return {"deleted": True, "id": anti_pattern_id}

    except HTTPException:
        raise
    except Exception as e:
        err = str(e).lower()
        if "wrong input" in err or "uuid" in err or "bad request" in err:
            raise HTTPException(status_code=404, detail="Anti-pattern not found")
        logger.error("delete_anti_pattern_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================
# FEEDBACK LOOP (must be before /{memory_id} catch-all)
# =============================================================


class FeedbackRequest(BaseModel):
    """Request to submit retrieval feedback."""

    injected_ids: list[str] = Field(..., min_length=1, max_length=200)
    assistant_text: str = Field(..., min_length=50, max_length=15000)


class FeedbackResponse(BaseModel):
    """Response from feedback processing."""

    processed: int
    useful: int
    not_useful: int
    not_found: int
    relationships_strengthened: int = 0


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(request: FeedbackRequest, user: User | None = Depends(require_auth)):
    """
    Submit retrieval feedback.

    Compares assistant output embedding against each injected memory's embedding.
    Useful memories get importance/stability boosts; not-useful get small penalties.
    """
    try:
        from src.core.retrieval import cosine_similarity

        embedding_service = await get_embedding_service()
        assistant_embedding = await embedding_service.embed(request.assistant_text)

        qdrant = await get_qdrant_store()
        neo4j = await get_neo4j_store()
        pg = await get_postgres_store()

        processed = 0
        useful = 0
        not_useful = 0
        not_found = 0
        useful_memory_ids: list[str] = []

        for memory_id in request.injected_ids:
            result = await qdrant.get(memory_id)
            if not result:
                not_found += 1
                continue

            memory_embedding, payload = result
            processed += 1

            similarity = cosine_similarity(assistant_embedding, memory_embedding)
            old_importance = payload.get("importance", 0.5)
            old_stability = payload.get("stability", 0.1)

            if similarity > 0.35:
                # Useful — boost importance and stability
                new_importance = min(1.0, old_importance + 0.05)
                new_stability = min(1.0, old_stability + 0.03)
                useful += 1
                is_useful = True
                useful_memory_ids.append(memory_id)
            else:
                # Not useful — small penalty
                new_importance = max(0.01, old_importance - 0.02)
                new_stability = max(0.0, old_stability - 0.01)
                not_useful += 1
                is_useful = False

            # Update Qdrant
            await qdrant.update_importance(memory_id, new_importance)
            await qdrant.update_stability(memory_id, new_stability)

            # Update Neo4j
            await neo4j.update_importance(memory_id, new_importance)
            await neo4j.update_stability(memory_id, new_stability)

            # Audit log
            await pg.log_audit(
                "feedback", memory_id,
                actor=user.username if user else "system",
                user_id=user.id if user else None,
                details={
                    "useful": is_useful,
                    "similarity": round(similarity, 4),
                    "old_importance": round(old_importance, 4),
                    "new_importance": round(new_importance, 4),
                    "old_stability": round(old_stability, 4),
                    "new_stability": round(new_stability, 4),
                },
            )

        # Strengthen edges between co-retrieved useful memories
        relationships_strengthened = 0
        if len(useful_memory_ids) >= 2:
            from itertools import combinations
            for id_a, id_b in combinations(useful_memory_ids, 2):
                try:
                    await neo4j.strengthen_relationship(id_a, id_b)
                    relationships_strengthened += 1
                except Exception:
                    pass

        logger.info(
            "feedback_processed",
            processed=processed,
            useful=useful,
            not_useful=not_useful,
            not_found=not_found,
            relationships_strengthened=relationships_strengthened,
        )

        return FeedbackResponse(
            processed=processed,
            useful=useful,
            not_useful=not_useful,
            not_found=not_found,
            relationships_strengthened=relationships_strengthened,
        )

    except OllamaUnavailableError:
        raise HTTPException(status_code=503, detail="Embedding service unavailable")
    except Exception as e:
        logger.error("feedback_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================
# DURABILITY ENDPOINT (must be before /{memory_id} catch-all)
# =============================================================


class UpdateDurabilityRequest(BaseModel):
    """Request to update memory durability."""

    durability: str = Field(..., pattern="^(ephemeral|durable|permanent)$")


@router.put("/{memory_id}/durability")
async def update_durability(
    memory_id: str,
    request: UpdateDurabilityRequest,
    user: User | None = Depends(require_auth),
):
    """Update durability classification of a memory."""
    try:
        qdrant = await get_qdrant_store()
        result = await qdrant.get(memory_id)
        if not result:
            raise HTTPException(status_code=404, detail="Memory not found")

        await qdrant.update_durability(memory_id, request.durability)
        neo4j = await get_neo4j_store()
        await neo4j.update_durability(memory_id, request.durability)

        pg = await get_postgres_store()
        await pg.log_audit(
            "update_durability", memory_id,
            actor=user.username if user else "user",
            user_id=user.id if user else None,
            details={"durability": request.durability},
        )

        return {"id": memory_id, "durability": request.durability}

    except HTTPException:
        raise
    except Exception as e:
        err = str(e).lower()
        if "wrong input" in err or "uuid" in err or "bad request" in err:
            raise HTTPException(status_code=404, detail="Memory not found")
        logger.error("update_durability_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================
# FORCE PROFILE (must come before /{memory_id} catch-all)
# =============================================================


@router.get("/{memory_id}/forces")
async def get_force_profile(memory_id: str):
    """Get the force profile for a memory — all forces acting on its importance."""
    try:
        from src.core.health import create_health_computer

        computer = await create_health_computer()
        result = await computer.compute_forces(memory_id)

        if result is None:
            raise HTTPException(status_code=404, detail="Memory not found")

        return result

    except HTTPException:
        raise
    except Exception as e:
        err = str(e).lower()
        if "wrong input" in err or "uuid" in err or "bad request" in err:
            raise HTTPException(status_code=404, detail="Memory not found")
        logger.error("force_profile_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================
# MEMORY CRUD (/{memory_id} routes — must come after static paths)
# =============================================================


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
            stored_by=payload.get("username"),
            pinned=payload.get("pinned") == "true",
            durability=payload.get("durability"),
            initial_importance=payload.get("initial_importance"),
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
async def delete_memory(memory_id: str, user: User | None = Depends(require_auth)):
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
        await pg.log_audit(
            "delete", memory_id,
            actor=user.username if user else "user",
            user_id=user.id if user else None,
        )

        return {"deleted": True, "id": memory_id}

    except Exception as e:
        err = str(e).lower()
        if "wrong input" in err or "uuid" in err or "bad request" in err:
            raise HTTPException(status_code=404, detail="Memory not found")
        logger.error("delete_memory_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{memory_id}/pin")
async def pin_memory(memory_id: str, user: User | None = Depends(require_auth)):
    """Pin a memory to make it immune to decay."""
    try:
        qdrant = await get_qdrant_store()
        result = await qdrant.get(memory_id)
        if not result:
            raise HTTPException(status_code=404, detail="Memory not found")

        await qdrant.update_pinned(memory_id, True)
        neo4j = await get_neo4j_store()
        await neo4j.update_pinned(memory_id, True)

        pg = await get_postgres_store()
        await pg.log_audit(
            "pin", memory_id,
            actor=user.username if user else "user",
            user_id=user.id if user else None,
        )

        return {"pinned": True, "id": memory_id}

    except HTTPException:
        raise
    except Exception as e:
        err = str(e).lower()
        if "wrong input" in err or "uuid" in err or "bad request" in err:
            raise HTTPException(status_code=404, detail="Memory not found")
        logger.error("pin_memory_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{memory_id}/pin")
async def unpin_memory(memory_id: str, user: User | None = Depends(require_auth)):
    """Unpin a memory, making it subject to normal decay."""
    try:
        qdrant = await get_qdrant_store()
        result = await qdrant.get(memory_id)
        if not result:
            raise HTTPException(status_code=404, detail="Memory not found")

        await qdrant.update_pinned(memory_id, False)
        neo4j = await get_neo4j_store()
        await neo4j.update_pinned(memory_id, False)

        pg = await get_postgres_store()
        await pg.log_audit(
            "unpin", memory_id,
            actor=user.username if user else "user",
            user_id=user.id if user else None,
        )

        return {"pinned": False, "id": memory_id}

    except HTTPException:
        raise
    except Exception as e:
        err = str(e).lower()
        if "wrong input" in err or "uuid" in err or "bad request" in err:
            raise HTTPException(status_code=404, detail="Memory not found")
        logger.error("unpin_memory_error", error=str(e))
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
async def batch_store_memories(request: BatchStoreRequest, user: User | None = Depends(require_auth)):
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
                    user_id=user.id if user else None,
                    username=user.username if user else None,
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
                    "create", memory.id,
                    actor=user.username if user else "user",
                    session_id=item.session_id,
                    details={"type": memory.memory_type.value, "domain": memory.domain, "batch": True},
                    user_id=user.id if user else None,
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
async def batch_delete_memories(request: BatchDeleteRequest, user: User | None = Depends(require_auth)):
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

                await pg.log_audit(
                    "delete", memory_id,
                    actor=user.username if user else "user",
                    details={"batch": True},
                    user_id=user.id if user else None,
                )
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


