"""
Search and retrieval routes.
"""

from datetime import datetime

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.api.rate_limit import limiter
from src.core import MemoryQuery, MemoryType
from src.core.embeddings import OllamaUnavailableError
from src.core.retrieval import get_retrieval_pipeline

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
    since: datetime | None = None
    until: datetime | None = None
    user: str | None = None  # Filter by username


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
    stored_by: str | None = None
    pinned: bool = False
    durability: str | None = None


class SearchResponse(BaseModel):
    """Response from memory search."""

    results: list[SearchResult]
    total: int
    query: str


class BrowseResult(BaseModel):
    """A lightweight search result for the 3-layer browse flow."""

    id: str
    summary: str
    memory_type: str
    domain: str
    similarity: float
    importance: float
    created_at: str
    tags: list[str]
    stored_by: str | None = None
    pinned: bool = False
    access_count: int = 0
    durability: str | None = None


class BrowseResponse(BaseModel):
    """Response from browse search."""

    results: list[BrowseResult]
    total: int
    query: str


class TimelineRequest(BaseModel):
    """Request for chronological timeline view."""

    anchor_id: str | None = None
    domain: str | None = None
    memory_type: str | None = None
    limit: int = Field(default=20, ge=1, le=100)
    before: int = Field(default=10, ge=0)
    after: int = Field(default=10, ge=0)


class TimelineEntry(BaseModel):
    """A single timeline entry."""

    id: str
    summary: str
    memory_type: str
    domain: str
    created_at: str
    importance: float
    stored_by: str | None = None
    pinned: bool = False
    access_count: int = 0
    durability: str | None = None


class TimelineResponse(BaseModel):
    """Response from timeline view."""

    entries: list[TimelineEntry]
    total: int
    anchor_id: str | None


class RehydrateRequest(BaseModel):
    """Request for temporal context reconstruction."""

    since: str | None = None
    until: str | None = None
    domain: str | None = None
    memory_type: str | None = None
    max_entries: int = Field(default=50, ge=1, le=200)
    include_narrative: bool = False
    include_anti_patterns: bool = False


class RehydrateEntry(BaseModel):
    """A single entry in the rehydrated context."""

    id: str
    summary: str
    memory_type: str
    domain: str
    created_at: str
    importance: float
    durability: str | None = None
    pinned: bool = False
    is_anti_pattern: bool = False


class RehydrateResponse(BaseModel):
    """Response from temporal context reconstruction."""

    entries: list[RehydrateEntry]
    total: int
    window_start: str
    window_end: str
    narrative: str | None = None


class ContextRequest(BaseModel):
    """Request for context assembly."""

    query: str | None = None
    session_id: str | None = None
    current_file: str | None = None
    current_task: str | None = None
    domain: str | None = None
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


@router.post("/browse", response_model=BrowseResponse)
@limiter.limit("30/minute")
async def browse_memories(request: Request, body: SearchRequest):
    """
    Token-efficient memory search.

    Returns lightweight results with 120-char summaries instead of full content.
    Use GET /memory/{id} to fetch full details for specific results.
    """
    try:
        query = MemoryQuery(
            text=body.query,
            memory_types=body.memory_types,
            domains=body.domains,
            tags=body.tags,
            min_importance=body.min_importance,
            expand_relationships=body.expand_relationships,
            max_depth=body.max_depth,
            limit=body.limit,
            session_id=body.session_id,
            current_file=body.current_file,
            current_task=body.current_task,
            since=body.since,
            until=body.until,
            username=body.user,
        )

        pipeline = await get_retrieval_pipeline()
        results = await pipeline.retrieve(query)

        browse_results = [
            BrowseResult(
                id=r.memory.id,
                summary=r.memory.content[:120],
                memory_type=r.memory.memory_type.value,
                domain=r.memory.domain,
                similarity=round(r.similarity, 4),
                importance=r.memory.importance,
                created_at=r.memory.created_at.isoformat(),
                tags=r.memory.tags,
                stored_by=r.memory.username,
                pinned=r.memory.pinned,
                access_count=r.memory.access_count,
                durability=r.memory.durability.value if r.memory.durability else None,
            )
            for r in results
        ]

        logger.info("browse_completed", query=body.query[:50], results=len(browse_results))

        return BrowseResponse(
            results=browse_results,
            total=len(browse_results),
            query=body.query,
        )

    except OllamaUnavailableError:
        raise HTTPException(status_code=503, detail="Embedding service unavailable")
    except Exception as e:
        logger.error("browse_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/timeline", response_model=TimelineResponse)
