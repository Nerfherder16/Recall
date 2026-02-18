"""
Auto-linker — creates RELATED_TO edges when a memory is stored.

Searches for the top-3 most similar existing memories and creates
RELATED_TO edges via neo4j.strengthen_relationship().
"""

import structlog

from src.storage import get_neo4j_store, get_qdrant_store

logger = structlog.get_logger()

SIMILARITY_THRESHOLD = 0.5
MAX_LINKS = 3


async def auto_link_memory(
    memory_id: str,
    embedding: list[float],
    domain: str | None = None,
) -> int:
    """
    Find similar memories and create RELATED_TO edges.

    Args:
        memory_id: The newly stored memory's ID.
        embedding: The memory's embedding vector.
        domain: Optional domain filter for narrower matches.

    Returns:
        Number of edges created.
    """
    try:
        qdrant = await get_qdrant_store()
        neo4j = await get_neo4j_store()

        # Search for similar memories
        results = await qdrant.search(
            query_vector=embedding,
            limit=MAX_LINKS + 1,  # Extra to account for self
        )

        edges_created = 0
        for candidate_id, similarity, payload in results:
            # Skip self
            if candidate_id == memory_id:
                continue

            # Must exceed similarity threshold
            if similarity < SIMILARITY_THRESHOLD:
                continue

            # Create/strengthen RELATED_TO edge
            # Initial strength proportional to similarity
            initial_strength = similarity * 0.5
            await neo4j.strengthen_relationship(
                source_id=memory_id,
                target_id=candidate_id,
                increment=initial_strength,
            )
            edges_created += 1

            if edges_created >= MAX_LINKS:
                break

        if edges_created > 0:
            logger.info(
                "auto_linked",
                memory_id=memory_id,
                edges_created=edges_created,
            )

        return edges_created

    except Exception as e:
        logger.error(
            "auto_link_error",
            memory_id=memory_id,
            error=str(e),
        )
        return 0
