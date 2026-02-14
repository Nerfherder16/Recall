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

    async def _ensure_indexes(self):
        """Create indexes for efficient filtering."""
        indexes = [
            ("memory_type", "keyword"),
            ("domain", "keyword"),
            ("source", "keyword"),
            ("session_id", "keyword"),
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
    ) -> list[tuple[str, float, dict[str, Any]]]:
        """
        Search for similar memories.

        Returns list of (memory_id, similarity_score, payload).
        """
        # Build filter conditions
        conditions = []

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

    async def update_importance(self, memory_id: str, importance: float):
        """Update the importance score of a memory."""
        await self.client.set_payload(
            collection_name=self.collection,
            payload={"importance": importance},
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
