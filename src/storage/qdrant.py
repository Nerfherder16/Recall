"""
Qdrant vector storage for semantic memory retrieval.

Qdrant handles:
- Storing memory embeddings
- Fast similarity search
- Filtered retrieval
"""

from typing import Any

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    DatetimeRange,
    Distance,
    FieldCondition,
    Filter,
    IsNullCondition,
    MatchAny,
    MatchValue,
    PayloadField,
    PointStruct,
    Range,
    VectorParams,
)

from src.core import Memory, MemoryType, get_settings

logger = structlog.get_logger()


class QdrantStore:
    """Vector storage using Qdrant."""

    def __init__(self):
        self.settings = get_settings()
        self.client: AsyncQdrantClient | None = None
        self.collection = self.settings.qdrant_collection

    async def connect(self):
        """Initialize connection to Qdrant."""
        self.client = AsyncQdrantClient(
            host=self.settings.qdrant_host,
            port=self.settings.qdrant_port,
        )

        # Ensure collection exists
        collections = await self.client.get_collections()
        exists = any(c.name == self.collection for c in collections.collections)

        if not exists:
            await self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(
                    size=self.settings.embedding_dimensions,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("created_qdrant_collection", name=self.collection)

        # Create payload indexes for filtering
        await self._ensure_indexes()

        # Create facts sub-embedding collection
        await self.ensure_facts_collection()

        # Create anti-patterns collection
        await self.ensure_anti_patterns_collection()

    async def _ensure_indexes(self):
        """Create indexes for efficient filtering."""
        indexes = [
            ("memory_type", "keyword"),
            ("domain", "keyword"),
            ("source", "keyword"),
            ("session_id", "keyword"),
            ("content_hash", "keyword"),
            ("created_at", "datetime"),
            ("user_id", "integer"),
            ("username", "keyword"),
            ("pinned", "keyword"),
            ("access_count", "integer"),
            ("durability", "keyword"),
            ("document_id", "keyword"),
        ]

        for field, field_type in indexes:
            try:
                await self.client.create_payload_index(
                    collection_name=self.collection,
                    field_name=field,
                    field_schema=field_type,
                )
            except Exception:
                # Index might already exist
                pass

    async def store(self, memory: Memory, embedding: list[float]) -> str:
        """
        Store a memory with its embedding.

        Returns the memory ID.
        """
        point = PointStruct(
            id=memory.id,
            vector=embedding,
            payload={
                "content": memory.content,
                "content_hash": memory.content_hash,
                "memory_type": memory.memory_type.value,
                "source": memory.source.value,
                "domain": memory.domain,
                "tags": memory.tags,
                "importance": memory.importance,
                "stability": memory.stability,
                "confidence": memory.confidence,
                "access_count": memory.access_count,
                "created_at": memory.created_at.isoformat(),
                "updated_at": memory.updated_at.isoformat(),
                "last_accessed": memory.last_accessed.isoformat(),
                "session_id": memory.session_id,
                "superseded_by": memory.superseded_by,
                "parent_ids": memory.parent_ids,
                "metadata": memory.metadata,
                "user_id": memory.user_id,
                "username": memory.username,
                "pinned": "true" if memory.pinned else "false",
                "durability": memory.durability.value if memory.durability else None,
                "initial_importance": memory.initial_importance,
                "document_id": memory.metadata.get("document_id"),
            },
        )

        await self.client.upsert(
            collection_name=self.collection,
            points=[point],
        )

        logger.debug("stored_memory_vector", id=memory.id)
        return memory.id

    async def search(
        self,
        query_vector: list[float],
        limit: int = 10,
        memory_types: list[MemoryType] | None = None,
        domains: list[str] | None = None,
        min_importance: float = 0.0,
        include_superseded: bool = False,
        session_id: str | None = None,
        since: str | None = None,
        until: str | None = None,
        username: str | None = None,
    ) -> list[tuple[str, float, dict[str, Any]]]:
        """
        Search for similar memories.

        Returns list of (memory_id, similarity_score, payload).
        """
        # Build filter conditions
        conditions = []

        if username:
            conditions.append(
                FieldCondition(
                    key="username",
                    match=MatchValue(value=username),
                )
            )

        if memory_types:
            conditions.append(
                FieldCondition(
                    key="memory_type",
                    match=MatchAny(any=[t.value for t in memory_types]),
                )
            )

        if domains:
            conditions.append(
                FieldCondition(
                    key="domain",
                    match=MatchAny(any=domains),
                )
            )

        if min_importance > 0:
            conditions.append(
                FieldCondition(
                    key="importance",
                    range=Range(gte=min_importance),
                )
            )

        if not include_superseded:
            conditions.append(
                IsNullCondition(
                    is_null=PayloadField(key="superseded_by"),
                )
            )

        if session_id:
            conditions.append(
                FieldCondition(
                    key="session_id",
                    match=MatchValue(value=session_id),
                )
            )

        if since:
            conditions.append(
                FieldCondition(key="created_at", range=DatetimeRange(gte=since))
            )

        if until:
            conditions.append(
                FieldCondition(key="created_at", range=DatetimeRange(lte=until))
            )

        search_filter = Filter(must=conditions) if conditions else None

        results = await self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            limit=limit,
            query_filter=search_filter,
            with_payload=True,
        )

        return [
            (str(r.id), r.score, r.payload)
            for r in results.points
        ]

    async def get(self, memory_id: str) -> tuple[list[float], dict[str, Any]] | None:
        """Get a memory by ID, returning (embedding, payload)."""
        results = await self.client.retrieve(
            collection_name=self.collection,
            ids=[memory_id],
            with_vectors=True,
            with_payload=True,
        )

        if results:
            point = results[0]
            return point.vector, point.payload
        return None

    async def find_by_content_hash(self, hash_value: str) -> str | None:
        """Find a memory by content_hash. Returns memory_id or None."""
        results, _ = await self.client.scroll(
            collection_name=self.collection,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="content_hash",
                        match=MatchValue(value=hash_value),
                    ),
                ]
            ),
            limit=1,
            with_payload=False,
        )
        if results:
            return str(results[0].id)
        return None

    async def update_importance(self, memory_id: str, importance: float):
        """Update the importance score of a memory."""
        await self.client.set_payload(
            collection_name=self.collection,
            payload={"importance": importance},
            points=[memory_id],
        )

    async def update_pinned(self, memory_id: str, pinned: bool):
        """Update the pinned status of a memory."""
        await self.client.set_payload(
            collection_name=self.collection,
            payload={"pinned": "true" if pinned else "false"},
            points=[memory_id],
        )

    async def update_stability(self, memory_id: str, stability: float):
        """Update the stability score of a memory."""
        await self.client.set_payload(
            collection_name=self.collection,
            payload={"stability": stability},
            points=[memory_id],
        )

    async def update_access(self, memory_id: str, access_count: int, last_accessed: str):
        """Update access tracking for a memory."""
        await self.client.set_payload(
            collection_name=self.collection,
            payload={
                "access_count": access_count,
                "last_accessed": last_accessed,
            },
            points=[memory_id],
        )

    async def update_durability(self, memory_id: str, durability: str | None):
        """Update the durability classification of a memory."""
        await self.client.set_payload(
            collection_name=self.collection,
            payload={"durability": durability},
            points=[memory_id],
        )

    async def count_pinned(self) -> int:
        """Count pinned memories."""
        result = await self.client.count(
            collection_name=self.collection,
            count_filter=Filter(
                must=[
                    FieldCondition(
                        key="pinned",
                        match=MatchValue(value="true"),
                    )
                ]
            ),
        )
        return result.count

    async def get_importance_distribution(self) -> list[dict[str, Any]]:
        """Get count of memories in importance bands."""
        bands = []
        ranges = [
            ("0.0-0.2", 0.0, 0.2),
            ("0.2-0.4", 0.2, 0.4),
            ("0.4-0.6", 0.4, 0.6),
            ("0.6-0.8", 0.6, 0.8),
            ("0.8-1.0", 0.8, 1.01),
        ]
        for label, low, high in ranges:
            result = await self.client.count(
                collection_name=self.collection,
                count_filter=Filter(
                    must=[
                        FieldCondition(
                            key="importance",
                            range=Range(gte=low, lt=high),
                        )
                    ]
                ),
            )
            bands.append({"range": label, "count": result.count})
        return bands

    async def scroll_by_document_id(
        self, doc_id: str,
    ) -> list[tuple[str, dict[str, Any]]]:
        """Scroll all memories belonging to a document."""
        all_points = []
        offset = None
        while True:
            points, next_offset = await self.client.scroll(
                collection_name=self.collection,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=doc_id),
                        )
                    ]
                ),
                limit=100,
                offset=offset,
                with_payload=True,
            )
            for point in points:
                all_points.append((str(point.id), point.payload or {}))
            if next_offset is None:
                break
            offset = next_offset
        return all_points

    async def mark_superseded(self, memory_id: str, superseded_by: str):
        """Mark a memory as superseded by another."""
        await self.client.set_payload(
            collection_name=self.collection,
            payload={"superseded_by": superseded_by},
            points=[memory_id],
        )

    async def delete(self, memory_id: str):
        """Delete a memory from the vector store."""
        await self.client.delete(
            collection_name=self.collection,
            points_selector=[memory_id],
        )

    async def scroll_all(
        self,
        include_superseded: bool = False,
        batch_size: int = 100,
        with_vectors: bool = False,
    ) -> list[tuple[str, dict[str, Any]]]:
        """
        Iterate over ALL points using Qdrant scroll API.

        Returns list of (memory_id, payload). Unlike search(), this is
        unbiased and not capped — every point is returned.
        """
        conditions = []
        if not include_superseded:
            conditions.append(
                IsNullCondition(
                    is_null=PayloadField(key="superseded_by"),
                )
            )

        scroll_filter = Filter(must=conditions) if conditions else None
        all_points = []
        offset = None

        while True:
            points, next_offset = await self.client.scroll(
                collection_name=self.collection,
                scroll_filter=scroll_filter,
                limit=batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=with_vectors,
            )

            for point in points:
                payload = point.payload or {}
                vector = point.vector if with_vectors else None
                if with_vectors:
                    all_points.append((str(point.id), payload, vector))
                else:
                    all_points.append((str(point.id), payload))

            if next_offset is None:
                break
            offset = next_offset

        return all_points

    async def scroll_around(
        self,
        anchor_date: str,
        before: int,
        after: int,
        domain: str | None = None,
        memory_type: str | None = None,
    ) -> list[tuple[str, dict[str, Any]]]:
        """
        Scroll memories around an anchor date for timeline view.

        Returns (before + after) entries sorted by created_at.
        """
        base_conditions = []
        if domain:
            base_conditions.append(
                FieldCondition(key="domain", match=MatchValue(value=domain))
            )
        if memory_type:
            base_conditions.append(
                FieldCondition(key="memory_type", match=MatchValue(value=memory_type))
            )
        base_conditions.append(
            IsNullCondition(is_null=PayloadField(key="superseded_by"))
        )

        results = []

        # Get entries BEFORE anchor (lte)
        # Overscan and sort in Python for version compatibility
        if before > 0:
            before_conditions = base_conditions + [
                FieldCondition(key="created_at", range=DatetimeRange(lte=anchor_date))
            ]
            before_points = []
            offset = None
            fetch_limit = min(before * 3, 200)  # Overscan to get closest entries
            while len(before_points) < fetch_limit:
                batch, next_offset = await self.client.scroll(
                    collection_name=self.collection,
                    scroll_filter=Filter(must=before_conditions),
                    limit=min(100, fetch_limit - len(before_points)),
                    offset=offset,
                    with_payload=True,
                )
                for p in batch:
                    before_points.append((str(p.id), p.payload or {}))
                if next_offset is None or not batch:
                    break
                offset = next_offset

            # Sort desc by created_at, take closest N to anchor
            before_points.sort(key=lambda x: x[1].get("created_at", ""), reverse=True)
            results.extend(before_points[:before])

        # Get entries AFTER anchor (gt)
        if after > 0:
            after_conditions = base_conditions + [
                FieldCondition(key="created_at", range=DatetimeRange(gt=anchor_date))
            ]
            after_points = []
            offset = None
            fetch_limit = min(after * 3, 200)
            while len(after_points) < fetch_limit:
                batch, next_offset = await self.client.scroll(
                    collection_name=self.collection,
                    scroll_filter=Filter(must=after_conditions),
                    limit=min(100, fetch_limit - len(after_points)),
                    offset=offset,
                    with_payload=True,
                )
                for p in batch:
                    after_points.append((str(p.id), p.payload or {}))
                if next_offset is None or not batch:
                    break
                offset = next_offset

            # Sort asc by created_at, take closest N to anchor
            after_points.sort(key=lambda x: x[1].get("created_at", ""))
            results.extend(after_points[:after])

        # Final sort by created_at
        results.sort(key=lambda x: x[1].get("created_at", ""))
        return results

    # --- Facts collection methods (sub-embeddings) ---

    async def ensure_facts_collection(self):
        """Create the facts sub-embedding collection if it doesn't exist."""
        self.facts_collection = f"{self.collection}_facts"
        collections = await self.client.get_collections()
        exists = any(c.name == self.facts_collection for c in collections.collections)

        if not exists:
            await self.client.create_collection(
                collection_name=self.facts_collection,
                vectors_config=VectorParams(
                    size=self.settings.embedding_dimensions,
                    distance=Distance.COSINE,
                ),
            )
            # Create indexes
            for field_name, field_type in [
                ("parent_id", "keyword"),
                ("domain", "keyword"),
                ("created_at", "datetime"),
            ]:
                try:
                    await self.client.create_payload_index(
                        collection_name=self.facts_collection,
                        field_name=field_name,
                        field_schema=field_type,
                    )
                except Exception:
                    pass
            logger.info("created_facts_collection", name=self.facts_collection)

    async def store_fact(
        self, parent_id: str, fact_content: str, fact_index: int,
        embedding: list[float], domain: str = "general",
    ) -> str:
        """Store a single fact sub-embedding linked to a parent memory."""
        from src.core.models import generate_id

        fact_id = generate_id()
        point = PointStruct(
            id=fact_id,
            vector=embedding,
            payload={
                "parent_id": parent_id,
                "fact_content": fact_content,
                "fact_index": fact_index,
                "domain": domain,
                "created_at": __import__("datetime").datetime.utcnow().isoformat(),
            },
        )
        await self.client.upsert(
            collection_name=self.facts_collection,
            points=[point],
        )
        return fact_id

    async def search_facts(
        self, query_vector: list[float], limit: int = 10,
        domain: str | None = None,
    ) -> list[tuple[str, float, dict[str, Any]]]:
        """Search the facts collection for matching sub-embeddings."""
        conditions = []
        if domain:
            conditions.append(
                FieldCondition(key="domain", match=MatchValue(value=domain))
            )
        search_filter = Filter(must=conditions) if conditions else None

        results = await self.client.query_points(
            collection_name=self.facts_collection,
            query=query_vector,
            limit=limit,
            query_filter=search_filter,
            with_payload=True,
        )
        return [
            (str(r.id), r.score, r.payload)
            for r in results.points
        ]

    async def delete_facts_for_memory(self, parent_id: str):
        """Delete all facts linked to a parent memory."""
        await self.client.delete(
            collection_name=self.facts_collection,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="parent_id",
                        match=MatchValue(value=parent_id),
                    )
                ]
            ),
        )

    async def count_facts(self) -> int:
        """Get total number of facts in the sub-embedding collection."""
        try:
            info = await self.client.get_collection(self.facts_collection)
            return info.points_count
        except Exception:
            return 0

    # --- Anti-patterns collection methods ---

    async def ensure_anti_patterns_collection(self):
        """Create the anti-patterns collection if it doesn't exist."""
        self.anti_patterns_collection = f"{self.collection}_anti_patterns"
        collections = await self.client.get_collections()
        exists = any(c.name == self.anti_patterns_collection for c in collections.collections)

        if not exists:
            await self.client.create_collection(
                collection_name=self.anti_patterns_collection,
                vectors_config=VectorParams(
                    size=self.settings.embedding_dimensions,
                    distance=Distance.COSINE,
                ),
            )
            for field_name, field_type in [
                ("domain", "keyword"),
                ("severity", "keyword"),
                ("created_at", "datetime"),
            ]:
                try:
                    await self.client.create_payload_index(
                        collection_name=self.anti_patterns_collection,
                        field_name=field_name,
                        field_schema=field_type,
                    )
                except Exception:
                    pass
            logger.info("created_anti_patterns_collection", name=self.anti_patterns_collection)

    async def store_anti_pattern(self, anti_pattern, embedding: list[float]) -> str:
        """Store an anti-pattern with its embedding."""
        point = PointStruct(
            id=anti_pattern.id,
            vector=embedding,
            payload={
                "pattern": anti_pattern.pattern,
                "warning": anti_pattern.warning,
                "alternative": anti_pattern.alternative,
                "severity": anti_pattern.severity,
                "domain": anti_pattern.domain,
                "tags": anti_pattern.tags,
                "times_triggered": anti_pattern.times_triggered,
                "created_at": anti_pattern.created_at.isoformat(),
                "user_id": anti_pattern.user_id,
                "username": anti_pattern.username,
            },
        )
        await self.client.upsert(
            collection_name=self.anti_patterns_collection,
            points=[point],
        )
        return anti_pattern.id

    async def search_anti_patterns(
        self, query_vector: list[float], limit: int = 5, domain: str | None = None,
    ) -> list[tuple[str, float, dict[str, Any]]]:
        """Search anti-patterns by embedding similarity."""
        conditions = []
        if domain:
            conditions.append(
                FieldCondition(key="domain", match=MatchValue(value=domain))
            )
        search_filter = Filter(must=conditions) if conditions else None

        results = await self.client.query_points(
            collection_name=self.anti_patterns_collection,
            query=query_vector,
            limit=limit,
            query_filter=search_filter,
            with_payload=True,
        )
        return [(str(r.id), r.score, r.payload) for r in results.points]

    async def get_anti_pattern(self, anti_pattern_id: str):
        """Get an anti-pattern by ID."""
        results = await self.client.retrieve(
            collection_name=self.anti_patterns_collection,
            ids=[anti_pattern_id],
            with_vectors=True,
            with_payload=True,
        )
        if results:
            point = results[0]
            return point.vector, point.payload
        return None

    async def delete_anti_pattern(self, anti_pattern_id: str):
        """Delete an anti-pattern."""
        await self.client.delete(
            collection_name=self.anti_patterns_collection,
            points_selector=[anti_pattern_id],
        )

    async def scroll_anti_patterns(
        self, domain: str | None = None,
    ) -> list[tuple[str, dict[str, Any]]]:
        """Scroll all anti-patterns."""
        conditions = []
        if domain:
            conditions.append(
                FieldCondition(key="domain", match=MatchValue(value=domain))
            )
        scroll_filter = Filter(must=conditions) if conditions else None
        all_points = []
        offset = None

        while True:
            points, next_offset = await self.client.scroll(
                collection_name=self.anti_patterns_collection,
                scroll_filter=scroll_filter,
                limit=100,
                offset=offset,
                with_payload=True,
            )
            for point in points:
                all_points.append((str(point.id), point.payload or {}))
            if next_offset is None:
                break
            offset = next_offset

        return all_points

    async def increment_triggered(self, anti_pattern_id: str):
        """Increment times_triggered for an anti-pattern."""
        result = await self.get_anti_pattern(anti_pattern_id)
        if result:
            _, payload = result
            count = payload.get("times_triggered", 0) + 1
            await self.client.set_payload(
                collection_name=self.anti_patterns_collection,
                payload={"times_triggered": count},
                points=[anti_pattern_id],
            )

    async def count(self) -> int:
        """Get total number of memories."""
        info = await self.client.get_collection(self.collection)
        return info.points_count

    async def close(self):
        """Close the connection."""
        if self.client:
            await self.client.close()


# Singleton
_store: QdrantStore | None = None


async def get_qdrant_store() -> QdrantStore:
    """Get or create Qdrant store singleton."""
    global _store
    if _store is None:
        _store = QdrantStore()
        await _store.connect()
    return _store
