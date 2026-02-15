"""
Neo4j graph storage for memory relationships.

Neo4j handles:
- Storing relationships between memories
- Graph traversal queries
- Finding connected concepts
"""

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
                    m.content_preview = $preview
                """,
                id=memory.id,
                memory_type=memory.memory_type.value,
                domain=memory.domain,
                importance=memory.importance,
                created_at=memory.created_at.isoformat(),
                preview=memory.content[:100] if memory.content else "",
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
                    [rel in relationships(path) | type(rel)] as rel_types
                ORDER BY distance, related.importance DESC
                LIMIT $limit
                """,
                id=memory_id,
                limit=limit,
            )

            records = await result.data()
            return records

    async def find_path(
        self, source_id: str, target_id: str, max_depth: int = 5
    ) -> list[dict[str, Any]] | None:
        """Find shortest path between two memories."""
        # Clamp max_depth to a safe range (Cypher literal, not parameterized)
        max_depth = max(1, min(max_depth, 15))

        async with self.driver.session() as session:
            result = await session.run(
                f"""
                MATCH path = shortestPath(
                    (source:Memory {{id: $source_id}})-[*..{max_depth}]-(target:Memory {{id: $target_id}})
                )
                RETURN [node in nodes(path) | node.id] as node_ids,
                       [rel in relationships(path) | type(rel)] as rel_types,
                       length(path) as distance
                """,
                source_id=source_id,
                target_id=target_id,
            )

            record = await result.single()
            if record:
                return {
                    "node_ids": record["node_ids"],
                    "relationship_types": record["rel_types"],
                    "distance": record["distance"],
                }
            return None

    async def get_subgraph(
        self,
        memory_ids: list[str],
        include_relationships: bool = True,
    ) -> dict[str, Any]:
        """Get a subgraph containing specified memories and their connections."""
        async with self.driver.session() as session:
            result = await session.run(
                """
                MATCH (m:Memory)
                WHERE m.id IN $ids
                OPTIONAL MATCH (m)-[r]-(connected:Memory)
                WHERE connected.id IN $ids
                RETURN collect(DISTINCT m) as memories,
                       collect(DISTINCT r) as relationships
                """,
                ids=memory_ids,
            )

            record = await result.single()
            if record:
                return {
                    "memories": [dict(m) for m in record["memories"]],
                    "relationships": [
                        {
                            "type": type(r).__name__,
                            "strength": r.get("strength", 0.5),
                        }
                        for r in record["relationships"]
                        if r is not None
                    ],
                }
            return {"memories": [], "relationships": []}

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

    async def get_statistics(self) -> dict[str, Any]:
        """Get graph statistics."""
        async with self.driver.session() as session:
            result = await session.run(
                """
                MATCH (m:Memory)
                OPTIONAL MATCH ()-[r]->()
                RETURN count(DISTINCT m) as memory_count,
                       count(DISTINCT r) as relationship_count
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


async def get_neo4j_store() -> Neo4jStore:
    """Get or create Neo4j store singleton."""
    global _store
    if _store is None:
        _store = Neo4jStore()
        await _store.connect()
    return _store