@limiter.limit("30/minute")
async def timeline_view(request: Request, body: TimelineRequest):
    """
    Browse memories chronologically around an anchor point.

    If anchor_id is provided, centers the timeline there.
    Otherwise returns the most recent entries.
    """
    try:
        from src.storage import get_qdrant_store

        qdrant = await get_qdrant_store()

        anchor_date = None
        if body.anchor_id:
            result = await qdrant.get(body.anchor_id)
            if not result:
                raise HTTPException(status_code=404, detail="Anchor memory not found")
            _, payload = result
            anchor_date = payload.get("created_at")

        if anchor_date:
            points = await qdrant.scroll_around(
                anchor_date=anchor_date,
                before=body.before,
                after=body.after,
                domain=body.domain,
                memory_type=body.memory_type,
            )
        else:
            # No anchor — return most recent
            points = await qdrant.scroll_around(
                anchor_date=datetime.utcnow().isoformat(),
                before=body.limit,
                after=0,
                domain=body.domain,
                memory_type=body.memory_type,
            )

        entries = [
            TimelineEntry(
                id=mid,
                summary=payload.get("content", "")[:120],
                memory_type=payload.get("memory_type", "semantic"),
                domain=payload.get("domain", "general"),
                created_at=payload.get("created_at", ""),
                importance=payload.get("importance", 0.5),
                stored_by=payload.get("username"),
                pinned=payload.get("pinned") == "true",
                access_count=payload.get("access_count", 0),
                durability=payload.get("durability"),
            )
            for mid, payload in points
        ]

        logger.info("timeline_completed", entries=len(entries), anchor=body.anchor_id)

        return TimelineResponse(
            entries=entries,
            total=len(entries),
            anchor_id=body.anchor_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("timeline_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/rehydrate", response_model=RehydrateResponse)
@limiter.limit("10/minute")
async def rehydrate_context(request: Request, body: RehydrateRequest):
    """
    Temporal context reconstruction.

    Assembles a chronological briefing from memories in a time window.
    Optionally includes LLM-generated narrative summary and anti-patterns.
    """
    try:
        import datetime as dt_mod
        import hashlib
        import json

        from src.storage import get_qdrant_store, get_redis_store

        redis = await get_redis_store()

        # Default time range: last 24 hours
        if not body.since:
            body.since = (datetime.utcnow() - dt_mod.timedelta(hours=24)).isoformat()
        if not body.until:
            body.until = datetime.utcnow().isoformat()

        # Check Redis cache
        cache_key = (
            "recall:rehydrate:"
            + hashlib.md5(
                f"{body.since}:{body.until}:{body.domain}:{body.memory_type}"
                f":{body.include_narrative}:{body.include_anti_patterns}".encode()
            ).hexdigest()
        )

        cached = await redis.client.get(cache_key)
        if cached:
            return RehydrateResponse(**json.loads(cached))

        qdrant = await get_qdrant_store()

        # Scroll memories in time range
        points = await qdrant.scroll_time_range(
            since=body.since,
            until=body.until,
            domain=body.domain,
            memory_type=body.memory_type,
            limit=body.max_entries,
        )

        entries = [
            RehydrateEntry(
                id=mid,
                summary=payload.get("content", "")[:120],
                memory_type=payload.get("memory_type", "semantic"),
                domain=payload.get("domain", "general"),
                created_at=payload.get("created_at", ""),
                importance=payload.get("importance", 0.5),
                durability=payload.get("durability"),
                pinned=payload.get("pinned") == "true",
            )
            for mid, payload in points
        ]

        # Optional anti-pattern inclusion
        if body.include_anti_patterns:
            try:
                from qdrant_client.models import (
                    DatetimeRange,
                    FieldCondition,
                    Filter,
                    MatchValue,
                )

                ap_conditions = [
                    FieldCondition(key="created_at", range=DatetimeRange(gte=body.since)),
                    FieldCondition(key="created_at", range=DatetimeRange(lte=body.until)),
                ]
                if body.domain:
                    ap_conditions.append(
                        FieldCondition(key="domain", match=MatchValue(value=body.domain))
                    )

                ap_points, _ = await qdrant.client.scroll(
                    collection_name=qdrant.anti_patterns_collection,
                    scroll_filter=Filter(must=ap_conditions),
                    limit=body.max_entries,
                    with_payload=True,
                )
                for point in ap_points:
                    p = point.payload or {}
                    entries.append(
                        RehydrateEntry(
                            id=str(point.id),
                            summary=p.get("content", "")[:120],
                            memory_type=p.get("memory_type", "warning"),
                            domain=p.get("domain", "general"),
                            created_at=p.get("created_at", ""),
                            importance=p.get("importance", 0.5),
                            durability=p.get("durability"),
                            pinned=p.get("pinned") == "true",
                            is_anti_pattern=True,
                        )
                    )
                # Re-sort chronologically after merging
                entries.sort(key=lambda e: e.created_at)
            except Exception as ap_err:
                logger.warning("rehydrate_anti_patterns_failed", error=str(ap_err))

        window_start = entries[0].created_at if entries else body.since
        window_end = entries[-1].created_at if entries else body.until

        # Optional LLM narrative
        narrative = None
        if body.include_narrative and entries:
            try:
                from src.core.llm import get_llm

                llm = await get_llm()
                summaries = "\n".join(
                    f"- [{e.created_at}] ({e.memory_type}) {e.summary}" for e in entries
                )
                prompt = (
                    "You are summarizing a developer's session memories. "
                    "Write a 2-3 paragraph narrative briefing from these memories:\n\n"
                    f"{summaries}\n\n"
                    "Focus on what was accomplished, key decisions, and anything noteworthy."
                )
                narrative = await llm.generate(prompt, temperature=0.3)
            except Exception as llm_err:
                logger.warning("rehydrate_llm_failed", error=str(llm_err))

        response = RehydrateResponse(
            entries=entries,
            total=len(entries),
            window_start=window_start,
            window_end=window_end,
            narrative=narrative,
        )

        # Cache for 2 minutes
        await redis.client.setex(cache_key, 120, json.dumps(response.model_dump(), default=str))

        logger.info("rehydrate_completed", entries=len(entries), domain=body.domain)

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("rehydrate_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/query", response_model=SearchResponse)
@limiter.limit("30/minute")
async def search_memories(request: Request, body: SearchRequest):
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
            text=body.query,
            memory_types=body.memory_types,
            domains=body.domains,
            tags=body.tags,
            min_importance=body.min_importance,
            expand_relationships=body.expand_relationships,
            max_depth=body.max_depth,
            limit=body.limit,
            session_id=body.session_id,
            current_file=body.current_file,
            current_task=body.current_task,
            since=body.since,
            until=body.until,
            username=body.user,
        )

        # Execute retrieval
        pipeline = await get_retrieval_pipeline()
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
                stored_by=r.memory.username,
                pinned=r.memory.pinned,
                durability=r.memory.durability.value if r.memory.durability else None,
            )
            for r in results
        ]

        logger.info(
            "search_completed",
            query=body.query[:50],
            results=len(search_results),
        )

        return SearchResponse(
            results=search_results,
            total=len(search_results),
            query=body.query,
        )

    except OllamaUnavailableError:
        raise HTTPException(status_code=503, detail="Embedding service unavailable")
    except Exception as e:
        logger.error("search_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/context", response_model=ContextResponse)
