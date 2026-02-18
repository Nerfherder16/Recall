"""
Memory retrieval pipeline.

Multi-stage retrieval:
1. Embed query
2. Vector search (semantic similarity)
3. Graph expansion (related memories)
4. Context filtering (current relevance)
5. Ranking and selection
"""

import asyncio
import math
from datetime import datetime
from typing import Any

import structlog

from .config import get_settings
from .embeddings import get_embedding_service
from .models import (
    Durability,
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

    async def retrieve(
        self,
        query: MemoryQuery,
        browse_mode: bool = False,
    ) -> list[RetrievalResult]:
        """
        Execute the full retrieval pipeline.

        Args:
            query: The memory query to execute.
            browse_mode: If True, skip _track_access (for lightweight browsing).

        Returns memories ranked by relevance.
        """
        results: dict[str, RetrievalResult] = {}

        # Stage 1: Get query embedding
        query_embedding = query.embedding
        if not query_embedding and query.text:
            embedding_service = await get_embedding_service()
            query_embedding = await embedding_service.embed(query.text, prefix="query")

        # Stage 2: Vector search (main collection + facts sub-embeddings)
        if query_embedding:
            vector_results = await self._vector_search(query, query_embedding)
            for result in vector_results:
                results[result.memory.id] = result

            # Also search facts collection for precise sub-embedding matches
            fact_results = await self._fact_search(query, query_embedding, results)
            for result in fact_results:
                if result.memory.id not in results:
                    results[result.memory.id] = result
                else:
                    # Boost score — fact-level match is more precise
                    results[result.memory.id].score *= 1.1

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
                    # Graph-only results (no vector match) get capped score
                    # so they don't outrank actual semantic matches
                    result.score = min(result.score, 0.15)
                    results[result.memory.id] = result
                else:
                    # Boost score if found via both vector and graph
                    existing = results[result.memory.id]
                    existing.score *= 1.2

        # Stage 3.5: Document-sibling boost
        if query.expand_relationships and results:
            sibling_results = await self._document_sibling_boost(results)
            for result in sibling_results:
                if result.memory.id not in results:
                    results[result.memory.id] = result

        # Stage 4: Context filtering
        if query.session_id or query.current_file or query.current_task:
            results = await self._context_filter(results, query)

        # Stage 4.5: Anti-pattern check
        if query_embedding:
            anti_results = await self._check_anti_patterns(query, query_embedding)
            for result in anti_results:
                if result.memory.id not in results:
                    results[result.memory.id] = result

        # Stage 5: Final ranking (ML reranker or legacy formula)
        from .reranker import get_reranker

        reranker = await get_reranker(self.redis)
        ranked = self._rank_results(list(results.values()), query, reranker)

        # Stage 5.5: Inhibition — suppress contradictions and near-duplicates
        ranked = await self._inhibit(ranked)

        # Stage 6: Track access (fire-and-forget, skip in browse mode)
        final = ranked[: query.limit]
        if not browse_mode and final:
            asyncio.create_task(self._track_access(final))

        return final

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
            username=query.username,
        )

        for memory_id, similarity, payload in search_results:
            memory = self._payload_to_memory(memory_id, payload)
            results.append(
                RetrievalResult(
                    memory=memory,
                    score=similarity * max(memory.importance, 0.15),
                    similarity=similarity,
                    graph_distance=0,
                    retrieval_path=[memory_id],
                )
            )

        return results

    async def _fact_search(
        self,
        query: MemoryQuery,
        embedding: list[float],
        existing_results: dict[str, RetrievalResult],
    ) -> list[RetrievalResult]:
        """Search facts sub-embeddings for precise matches, return parent memories."""
        results = []
        try:
            fact_results = await self.qdrant.search_facts(
                query_vector=embedding,
                limit=query.limit,
                domain=query.domains[0] if query.domains else None,
            )
        except Exception:
            return results  # Facts collection might not exist yet

        seen_parents = set(existing_results.keys())
        for fact_id, similarity, fact_payload in fact_results:
            parent_id = fact_payload.get("parent_id")
            if not parent_id or parent_id in seen_parents:
                continue
            seen_parents.add(parent_id)

            # Fetch parent memory
            parent = await self.qdrant.get(parent_id)
            if not parent:
                continue

            _, payload = parent
            memory = self._payload_to_memory(parent_id, payload)

            # Fact-level match gets a precision boost
            results.append(
                RetrievalResult(
                    memory=memory,
                    score=similarity * max(memory.importance, 0.15) * 1.15,
                    similarity=similarity,
                    graph_distance=0,
                    retrieval_path=[parent_id],
                )
            )

        return results

    async def _graph_expand(
        self,
        seed_ids: list[str],
        relationship_types: list[RelationshipType] | None,
        max_depth: int,
    ) -> list[RetrievalResult]:
        """
        Stage 3: Spreading activation (Collins & Loftus, 1975).

        Instead of flat distance penalty, activation propagates through
        graph edges weighted by relationship strength:
          child_activation = parent_activation * edge_strength * decay
        where decay = 1 / (1 + hop * 0.3)
        """
        # Activation map: memory_id -> (best_activation, seed_id)
        activation: dict[str, tuple[float, str]] = {}

        if not seed_ids:
            return []

        # Fire all Neo4j queries concurrently
        all_related = await asyncio.gather(
            *(
                self.neo4j.find_related(
                    memory_id=seed_id,
                    relationship_types=relationship_types,
                    max_depth=max_depth,
                    limit=10,
                )
                for seed_id in seed_ids
            )
        )

        for seed_id, related in zip(seed_ids, all_related):
            for record in related:
                node_id = record["id"]
                strengths = record.get("rel_strengths", [])

                # Propagate activation through edge strengths
                # Start with seed activation = 1.0
                act = 1.0
                for hop_idx, strength in enumerate(strengths):
                    edge_strength = max(0.01, min(1.0, strength))
                    decay = 1.0 / (1 + (hop_idx + 1) * 0.3)
                    act *= edge_strength * decay

                # Scale by node importance
                node_importance = record.get("importance", 0.5) or 0.5
                act *= node_importance

                # Keep highest activation across seeds
                if node_id not in activation or act > activation[node_id][0]:
                    activation[node_id] = (act, seed_id)

        # Fetch memories for activated nodes above threshold
        results = []
        activation_threshold = 0.20

        for node_id, (act, seed_id) in activation.items():
            if act < activation_threshold:
                continue

            qdrant_result = await self.qdrant.get(node_id)
            if qdrant_result:
                _, payload = qdrant_result
                memory = self._payload_to_memory(node_id, payload)
                results.append(
                    RetrievalResult(
                        memory=memory,
                        score=act,
                        similarity=0.0,
                        graph_distance=0,  # activation replaces distance
                        retrieval_path=[seed_id, node_id],
                    )
                )

        return results

    async def _document_sibling_boost(
        self,
        results: dict[str, RetrievalResult],
    ) -> list[RetrievalResult]:
        """
        Stage 3.5: Document-sibling boost.

        When a seed memory came from a document (has document_id),
        find sibling memories from the same document and include them
        with a moderate score boost.
        """
        from src.storage.neo4j_documents import Neo4jDocumentStore

        sibling_results = []
        doc_store = Neo4jDocumentStore(self.neo4j.driver)

        for memory_id, result in list(results.items())[:5]:
            doc_id = result.memory.metadata.get("document_id")
            if not doc_id:
                continue

            try:
                sibling_ids = await doc_store.find_document_siblings(
                    memory_id,
                    doc_id,
                    limit=5,
                )
            except Exception:
                continue

            for sib_id in sibling_ids:
                if sib_id in results:
                    continue
                qdrant_result = await self.qdrant.get(sib_id)
                if not qdrant_result:
                    continue
                _, payload = qdrant_result
                memory = self._payload_to_memory(sib_id, payload)
                sibling_results.append(
                    RetrievalResult(
                        memory=memory,
                        score=0.3 * memory.importance,
                        similarity=0.0,
                        graph_distance=1,
                        retrieval_path=[memory_id, sib_id],
                    )
                )

        return sibling_results

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
        self,
        results: list[RetrievalResult],
        query: MemoryQuery,
        reranker=None,
    ) -> list[RetrievalResult]:
        """Stage 5: Final ranking. Uses ML reranker if available, else legacy formula."""
        if reranker is not None:
            return reranker.score_results(results)

        # Legacy formula
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

    async def _inhibit(self, ranked: list[RetrievalResult]) -> list[RetrievalResult]:
        """
        Stage 5.5: Interference and inhibition.

        Two suppression mechanisms:
        1. Contradiction inhibition: if A CONTRADICTS B and A scores higher,
           penalize B by 0.7x (it might still appear, just ranked lower).
        2. Near-duplicate suppression: if two results have very similar content
           (same content_hash or score ratio within 5%), keep only the higher.
        """
        if len(ranked) < 2:
            return ranked

        # --- Contradiction inhibition via Neo4j CONTRADICTS edges ---
        result_ids = [r.memory.id for r in ranked]
        try:
            contradictions = await self.neo4j.find_contradictions(result_ids)
        except Exception:
            contradictions = []

        # Build score lookup
        score_map = {r.memory.id: r for r in ranked}

        suppressed_ids: set[str] = set()
        for id_a, id_b in contradictions:
            ra, rb = score_map.get(id_a), score_map.get(id_b)
            if not ra or not rb:
                continue
            # Higher score wins — penalize the loser
            if ra.score >= rb.score:
                rb.score *= 0.7
            else:
                ra.score *= 0.7

        # --- Near-duplicate suppression ---
        # Group by content hash to catch exact duplicates
        seen_hashes: dict[str, str] = {}  # hash -> best id
        for r in ranked:
            chash = getattr(r.memory, "content_hash", None)
            if not chash:
                continue
            if chash in seen_hashes:
                # Duplicate — suppress the lower-scored one
                suppressed_ids.add(r.memory.id)
            else:
                seen_hashes[chash] = r.memory.id

        # Remove fully suppressed, re-sort
        result = [r for r in ranked if r.memory.id not in suppressed_ids]
        result.sort(key=lambda r: r.score, reverse=True)
        return result

    async def _check_anti_patterns(
        self,
        query: MemoryQuery,
        embedding: list[float],
    ) -> list[RetrievalResult]:
        """Stage 4.5: Check anti-patterns collection for relevant warnings."""
        results = []
        try:
            domain = None
            if query.domains:
                domain = query.domains[0]
            elif query.current_file:
                # Extract domain hint from file path
                parts = query.current_file.replace("\\", "/").split("/")
                domain = parts[-1].split(".")[0] if parts else None

            matches = await self.qdrant.search_anti_patterns(
                query_vector=embedding,
                limit=3,
                domain=domain,
            )

            for ap_id, similarity, payload in matches:
                if similarity < 0.3:
                    continue

                # Build a synthetic Memory to carry the anti-pattern through the pipeline
                memory = Memory(
                    id=ap_id,
                    content=f"WARNING: {payload.get('warning', '')}",
                    memory_type=MemoryType.SEMANTIC,
                    domain=payload.get("domain", "general"),
                    tags=payload.get("tags", []),
                    importance=0.8,
                    stability=1.0,
                    confidence=0.9,
                    metadata={
                        "is_anti_pattern": True,
                        "warning": payload.get("warning", ""),
                        "alternative": payload.get("alternative"),
                        "severity": payload.get("severity", "warning"),
                        "pattern": payload.get("pattern", ""),
                    },
                )

                # Apply domain-match boost (1.4x, higher than normal 1.3x)
                score = similarity * 0.8  # base score
                if domain and payload.get("domain") == domain:
                    score *= 1.4

                # Escalating boost: repeated warnings get louder
                times_triggered = payload.get("times_triggered", 0)
                if times_triggered > 0:
                    score *= 1.0 + 0.1 * math.log2(1 + times_triggered)

                results.append(
                    RetrievalResult(
                        memory=memory,
                        score=score,
                        similarity=similarity,
                        graph_distance=0,
                        retrieval_path=[ap_id],
                    )
                )

                # Increment trigger count (fire-and-forget)
                try:
                    await self.qdrant.increment_triggered(ap_id)
                except Exception:
                    pass

        except Exception as e:
            logger.debug("anti_pattern_check_error", error=str(e))

        return results

    async def _track_access(self, results: list[RetrievalResult]):
        """Track that these memories were accessed (reinforcement)."""
        now = datetime.utcnow()

        for result in results:
            memory = result.memory

            # Skip anti-patterns — they live in a separate collection
            if memory.metadata.get("is_anti_pattern"):
                continue

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
            created_at=datetime.fromisoformat(payload["created_at"])
            if payload.get("created_at")
            else datetime.utcnow(),
            updated_at=datetime.fromisoformat(payload["updated_at"])
            if payload.get("updated_at")
            else datetime.utcnow(),
            last_accessed=datetime.fromisoformat(payload["last_accessed"])
            if payload.get("last_accessed")
            else datetime.utcnow(),
            session_id=payload.get("session_id"),
            superseded_by=payload.get("superseded_by"),
            parent_ids=payload.get("parent_ids", []),
            user_id=payload.get("user_id"),
            username=payload.get("username"),
            pinned=payload.get("pinned") == "true",
            durability=Durability(payload["durability"])
            if payload.get("durability")
            else Durability.DURABLE,
            initial_importance=payload.get("initial_importance"),
        )


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def create_retrieval_pipeline():
    """Create retrieval pipeline with all dependencies."""
    from src.storage import get_neo4j_store, get_qdrant_store, get_redis_store

    qdrant = await get_qdrant_store()
    neo4j = await get_neo4j_store()
    redis = await get_redis_store()

    return RetrievalPipeline(qdrant, neo4j, redis)
