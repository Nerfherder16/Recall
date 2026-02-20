"""
Neo4j graph storage for memory relationships.

Neo4j handles:
- Storing relationships between memories
- Graph traversal queries
- Finding connected concepts
"""

import asyncio
import re
from typing import Any

import structlog
from neo4j import AsyncGraphDatabase

from src.core import Memory, Relationship, RelationshipType, get_settings

logger = structlog.get_logger()


class Neo4jStore:
    """Graph storage using Neo4j."""

    def __init__(self):
        self.settings = get_settings()
        self.driver = None

    async def connect(self):
        """Initialize connection to Neo4j."""
        self.driver = AsyncGraphDatabase.driver(
            self.settings.neo4j_uri,
            auth=(self.settings.neo4j_user, self.settings.neo4j_password),
        )

        # Verify connection and create constraints
        async with self.driver.session() as session:
            # Create uniqueness constraint on Memory id
            await session.run(
                """
                CREATE CONSTRAINT memory_id IF NOT EXISTS
                FOR (m:Memory) REQUIRE m.id IS UNIQUE
                """
            )

            # Create index on memory_type for filtering
            await session.run(
                """
                CREATE INDEX memory_type_idx IF NOT EXISTS
                FOR (m:Memory) ON (m.memory_type)
                """
            )

            # Create index on domain
            await session.run(
                """
                CREATE INDEX memory_domain_idx IF NOT EXISTS
                FOR (m:Memory) ON (m.domain)
                """
            )

            # Create index on user_id
            await session.run(
                """
                CREATE INDEX memory_user_id_idx IF NOT EXISTS
                FOR (m:Memory) ON (m.user_id)
                """
            )

            # Document constraints
            await session.run(
                """
                CREATE CONSTRAINT document_id IF NOT EXISTS
                FOR (d:Document) REQUIRE d.id IS UNIQUE
                """
            )
            await session.run(
                """
                CREATE INDEX document_domain_idx IF NOT EXISTS
                FOR (d:Document) ON (d.domain)
                """
            )

        logger.info("connected_to_neo4j")

    async def create_memory_node(self, memory: Memory):
        """
        Create a node for a memory.

        The node stores metadata for graph queries.
        Full content is in Qdrant.
        """
        async with self.driver.session() as session:
            await session.run(
                """
                MERGE (m:Memory {id: $id})
                SET m.memory_type = $memory_type,
                    m.domain = $domain,
                    m.importance = $importance,
                    m.created_at = $created_at,
                    m.content_preview = $preview,
                    m.user_id = $user_id,
                    m.pinned = $pinned,
                    m.stability = $stability,
                    m.durability = $durability,
                    m.initial_importance = $initial_importance
                """,
                id=memory.id,
                memory_type=memory.memory_type.value,
                domain=memory.domain,
                importance=memory.importance,
                created_at=memory.created_at.isoformat(),
                preview=memory.content[:100] if memory.content else "",
                user_id=memory.user_id,
                pinned=memory.pinned,
                stability=memory.stability,
                durability=memory.durability.value if memory.durability else None,
                initial_importance=memory.initial_importance,
            )

        logger.debug("created_memory_node", id=memory.id)

    @staticmethod
    def _safe_rel_type(value: str) -> str:
        """Validate relationship type is safe for Cypher interpolation."""
        upper = value.upper()
        if not re.match(r"^[A-Z_][A-Z0-9_]*$", upper):
            raise ValueError(f"Invalid relationship type for Cypher: {value!r}")
        return upper

    async def create_relationship(self, relationship: Relationship):
        """Create a relationship between two memories."""
        async with self.driver.session() as session:
            # Map relationship type to Neo4j relationship type
            rel_type = self._safe_rel_type(relationship.relationship_type.value)

            await session.run(
                f"""
                MATCH (source:Memory {{id: $source_id}})
                MATCH (target:Memory {{id: $target_id}})
                MERGE (source)-[r:{rel_type}]->(target)
                SET r.id = $rel_id,
                    r.strength = $strength,
                    r.created_at = $created_at
                """,
                source_id=relationship.source_id,
                target_id=relationship.target_id,
                rel_id=relationship.id,
                strength=relationship.strength,
                created_at=relationship.created_at.isoformat(),
            )

            # If bidirectional, create reverse edge
            if relationship.bidirectional:
                await session.run(
                    f"""
                    MATCH (source:Memory {{id: $source_id}})
                    MATCH (target:Memory {{id: $target_id}})
                    MERGE (target)-[r:{rel_type}]->(source)
                    SET r.strength = $strength,
                        r.created_at = $created_at
                    """,
                    source_id=relationship.source_id,
                    target_id=relationship.target_id,
                    strength=relationship.strength,
                    created_at=relationship.created_at.isoformat(),
                )

        logger.debug(
            "created_relationship",
            source=relationship.source_id,
            target=relationship.target_id,
            type=relationship.relationship_type.value,
        )

    async def strengthen_relationship(
        self, source_id: str, target_id: str, increment: float = 0.05
    ):
        """Increment edge strength between two memories (creates if missing)."""
        async with self.driver.session() as session:
            await session.run(
                """
                MATCH (a:Memory {id: $source_id}), (b:Memory {id: $target_id})
                MERGE (a)-[r:RELATED_TO]-(b)
                ON CREATE SET r.strength = 0.5 + $increment,
                              r.created_at = datetime()
                ON MATCH SET r.strength = CASE
                    WHEN r.strength + $increment > 1.0 THEN 1.0
                    ELSE r.strength + $increment
                END
                """,
                source_id=source_id,
                target_id=target_id,
                increment=increment,
            )
        logger.debug(
            "strengthened_relationship",
            source=source_id,
            target=target_id,
            increment=increment,
        )

    async def find_related(
        self,
        memory_id: str,
        relationship_types: list[RelationshipType] | None = None,
        max_depth: int = 2,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Find memories related to a given memory.

        Returns list of {id, relationship_type, distance, path}.
        """
        # Clamp max_depth to prevent combinatorial explosion in Cypher
        max_depth = max(1, min(max_depth, 10))

        async with self.driver.session() as session:
            if relationship_types:
                rel_filter = "|".join(self._safe_rel_type(rt.value) for rt in relationship_types)
                rel_pattern = f"[r:{rel_filter}*1..{max_depth}]"
            else:
                rel_pattern = f"[r*1..{max_depth}]"

            result = await session.run(
                f"""
                MATCH path = (start:Memory {{id: $id}})-{rel_pattern}-(related:Memory)
                WHERE start <> related AND related.superseded_by IS NULL
                RETURN DISTINCT
                    related.id as id,
                    related.memory_type as memory_type,
                    related.domain as domain,
                    related.importance as importance,
                    length(path) as distance,
                    [rel in relationships(path) | type(rel)] as rel_types,
                    [rel in relationships(path) | coalesce(rel.strength, 0.5)] as rel_strengths
                ORDER BY distance, related.importance DESC
                LIMIT $limit
                """,
                id=memory_id,
                limit=limit,
            )

            records = await result.data()
            return records

    async def find_contradictions(self, memory_ids: list[str]) -> list[tuple[str, str]]:
        """
        Find CONTRADICTS edges between a set of memory IDs.

        Returns list of (id_a, id_b) pairs that contradict each other.
        """
        if len(memory_ids) < 2:
            return []

        async with self.driver.session() as session:
            result = await session.run(
                """
                MATCH (a:Memory)-[:CONTRADICTS]-(b:Memory)
                WHERE a.id IN $ids AND b.id IN $ids AND a.id < b.id
                RETURN a.id AS id_a, b.id AS id_b
                """,
                ids=memory_ids,
            )
            records = await result.data()
            return [(r["id_a"], r["id_b"]) for r in records]

    async def mark_superseded(self, memory_id: str, superseded_by: str):
        """Mark a memory node as superseded in the graph."""
        async with self.driver.session() as session:
            await session.run(
                """
                MATCH (m:Memory {id: $id})
                SET m.superseded_by = $superseded_by,
                    m.importance = 0.0
                """,
                id=memory_id,
                superseded_by=superseded_by,
            )

    async def update_importance(self, memory_id: str, importance: float):
        """Update importance in graph node."""
        async with self.driver.session() as session:
            await session.run(
                """
                MATCH (m:Memory {id: $id})
                SET m.importance = $importance
                """,
                id=memory_id,
                importance=importance,
            )

    async def update_pinned(self, memory_id: str, pinned: bool):
        """Update pinned status in graph node."""
        async with self.driver.session() as session:
            await session.run(
                """
                MATCH (m:Memory {id: $id})
                SET m.pinned = $pinned
                """,
                id=memory_id,
                pinned=pinned,
            )

    async def update_durability(self, memory_id: str, durability: str | None):
        """Update durability in graph node."""
        async with self.driver.session() as session:
            await session.run(
                """
                MATCH (m:Memory {id: $id})
                SET m.durability = $durability
                """,
                id=memory_id,
                durability=durability,
            )

    async def get_avg_edge_strength(self) -> tuple[float, int]:
        """Get average RELATED_TO edge strength and count."""
        async with self.driver.session() as session:
            result = await session.run(
                """
                MATCH ()-[r:RELATED_TO]->()
                RETURN avg(coalesce(r.strength, 0.5)) AS avg_strength,
                       count(r) AS edge_count
                """
            )
            record = await result.single()
            if record:
                return (
                    record["avg_strength"] or 0.0,
                    record["edge_count"] or 0,
                )
            return (0.0, 0)

    async def get_bulk_edge_strengths(self, memory_ids: list[str]) -> dict[str, float]:
        """Return total RELATED_TO edge strength for each memory ID."""
        if not memory_ids:
            return {}
        async with self.driver.session() as session:
            result = await session.run(
                """
                UNWIND $ids AS mid
                OPTIONAL MATCH (m:Memory {id: mid})-[r:RELATED_TO]-()
                WITH mid, coalesce(sum(coalesce(r.strength, 0.5)), 0) AS total_strength
                RETURN mid AS id, total_strength
                """,
                ids=memory_ids,
            )
            records = await result.data()
            return {r["id"]: r["total_strength"] for r in records}

    async def get_high_gravity_memories(self, min_strength: float = 2.0) -> list[dict[str, Any]]:
        """Find memories with high total RELATED_TO strength but low importance."""
        async with self.driver.session() as session:
            result = await session.run(
                """
                MATCH (m:Memory)-[r:RELATED_TO]-()
                WHERE m.superseded_by IS NULL
                WITH m, sum(coalesce(r.strength, 0.5)) AS total_strength
                WHERE total_strength >= $min_strength AND m.importance < 0.3
                RETURN m.id AS id, m.importance AS importance,
                       total_strength, m.domain AS domain
                ORDER BY total_strength DESC
                LIMIT 50
                """,
                min_strength=min_strength,
            )
            return await result.data()

    async def update_stability(self, memory_id: str, stability: float):
        """Update stability in graph node."""
        async with self.driver.session() as session:
            await session.run(
                """
                MATCH (m:Memory {id: $id})
                SET m.stability = $stability
                """,
                id=memory_id,
                stability=stability,
            )

    async def delete_memory(self, memory_id: str):
        """Delete a memory node and its relationships."""
        async with self.driver.session() as session:
            await session.run(
                """
                MATCH (m:Memory {id: $id})
                DETACH DELETE m
                """,
                id=memory_id,
            )

    async def get_all_memory_ids(self) -> set[str]:
        """Return the set of all Memory node IDs in the graph."""
        async with self.driver.session() as session:
            result = await session.run("MATCH (m:Memory) RETURN m.id AS id")
            records = await result.data()
            return {r["id"] for r in records}

    async def get_memory_data(self, memory_id: str) -> dict[str, Any] | None:
        """Return {importance, superseded_by} for a single memory node."""
        async with self.driver.session() as session:
            result = await session.run(
                """
                MATCH (m:Memory {id: $id})
                RETURN m.importance AS importance,
                       m.superseded_by AS superseded_by
                """,
                id=memory_id,
            )
            record = await result.single()
            if record:
                return {
                    "importance": record["importance"],
                    "superseded_by": record["superseded_by"],
                }
            return None

    async def get_relationships_for_memory(self, memory_id: str) -> list[dict[str, Any]]:
        """Return all relationships involving a memory (as source or target)."""
        async with self.driver.session() as session:
            result = await session.run(
                """
                MATCH (m:Memory {id: $id})-[r]-(other:Memory)
                RETURN type(r) AS rel_type,
                       r.strength AS strength,
                       startNode(r).id AS source_id,
                       endNode(r).id AS target_id
                """,
                id=memory_id,
            )
            return await result.data()

    async def get_statistics(self) -> dict[str, Any]:
        """Get graph statistics."""
        async with self.driver.session() as session:
            result = await session.run(
                """
                MATCH (m:Memory)
                WITH count(m) AS memory_count
                OPTIONAL MATCH (:Memory)-[r]->(:Memory)
                RETURN memory_count,
                       count(r) AS relationship_count
                """
            )

            record = await result.single()
            return {
                "memories": record["memory_count"],
                "relationships": record["relationship_count"],
            }

    async def close(self):
        """Close the driver."""
        if self.driver:
            await self.driver.close()


# Singleton
_store: Neo4jStore | None = None
_store_lock: asyncio.Lock | None = None


def _get_store_lock() -> asyncio.Lock:
    global _store_lock
    if _store_lock is None:
        _store_lock = asyncio.Lock()
    return _store_lock


async def get_neo4j_store() -> Neo4jStore:
    """Get or create Neo4j store singleton."""
    global _store
    if _store is not None:
        return _store
    async with _get_store_lock():
        if _store is None:
            _store = Neo4jStore()
            await _store.connect()
        return _store