@limiter.limit("30/minute")
async def assemble_context(request: Request, body: ContextRequest):
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
        if body.include_working_memory and body.session_id:
            redis = await get_redis_store()
            working_ids = await redis.get_working_memory(body.session_id)

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
        if body.query or body.current_task:
            query = MemoryQuery(
                text=body.query or body.current_task,
                session_id=body.session_id,
                current_file=body.current_file,
                current_task=body.current_task,
                domains=[body.domain] if body.domain else None,
                limit=10,
            )

            pipeline = await get_retrieval_pipeline()
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

            # Separate anti-pattern warnings from regular memories
            warnings = []
            for r in results:
                meta = r.memory.metadata or {}
                if meta.get("is_anti_pattern"):
                    warning_text = meta.get("warning", r.memory.content)
                    alt = meta.get("alternative")
                    line = f"- WARNING: {warning_text}"
                    if alt:
                        line += f" -> Instead: {alt}"
                    warnings.append(line)

            # Format each type
            if warnings:
                context_parts.append("## Warnings (things to avoid)\n" + "\n".join(warnings))

            if by_type["semantic"]:
                context_parts.append(
                    "## Known Facts\n" + "\n".join(f"- {c}" for c in by_type["semantic"])
                )

            if by_type["episodic"]:
                context_parts.append(
                    "## Previous Experiences\n" + "\n".join(f"- {c}" for c in by_type["episodic"])
                )

            if by_type["procedural"]:
                context_parts.append(
                    "## Workflows\n" + "\n".join(f"- {c}" for c in by_type["procedural"])
                )

        # Combine context
        full_context = "\n\n".join(context_parts) if context_parts else ""

        # Estimate tokens (rough: 1 token ≈ 4 chars)
        estimated_tokens = len(full_context) // 4

        # Truncate if needed
        if estimated_tokens > body.max_tokens:
            char_limit = body.max_tokens * 4
            full_context = full_context[:char_limit] + "\n... (truncated)"
            estimated_tokens = body.max_tokens

        return ContextResponse(
            context=full_context,
            memories_used=memories_used,
            estimated_tokens=estimated_tokens,
            breakdown=breakdown,
        )

    except OllamaUnavailableError:
        raise HTTPException(status_code=503, detail="Embedding service unavailable")
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
