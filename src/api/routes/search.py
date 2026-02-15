"""
Search and retrieval routes.
"""

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.core import MemoryQuery, MemoryType, RelationshipType
from src.core.retrieval import create_retrieval_pipeline

logger = structlog.get_logger()
router = APIRouter()


# =============================================================
# REQUEST/RESPONSE MODELS
# =============================================================


class SearchRequest(BaseModel):
    """Request for memory search."""

    query: str
    memory_types: list[MemoryType] | None = None
    domains: list[str] | None = None
    tags: list[str] | None = None
    min_importance: float = 0.0
    expand_relationships: bool = True
    max_depth: int = Field(default=2, ge=1, le=10)
    limit: int = Field(default=10, ge=1, le=100)
    session_id: str | None = None
    current_file: str | None = None
    current_task: str | None = None


class SearchResult(BaseModel):
    """A single search result."""

    id: str
    content: str
    memory_type: str
    domain: str
    score: float
    similarity: float
    graph_distance: int
    importance: float
    tags: list[str]


class SearchResponse(BaseModel):
    """Response from memory search."""

    results: list[SearchResult]
    total: int
    query: str


class ContextRequest(BaseModel):
    """Request for context assembly."""

    query: str | None = None
    session_id: str | None = None
    current_file: str | None = None
    current_task: str | None = None
    max_tokens: int = 2000
    include_working_memory: bool = True


class ContextResponse(BaseModel):
    """Assembled context for injection."""

    context: str
    memories_used: int
    estimated_tokens: int
    breakdown: dict[str, int]


# =============================================================
# ROUTES
# =============================================================


@router.post("/query", response_model=SearchResponse)
async def search_memories(request: SearchRequest):
    """
    Search for relevant memories.

    Uses the full retrieval pipeline:
    1. Semantic similarity search
    2. Graph expansion
    3. Context filtering
    4. Ranking
    """
    try:
        # Build query
        query = MemoryQuery(
            text=request.query,
            memory_types=request.memory_types,
            domains=request.domains,
            tags=request.tags,
            min_importance=request.min_importance,
            expand_relationships=request.expand_relationships,
            max_depth=request.max_depth,
            limit=request.limit,
            session_id=request.session_id,
            current_file=request.current_file,
            current_task=request.current_task,
        )

        # Execute retrieval
        pipeline = await create_retrieval_pipeline()
        results = await pipeline.retrieve(query)

        # Format response
        search_results = [
            SearchResult(
                id=r.memory.id,
                content=r.memory.content,
                memory_type=r.memory.memory_type.value,
                domain=r.memory.domain,
                score=round(r.score, 4),
                similarity=round(r.similarity, 4),
                graph_distance=r.graph_distance,
                importance=r.memory.importance,
                tags=r.memory.tags,
            )
            for r in results
        ]

        logger.info(
            "search_completed",
            query=request.query[:50],
            results=len(search_results),
        )

        return SearchResponse(
            results=search_results,
            total=len(search_results),
            query=request.query,
        )

    except Exception as e:
        logger.error("search_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/context", response_model=ContextResponse)
async def assemble_context(request: ContextRequest):
    """
    Assemble context for injection into a conversation.

    This is the main endpoint for Claude Code integration.
    Returns formatted context suitable for system prompt injection.
    """
    try:
        from src.storage import get_redis_store

        memories_used = 0
        breakdown = {
            "working_memory": 0,
            "semantic": 0,
            "episodic": 0,
            "procedural": 0,
        }

        context_parts = []

        # Include working memory if session provided
        if request.include_working_memory and request.session_id:
            redis = await get_redis_store()
            working_ids = await redis.get_working_memory(request.session_id)

            if working_ids:
                from src.storage import get_qdrant_store

                qdrant = await get_qdrant_store()
                working_context = ["## Recent Context"]

                for memory_id in working_ids[:5]:  # Limit working memory
                    result = await qdrant.get(memory_id)
                    if result:
                        _, payload = result
                        working_context.append(f"- {payload.get('content', '')}")
                        breakdown["working_memory"] += 1
                        memories_used += 1

                if len(working_context) > 1:
                    context_parts.append("\n".join(working_context))

        # Retrieve relevant memories
        if request.query or request.current_task:
            query = MemoryQuery(
                text=request.query or request.current_task,
                session_id=request.session_id,
                current_file=request.current_file,
                current_task=request.current_task,
                limit=10,
            )

            pipeline = await create_retrieval_pipeline()
            results = await pipeline.retrieve(query)

            # Group by type
            by_type: dict[str, list] = {
                "semantic": [],
                "episodic": [],
                "procedural": [],
            }

            for r in results:
                type_key = r.memory.memory_type.value
                if type_key in by_type:
                    by_type[type_key].append(r.memory.content)
                    breakdown[type_key] += 1
                    memories_used += 1

            # Format each type
            if by_type["semantic"]:
                context_parts.append("## Known Facts\n" + "\n".join(f"- {c}" for c in by_type["semantic"]))

            if by_type["episodic"]:
                context_parts.append("## Previous Experiences\n" + "\n".join(f"- {c}" for c in by_type["episodic"]))

            if by_type["procedural"]:
                context_parts.append("## Workflows\n" + "\n".join(f"- {c}" for c in by_type["procedural"]))

        # Combine context
        full_context = "\n\n".join(context_parts) if context_parts else ""

        # Estimate tokens (rough: 1 token ≈ 4 chars)
        estimated_tokens = len(full_context) // 4

        # Truncate if needed
        if estimated_tokens > request.max_tokens:
            char_limit = request.max_tokens * 4
            full_context = full_context[:char_limit] + "\n... (truncated)"
            estimated_tokens = request.max_tokens

        return ContextResponse(
            context=full_context,
            memories_used=memories_used,
            estimated_tokens=estimated_tokens,
            breakdown=breakdown,
        )

    except Exception as e:
        logger.error("context_assembly_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/similar/{memory_id}")
async def find_similar(memory_id: str, limit: int = 5):
    """Find memories similar to a given memory."""
    try:
        from src.storage import get_qdrant_store

        qdrant = await get_qdrant_store()

        # Get the memory's embedding
        result = await qdrant.get(memory_id)
        if not result:
            raise HTTPException(status_code=404, detail="Memory not found")

        embedding, _ = result

        # Search for similar
        similar = await qdrant.search(
            query_vector=embedding,
            limit=limit + 1,  # +1 to exclude self
        )

        # Filter out self
        results = [
            {
                "id": mid,
                "similarity": round(score, 4),
                "content": payload.get("content", "")[:100],
            }
            for mid, score, payload in similar
            if mid != memory_id
        ][:limit]

        return {"source_id": memory_id, "similar": results}

    except HTTPException:
        raise
    except Exception as e:
        err = str(e).lower()
        if "wrong input" in err or "uuid" in err or "bad request" in err:
            raise HTTPException(status_code=404, detail="Memory not found")
        logger.error("find_similar_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")
