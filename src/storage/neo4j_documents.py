"""
Neo4j operations for the Document memory system.

Handles Document node CRUD, EXTRACTED_FROM edges, and sibling queries.
"""

from typing import Any

import structlog

from src.core import Document

logger = structlog.get_logger()


class Neo4jDocumentStore:
    """Document-specific Neo4j operations, using a shared driver."""

    def __init__(self, driver):
        self.driver = driver

    async def ensure_constraints(self):
        """Create Document-specific constraints and indexes."""
        async with self.driver.session() as session:
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

    async def create_document_node(self, document: Document):
        """Create a Document node in Neo4j."""
        async with self.driver.session() as session:
            await session.run(
                """
                MERGE (d:Document {id: $id})
                SET d.filename = $filename,
                    d.file_hash = $file_hash,
                    d.file_type = $file_type,
                    d.domain = $domain,
                    d.durability = $durability,
                    d.pinned = $pinned,
                    d.memory_count = $memory_count,
                    d.created_at = $created_at,
                    d.user_id = $user_id,
                    d.username = $username
                """,
                id=document.id,
                filename=document.filename,
                file_hash=document.file_hash,
                file_type=document.file_type,
                domain=document.domain,
                durability=document.durability.value if document.durability else None,
                pinned=document.pinned,
                memory_count=document.memory_count,
                created_at=document.created_at.isoformat(),
                user_id=document.user_id,
                username=document.username,
            )
        logger.debug("created_document_node", id=document.id)

    async def create_extracted_from_edge(self, memory_id: str, doc_id: str):
        """Create an EXTRACTED_FROM edge from memory to document."""
        async with self.driver.session() as session:
            await session.run(
                """
                MATCH (m:Memory {id: $memory_id}), (d:Document {id: $doc_id})
                MERGE (m)-[:EXTRACTED_FROM]->(d)
                """,
                memory_id=memory_id,
                doc_id=doc_id,
            )

    async def delete_document_cascade(self, doc_id: str) -> list[str]:
        """Delete a document and return its child memory IDs for cleanup."""
        async with self.driver.session() as session:
            # Get child memory IDs first
            result = await session.run(
                """
                MATCH (m:Memory)-[:EXTRACTED_FROM]->(d:Document {id: $doc_id})
                RETURN m.id AS memory_id
                """,
                doc_id=doc_id,
            )
            records = [r async for r in result]
            child_ids = [r["memory_id"] for r in records]

            # Delete the document node and all edges
            await session.run(
                """
                MATCH (d:Document {id: $doc_id})
                DETACH DELETE d
                """,
                doc_id=doc_id,
            )

        return child_ids

    async def get_document_children(self, doc_id: str) -> list[str]:
        """Get memory IDs extracted from a document."""
        async with self.driver.session() as session:
            result = await session.run(
                """
                MATCH (m:Memory)-[:EXTRACTED_FROM]->(d:Document {id: $doc_id})
                RETURN m.id AS memory_id
                """,
                doc_id=doc_id,
            )
            records = [r async for r in result]
            return [r["memory_id"] for r in records]

    async def get_document(self, doc_id: str) -> dict[str, Any] | None:
        """Get document properties."""
        async with self.driver.session() as session:
            result = await session.run(
                "MATCH (d:Document {id: $id}) RETURN d",
                id=doc_id,
            )
            record = await result.single()
            if not record:
                return None
            node = record["d"]
            return dict(node)

    _ALLOWED_FIELDS = frozenset({"domain", "durability", "pinned", "memory_count", "filename"})

    async def update_document(self, doc_id: str, **fields):
        """Update document properties."""
        # Validate field names to prevent Cypher injection
        safe_fields = {k: v for k, v in fields.items() if k in self._ALLOWED_FIELDS}
        if not safe_fields:
            return
        set_clauses = ", ".join(f"d.{k} = ${k}" for k in safe_fields)
        async with self.driver.session() as session:
            await session.run(
                f"MATCH (d:Document {{id: $id}}) SET {set_clauses}",
                id=doc_id,
                **safe_fields,
            )

    async def get_document_by_hash(self, file_hash: str) -> dict[str, Any] | None:
        """Look up a document by its file hash (O(1) via index)."""
        async with self.driver.session() as session:
            result = await session.run(
                "MATCH (d:Document {file_hash: $hash}) RETURN d LIMIT 1",
                hash=file_hash,
            )
            record = await result.single()
            if not record:
                return None
            return dict(record["d"])

    async def list_documents(
        self, domain: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """List documents, optionally filtered by domain."""
        if domain:
            query = """
                MATCH (d:Document {domain: $domain})
                RETURN d ORDER BY d.created_at DESC LIMIT $limit
            """
            params = {"domain": domain, "limit": limit}
        else:
            query = """
                MATCH (d:Document)
                RETURN d ORDER BY d.created_at DESC LIMIT $limit
            """
            params = {"limit": limit}

        async with self.driver.session() as session:
            result = await session.run(query, **params)
            records = [r async for r in result]
            return [dict(r["d"]) for r in records]

    async def find_document_siblings(
        self, memory_id: str, doc_id: str, limit: int = 10
    ) -> list[str]:
        """Find sibling memories from the same document."""
        async with self.driver.session() as session:
            result = await session.run(
                """
                MATCH (seed:Memory {id: $seed_id})-[:EXTRACTED_FROM]->(d:Document {id: $doc_id})
                      <-[:EXTRACTED_FROM]-(sibling:Memory)
                WHERE sibling.id <> $seed_id AND sibling.superseded_by IS NULL
                RETURN sibling.id AS memory_id
                LIMIT $limit
                """,
                seed_id=memory_id,
                doc_id=doc_id,
                limit=limit,
            )
            records = [r async for r in result]
            return [r["memory_id"] for r in records]
