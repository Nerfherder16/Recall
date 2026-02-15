"""
Memory retrieval pipeline.

Multi-stage retrieval:
1. Embed query
2. Vector search (semantic similarity)
3. Graph expansion (related memories)
4. Context filtering (current relevance)
5. Ranking and selection
"""

from datetime import datetime
from typing import Any

import structlog

from .config import get_settings
from .embeddings import get_embedding_service
from .models import (
    Memory,
    MemoryQuery,
    MemoryType,
    RelationshipType,
    RetrievalResult,
)

logger = structlog.get_logger()


class RetrievalPipeline:
    """
    Multi-stage memory retrieval.

    The pipeline mimics how human memory reconstruction works:
    - Start with semantic similarity
    - Expand through associations
    - Filter by current context
    - Rank by combined relevance
    """

    def __init__(self, qdrant_store, neo4j_store, redis_store):
        self.qdrant = qdrant_store
        self.neo4j = neo4j_store
        self.redis = redis_store
        self.settings = get_settings()

    async def retrieve(self, query: MemoryQuery) -> list[RetrievalResult]:
        """
        Execute the full retrieval pipeline.

        Returns memories ranked by relevance.
        """
        results: dict[str, RetrievalResult] = {}

        # Stage 1: Get query embedding
        query_embedding = query.embedding
        if not query_embedding and query.text:
            embedding_service = await get_embedding_service()
            query_embedding = await embedding_service.embed(query.text, prefix="query")

        # Stage 2: Vector search
        if query_embedding:
            vector_results = await self._vector_search(query, query_embedding)
            for result in vector_results:
                results[result.memory.id] = result

        # Stage 3: Graph expansion
        if query.expand_relationships and results:
            seed_ids = list(results.keys())[:5]  # Top 5 as seeds
            graph_results = await self._graph_expand(
                seed_ids,
                query.relationship_types,
                query.max_depth,
            )

            for result in graph_results:
                if result.memory.id not in results:
                    results[result.memory.id] = result
                else:
                    # Boost score if found via both vector and graph
                    existing = results[result.memory.id]
                    existing.score *= 1.2

        # Stage 4: Context filtering
        if query.session_id or query.current_file or query.current_task:
            results = await self._context_filter(results, query)

        # Stage 5: Final ranking
        ranked = self._rank_results(list(results.values()), query)

        # Stage 6: Track access
        await self._track_access(ranked[:query.limit])

        return ranked[:query.limit]

    async def _vector_search(
        self, query: MemoryQuery, embedding: list[float]
    ) -> list[RetrievalResult]:
        """Stage 2: Semantic similarity search."""
        results = []

        search_results = await self.qdrant.search(
            query_vector=embedding,
            limit=query.limit * 2,  # Get extra for filtering
            memory_types=query.memory_types,
            domains=query.domains,
            min_importance=query.min_importance,
            include_superseded=query.include_superseded,
            session_id=query.session_id if query.session_id else None,
            since=query.since.isoformat() if query.since else None,
            until=query.until.isoformat() if query.until else None,
        )

        for memory_id, similarity, payload in search_results:
            memory = self._payload_to_memory(memory_id, payload)
            results.append(
                RetrievalResult(
                    memory=memory,
                    score=similarity * memory.importance,
                    similarity=similarity,
                    graph_distance=0,
                    retrieval_path=[memory_id],
                )
            )

        return results

    async def _graph_expand(
        self,
        seed_ids: list[str],
        relationship_types: list[RelationshipType] | None,
        max_depth: int,
    ) -> list[RetrievalResult]:
        """Stage 3: Expand through graph relationships."""
        results = []

        for seed_id in seed_ids:
            related = await self.neo4j.find_related(
                memory_id=seed_id,
                relationship_types=relationship_types,
                max_depth=max_depth,
                limit=10,
            )

            for record in related:
                # Fetch full memory from Qdrant
                qdrant_result = await self.qdrant.get(record["id"])
                if qdrant_result:
                    embedding, payload = qdrant_result
                    memory = self._payload_to_memory(record["id"], payload)

                    # Score decreases with distance
                    distance = record.get("distance", 1)
                    graph_score = memory.importance / (1 + distance * 0.3)

                    results.append(
                        RetrievalResult(
                            memory=memory,
                            score=graph_score,
                            similarity=0.0,  # Not from vector search
                            graph_distance=distance,
                            retrieval_path=[seed_id, record["id"]],
                        )
                    )

        return results

    async def _context_filter(
        self, results: dict[str, RetrievalResult], query: MemoryQuery
    ) -> dict[str, RetrievalResult]:
        """Stage 4: Filter and boost by current context."""
        filtered = {}

        # Get working memory if session provided
        working_memory_ids = []
        if query.session_id:
            working_memory_ids = await self.redis.get_working_memory(query.session_id)

        for memory_id, result in results.items():
            score_multiplier = 1.0

            # Boost if in working memory
            if memory_id in working_memory_ids:
                score_multiplier *= 1.5

            # Boost if domain matches current context
            if query.current_file:
                # Extract domain hints from file path
                file_lower = query.current_file.lower()
                if result.memory.domain in file_lower:
                    score_multiplier *= 1.3

            if query.current_task:
                # Match task keywords to memory tags
                task_words = set(query.current_task.lower().split())
                memory_tags = set(t.lower() for t in result.memory.tags)
                overlap = len(task_words & memory_tags)
                if overlap > 0:
                    score_multiplier *= 1 + (overlap * 0.2)

            result.score *= score_multiplier
            filtered[memory_id] = result

        return filtered

    def _rank_results(
        self, results: list[RetrievalResult], query: MemoryQuery
    ) -> list[RetrievalResult]:
        """Stage 5: Final ranking."""
        for result in results:
            memory = result.memory

            # Recency boost
            hours_old = (datetime.utcnow() - memory.last_accessed).total_seconds() / 3600
            recency_factor = 1.0 / (1 + hours_old * 0.01)

            # Stability factor (consolidated memories are more reliable)
            stability_factor = 0.5 + memory.stability * 0.5

            # Confidence factor
            confidence_factor = 0.7 + memory.confidence * 0.3

            # Combined score
            result.score *= recency_factor * stability_factor * confidence_factor

        # Sort by final score
        results.sort(key=lambda r: r.score, reverse=True)
        return results

    async def _track_access(self, results: list[RetrievalResult]):
        """Track that these memories were accessed (reinforcement)."""
        now = datetime.utcnow()

        for result in results:
            memory = result.memory
            memory.access_count += 1
            memory.last_accessed = now

            # Reinforce importance slightly
            memory.importance = min(1.0, memory.importance + 0.02)

            # Update access count and timestamps in Qdrant
            await self.qdrant.update_access(
                memory.id,
                memory.access_count,
                now.isoformat(),
            )

            # Persist the importance boost to both stores
            await self.qdrant.update_importance(memory.id, memory.importance)
            await self.neo4j.update_importance(memory.id, memory.importance)

    def _payload_to_memory(self, memory_id: str, payload: dict[str, Any]) -> Memory:
        """Convert Qdrant payload to Memory object."""
        return Memory(
            id=memory_id,
            content=payload.get("content", ""),
            memory_type=MemoryType(payload.get("memory_type", "semantic")),
            domain=payload.get("domain", "general"),
            tags=payload.get("tags", []),
            importance=payload.get("importance", 0.5),
            stability=payload.get("stability", 0.1),
            confidence=payload.get("confidence", 0.8),
            access_count=payload.get("access_count", 0),
            created_at=datetime.fromisoformat(payload["created_at"]) if payload.get("created_at") else datetime.utcnow(),
            updated_at=datetime.fromisoformat(payload["updated_at"]) if payload.get("updated_at") else datetime.utcnow(),
            last_accessed=datetime.fromisoformat(payload["last_accessed"]) if payload.get("last_accessed") else datetime.utcnow(),
            session_id=payload.get("session_id"),
            superseded_by=payload.get("superseded_by"),
            parent_ids=payload.get("parent_ids", []),
        )


async def create_retrieval_pipeline():
    """Create retrieval pipeline with all dependencies."""
    from src.storage import get_neo4j_store, get_qdrant_store, get_redis_store

    qdrant = await get_qdrant_store()
    neo4j = await get_neo4j_store()
    redis = await get_redis_store()

    return RetrievalPipeline(qdrant, neo4j, redis)
