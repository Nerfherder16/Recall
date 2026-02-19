"""
Memory consolidation - merging similar memories into stronger ones.

Like sleep consolidation in biological memory:
- Find semantically similar memories
- Merge redundant information
- Strengthen stable patterns
- Extract generalizations
"""

import numpy as np
import structlog

from .config import get_settings
from .embeddings import OllamaUnavailableError, content_hash, get_embedding_service
from .llm import LLMError, get_llm
from .models import (
    ConsolidationResult,
    Durability,
    Memory,
    MemorySource,
    MemoryType,
    Relationship,
    RelationshipType,
)

logger = structlog.get_logger()


class MemoryConsolidator:
    """
    Consolidate memories by merging similar ones.

    The consolidation process:
    1. Find clusters of similar memories
    2. Merge each cluster into a single, stronger memory
    3. Link the merged memory to its sources
    4. Mark source memories as superseded (but don't delete)
    """

    def __init__(self, qdrant_store, neo4j_store, embedding_service):
        self.qdrant = qdrant_store
        self.neo4j = neo4j_store
        self.embeddings = embedding_service
        self.settings = get_settings()

    async def consolidate(
        self,
        memory_type: MemoryType | None = None,
        domain: str | None = None,
        min_cluster_size: int = 2,
        dry_run: bool = False,
    ) -> list[ConsolidationResult]:
        """
        Run consolidation on memories.

        Args:
            memory_type: Only consolidate this type of memory
            domain: Only consolidate this domain
            min_cluster_size: Minimum memories needed to form a cluster
            dry_run: If True, don't actually merge, just return what would happen

        Returns:
            List of consolidation results
        """
        results = []

        # Get all eligible memories
        memories = await self._get_eligible_memories(memory_type, domain)
        if len(memories) < min_cluster_size:
            logger.info("not_enough_memories_for_consolidation", count=len(memories))
            return results

        # Cluster by semantic similarity
        clusters = await self._cluster_memories(memories)

        for cluster in clusters:
            if len(cluster) < min_cluster_size:
                continue

            logger.info(
                "found_memory_cluster",
                size=len(cluster),
                preview=cluster[0].content[:50],
            )

            if not dry_run:
                result = await self._merge_cluster(cluster)
                if result:
                    results.append(result)

        return results

    async def _get_eligible_memories(
        self,
        memory_type: MemoryType | None,
        domain: str | None,
    ) -> list[tuple[Memory, list[float]]]:
        """Get memories eligible for consolidation with their embeddings."""
        memories = []

        # Scroll through ALL non-superseded memories with vectors
        results = await self.qdrant.scroll_all(
            include_superseded=False,
            with_vectors=True,
        )

        min_importance = self.settings.min_importance_for_retrieval

        for memory_id, payload, embedding in results:
            # Apply filters
            if memory_type and payload.get("memory_type") != memory_type.value:
                continue
            if domain and payload.get("domain") != domain:
                continue
            if payload.get("importance", 0.5) < min_importance:
                continue

            memory = Memory(
                id=memory_id,
                content=payload.get("content", ""),
                memory_type=MemoryType(payload.get("memory_type", "semantic")),
                domain=payload.get("domain", "general"),
                importance=payload.get("importance", 0.5),
                stability=payload.get("stability", 0.1),
                confidence=payload.get("confidence", 0.8),
                tags=payload.get("tags", []),
                parent_ids=payload.get("parent_ids", []),
            )
            memories.append((memory, embedding))

        return memories

    async def _cluster_memories(
        self,
        memories: list[tuple[Memory, list[float]]],
    ) -> list[list[Memory]]:
        """
        Cluster memories by semantic similarity.

        Uses a simple greedy clustering approach:
        - For each memory, find others above similarity threshold
        - Group them into clusters
        """
        threshold = self.settings.consolidation_threshold
        clusters = []
        clustered = set()

        for i, (memory_i, embedding_i) in enumerate(memories):
            if memory_i.id in clustered:
                continue

            cluster = [memory_i]
            clustered.add(memory_i.id)

            # Find similar memories
            for j, (memory_j, embedding_j) in enumerate(memories):
                if i == j or memory_j.id in clustered:
                    continue

                similarity = self._cosine_similarity(embedding_i, embedding_j)

                if similarity >= threshold:
                    cluster.append(memory_j)
                    clustered.add(memory_j.id)

            if len(cluster) > 1:
                clusters.append(cluster)

        return clusters

    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        a = np.array(vec1)
        b = np.array(vec2)
        norm_a, norm_b = np.linalg.norm(a), np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    async def _merge_cluster(
        self,
        cluster: list[Memory],
    ) -> ConsolidationResult | None:
        """
        Merge a cluster of memories into one.

        The merged memory:
        - Combines content (or uses summary)
        - Has higher stability (consolidated)
        - Links to source memories
        """
        if not cluster:
            return None

        # Combine content via LLM summarization
        contents = [m.content for m in cluster]
        merged_content = await self._merge_contents(contents)

        # Aggregate properties
        avg_importance = sum(m.importance for m in cluster) / len(cluster)
        max_confidence = max(m.confidence for m in cluster)
        total_access = sum(m.access_count for m in cluster)

        # Collect all tags
        all_tags = set()
        for m in cluster:
            all_tags.update(m.tags)

        # Inherit highest durability from cluster
        durability_order = {Durability.EPHEMERAL: 0, Durability.DURABLE: 1, Durability.PERMANENT: 2}
        best_durability = None
        for m in cluster:
            if m.durability and (
                best_durability is None
                or durability_order.get(m.durability, 0) > durability_order.get(best_durability, 0)
            ):
                best_durability = m.durability

        # Create merged memory
        merged = Memory(
            content=merged_content,
            content_hash=content_hash(merged_content),
            memory_type=cluster[0].memory_type,  # Use first memory's type
            source=MemorySource.CONSOLIDATION,
            domain=cluster[0].domain,
            tags=list(all_tags),
            importance=min(1.0, avg_importance + 0.1),  # Boost importance
            stability=min(1.0, max(m.stability for m in cluster) + 0.2),  # Increase stability
            confidence=max_confidence,
            access_count=total_access,
            parent_ids=[m.id for m in cluster],
            durability=best_durability,
            initial_importance=min(1.0, avg_importance + 0.1),
        )

        # Generate embedding for merged content
        try:
            embedding = await self.embeddings.embed(merged_content)
        except OllamaUnavailableError:
            logger.warning(
                "consolidation_cluster_dropped_ollama_unavailable",
                cluster_size=len(cluster),
                preview=cluster[0].content[:80],
            )
            return None

        # Store merged memory — compensating delete on Neo4j failure
        await self.qdrant.store(merged, embedding)
        try:
            await self.neo4j.create_memory_node(merged)
        except Exception as neo4j_err:
            logger.error("neo4j_write_failed_compensating", id=merged.id, error=str(neo4j_err))
            await self.qdrant.delete(merged.id)
            return None

        # Create relationships
        for source_memory in cluster:
            relationship = Relationship(
                source_id=merged.id,
                target_id=source_memory.id,
                relationship_type=RelationshipType.DERIVED_FROM,
                strength=0.9,
            )
            await self.neo4j.create_relationship(relationship)

            # Mark source as superseded in both stores
            await self.qdrant.mark_superseded(source_memory.id, merged.id)
            await self.neo4j.mark_superseded(source_memory.id, merged.id)

        # Audit log — consolidation merge + supersedes
        try:
            from src.storage import get_postgres_store

            pg = await get_postgres_store()
            source_ids = [m.id for m in cluster]
            await pg.log_audit(
                "consolidate",
                merged.id,
                actor="consolidation",
                details={"source_ids": source_ids, "source_count": len(source_ids)},
            )
            for source_memory in cluster:
                await pg.log_audit(
                    "supersede",
                    source_memory.id,
                    actor="consolidation",
                    details={"superseded_by": merged.id},
                )
        except Exception as audit_err:
            logger.warning("consolidation_audit_failed", error=str(audit_err))

        logger.info(
            "merged_memories",
            merged_id=merged.id,
            source_count=len(cluster),
            content_preview=merged_content[:50],
        )

        return ConsolidationResult(
            merged_memory=merged,
            source_memories=[m.id for m in cluster],
            relationships_created=len(cluster),
            memories_superseded=len(cluster),
        )

    async def _merge_contents(self, contents: list[str]) -> str:
        """
        Merge multiple content strings into one using LLM summarization.

        Falls back to simple dedup+join if LLM is unavailable.
        """
        # Remove near-duplicates first
        unique = []
        for content in contents:
            is_dup = False
            for existing in unique:
                if content in existing or existing in content:
                    is_dup = True
                    break
            if not is_dup:
                unique.append(content)

        if len(unique) == 1:
            return unique[0]

        # Try LLM-powered merge
        try:
            llm = await get_llm()
            numbered = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(unique))
            prompt = (
                "Merge these overlapping memory fragments into a single, concise memory. "
                "Preserve all unique facts and details. Do not add information that isn't present. "
                "Return ONLY the merged text, no preamble.\n\n"
                f"Fragments:\n{numbered}\n\nMerged memory:"
            )
            merged = await llm.generate(prompt, temperature=0.1)
            merged = merged.strip()
            if merged and len(merged) > 10:
                logger.debug("llm_merge_success", fragments=len(unique), result_len=len(merged))
                return merged
        except (LLMError, Exception) as e:
            logger.warning("llm_merge_failed_using_fallback", error=str(e))

        # Fallback: join with separator
        return " | ".join(unique)


async def create_consolidator():
    """Create consolidator with dependencies."""
    from src.storage import get_neo4j_store, get_qdrant_store

    qdrant = await get_qdrant_store()
    neo4j = await get_neo4j_store()
    embeddings = await get_embedding_service()

    return MemoryConsolidator(qdrant, neo4j, embeddings)
