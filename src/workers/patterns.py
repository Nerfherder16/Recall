"""
Pattern extraction worker.

Analyzes episodic memories to discover recurring patterns,
then promotes those patterns to semantic memories.

This is how the system "learns" from experience.
"""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import structlog

from src.core import (
    Memory,
    MemorySource,
    MemoryType,
    Relationship,
    RelationshipType,
    get_embedding_service,
)
from src.core.embeddings import OllamaUnavailableError, content_hash
from src.core.llm import LLMError, get_llm

logger = structlog.get_logger()


class PatternExtractor:
    """
    Extract patterns from episodic memories.

    The process:
    1. Get recent episodic memories
    2. Cluster by semantic similarity
    3. For recurring clusters, extract the common pattern
    4. Create semantic memories from patterns
    """

    def __init__(self, qdrant_store, neo4j_store):
        self.qdrant = qdrant_store
        self.neo4j = neo4j_store

    async def extract(self, days: int = 7, min_occurrences: int = 3) -> dict[str, Any]:
        """
        Extract patterns from recent memories.

        Args:
            days: Look back this many days
            min_occurrences: Minimum times a pattern must appear

        Returns:
            Statistics about extraction
        """
        stats = {
            "episodes_analyzed": 0,
            "clusters_found": 0,
            "patterns_created": 0,
        }

        # Get ALL episodic memories (unbiased scroll, not semantic search)
        all_points = await self.qdrant.scroll_all(
            include_superseded=False,
            with_vectors=True,
        )

        # Filter to episodic memories within the time window
        cutoff = datetime.utcnow() - timedelta(days=days)
        results = []
        for item in all_points:
            memory_id, payload, embedding = item
            if payload.get("memory_type") != MemoryType.EPISODIC.value:
                continue
            created = payload.get("created_at", "")
            if created and created < cutoff.isoformat():
                continue
            results.append((memory_id, payload, embedding))

        if len(results) < min_occurrences:
            logger.info("not_enough_episodes", count=len(results))
            return stats

        stats["episodes_analyzed"] = len(results)

        # Build list with embeddings already loaded from scroll
        memories_with_embeddings = []
        for memory_id, payload, embedding in results:
            memories_with_embeddings.append(
                {
                    "id": memory_id,
                    "content": payload.get("content", ""),
                    "embedding": embedding,
                    "domain": payload.get("domain", "general"),
                    "tags": payload.get("tags", []),
                }
            )

        # Cluster by similarity
        clusters = self._cluster_by_similarity(
            memories_with_embeddings,
            threshold=0.65,
            min_size=min_occurrences,
        )

        stats["clusters_found"] = len(clusters)

        # Create patterns from clusters
        for cluster in clusters:
            pattern = await self._create_pattern_from_cluster(cluster)
            if pattern:
                stats["patterns_created"] += 1

        logger.info(
            "pattern_extraction_complete",
            episodes=stats["episodes_analyzed"],
            clusters=stats["clusters_found"],
            patterns=stats["patterns_created"],
        )

        return stats

    def _cluster_by_similarity(
        self,
        memories: list[dict],
        threshold: float,
        min_size: int,
    ) -> list[list[dict]]:
        """
        Simple greedy clustering by cosine similarity.

        In production, could use more sophisticated clustering
        (DBSCAN, HDBSCAN, etc.)
        """
        clusters = []
        clustered = set()

        for i, mem_i in enumerate(memories):
            if mem_i["id"] in clustered:
                continue

            cluster = [mem_i]
            clustered.add(mem_i["id"])

            for j, mem_j in enumerate(memories):
                if i == j or mem_j["id"] in clustered:
                    continue

                similarity = self._cosine_similarity(
                    mem_i["embedding"],
                    mem_j["embedding"],
                )

                if similarity >= threshold:
                    cluster.append(mem_j)
                    clustered.add(mem_j["id"])

            if len(cluster) >= min_size:
                clusters.append(cluster)

        return clusters

    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """Compute cosine similarity."""
        a = np.array(vec1)
        b = np.array(vec2)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    async def _create_pattern_from_cluster(
        self,
        cluster: list[dict],
    ) -> Memory | None:
        """
        Create a semantic pattern memory from a cluster of episodes.

        The pattern summarizes what the episodes have in common.
        """
        if not cluster:
            return None

        # Extract common elements
        contents = [m["content"] for m in cluster]
        domains = [m["domain"] for m in cluster]
        all_tags = []
        for m in cluster:
            all_tags.extend(m["tags"])

        # Find most common domain
        domain_counts = defaultdict(int)
        for d in domains:
            domain_counts[d] += 1
        common_domain = max(domain_counts, key=domain_counts.get)

        # Find common tags
        tag_counts = defaultdict(int)
        for t in all_tags:
            tag_counts[t] += 1
        common_tags = [t for t, c in tag_counts.items() if c >= len(cluster) // 2]

        # Create pattern content via LLM summarization
        pattern_content = await self._extract_common_pattern(contents)

        if not pattern_content:
            return None

        # Check for duplicates
        try:
            embedding_service = await get_embedding_service()
            pattern_embedding = await embedding_service.embed(pattern_content)
        except OllamaUnavailableError:
            logger.warning("pattern_creation_ollama_unavailable")
            return None

        # Check if similar pattern exists
        existing = await self.qdrant.search(
            query_vector=pattern_embedding,
            limit=5,
            memory_types=[MemoryType.SEMANTIC],
        )

        for mem_id, similarity, payload in existing:
            if similarity > 0.9:
                logger.debug("pattern_already_exists", similarity=similarity)
                return None

        # Create the pattern memory
        pattern = Memory(
            content=pattern_content,
            content_hash=content_hash(pattern_content),
            memory_type=MemoryType.SEMANTIC,
            source=MemorySource.PATTERN,
            domain=common_domain,
            tags=common_tags + ["extracted_pattern"],
            importance=0.7,  # Start with moderate importance
            stability=0.5,  # Patterns are moderately stable
            confidence=min(
                1.0, len(cluster) / 10
            ),  # More occurrences = more confidence, capped at 1.0
            parent_ids=[m["id"] for m in cluster],
        )

        # Store pattern — compensating delete on Neo4j failure
        await self.qdrant.store(pattern, pattern_embedding)
        try:
            await self.neo4j.create_memory_node(pattern)
        except Exception as neo4j_err:
            logger.error("neo4j_write_failed_compensating", id=pattern.id, error=str(neo4j_err))
            await self.qdrant.delete(pattern.id)
            return None

        # Link to source episodes
        for source in cluster:
            relationship = Relationship(
                source_id=pattern.id,
                target_id=source["id"],
                relationship_type=RelationshipType.DERIVED_FROM,
                strength=0.8,
            )
            await self.neo4j.create_relationship(relationship)

        logger.info(
            "created_pattern",
            id=pattern.id,
            from_episodes=len(cluster),
            content=pattern_content[:50],
        )

        return pattern

    async def _extract_common_pattern(self, contents: list[str]) -> str | None:
        """
        Extract common pattern from multiple contents using LLM.

        Falls back to heuristic approach if LLM is unavailable.
        """
        if not contents:
            return None

        # Try LLM-powered extraction
        try:
            llm = await get_llm()
            numbered = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(contents))
            prompt = (
                "These episodic memories describe similar events that happened multiple times. "
                "Extract the recurring pattern as a single, general statement. "
                "Focus on WHAT keeps happening, not specific instances. "
                "Return ONLY the pattern statement, no preamble.\n\n"
                f"Episodes:\n{numbered}\n\nRecurring pattern:"
            )
            pattern = await llm.generate(prompt, temperature=0.1)
            pattern = pattern.strip()
            if pattern and len(pattern) > 10:
                logger.debug(
                    "llm_pattern_extraction_success",
                    episodes=len(contents),
                    result_len=len(pattern),
                )
                return pattern
        except (LLMError, Exception) as e:
            logger.warning("llm_pattern_extraction_failed_using_fallback", error=str(e))

        # Fallback: heuristic approach
        word_counts = defaultdict(int)
        for content in contents:
            words = set(content.lower().split())
            for word in words:
                if len(word) > 3:
                    word_counts[word] += 1

        threshold = len(contents) // 2
        common_words = {w for w, c in word_counts.items() if c > threshold}

        if len(common_words) < 3:
            return None

        shortest = min(contents, key=len)
        pattern = f"Pattern: {shortest}"
        return pattern if len(pattern) > 20 else None
