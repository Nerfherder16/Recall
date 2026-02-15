"""
Memory decay worker.

Implements the "forgetting curve" - memories lose importance over time
unless they are accessed (reinforced) or have high stability.
"""

from datetime import datetime
from typing import Any

import structlog

from src.core import get_settings

logger = structlog.get_logger()


class DecayWorker:
    """
    Apply decay to memory importance.

    The decay formula:
        new_importance = importance * (1 - decay_rate) ^ hours_since_access

    Where decay_rate is reduced by stability:
        effective_decay = base_decay * (1 - stability)

    High stability memories decay slowly.
    Frequently accessed memories stay important.
    """

    def __init__(self, qdrant_store, neo4j_store):
        self.qdrant = qdrant_store
        self.neo4j = neo4j_store
        self.settings = get_settings()

    async def run(self, hours_offset: float = 0.0) -> dict[str, Any]:
        """
        Run decay on all memories.

        Args:
            hours_offset: Extra hours to add to time-since-access, allowing
                          tests to simulate time passing without waiting.

        Returns statistics about the decay run.
        """
        stats = {
            "processed": 0,
            "decayed": 0,
            "archived": 0,
            "stable": 0,
        }

        # Scroll through ALL memories (unbiased, no limit)
        results = await self.qdrant.scroll_all(include_superseded=False)

        now = datetime.utcnow()
        archive_threshold = 0.05
        base_decay_rate = self.settings.importance_decay_rate

        for memory_id, payload in results:
            stats["processed"] += 1

            importance = payload.get("importance", 0.5)
            stability = payload.get("stability", 0.1)
            last_accessed_str = payload.get("last_accessed")

            if not last_accessed_str:
                continue

            last_accessed = datetime.fromisoformat(last_accessed_str)
            hours_since_access = (now - last_accessed).total_seconds() / 3600 + hours_offset

            # Calculate effective decay rate (stability reduces decay)
            effective_decay = base_decay_rate * (1 - stability)

            # Apply decay
            new_importance = importance * ((1 - effective_decay) ** hours_since_access)

            # Clamp to minimum
            new_importance = max(0.01, new_importance)

            if abs(new_importance - importance) > 0.001:
                # Update importance
                await self.qdrant.update_importance(memory_id, new_importance)
                await self.neo4j.update_importance(memory_id, new_importance)
                stats["decayed"] += 1

                # Check if should be archived
                if new_importance < archive_threshold and stability < 0.3:
                    stats["archived"] += 1
                    # Audit log — only on significant decay (crossing archive threshold)
                    try:
                        from src.storage import get_postgres_store
                        pg = await get_postgres_store()
                        await pg.log_audit(
                            "decay", memory_id, actor="decay",
                            details={"old_importance": round(importance, 4), "new_importance": round(new_importance, 4)},
                        )
                    except Exception:
                        pass  # Fire-and-forget
            else:
                stats["stable"] += 1

        logger.info(
            "decay_completed",
            processed=stats["processed"],
            decayed=stats["decayed"],
            archived=stats["archived"],
        )

        return stats


async def apply_decay_to_memory(
    memory_id: str,
    qdrant_store,
    neo4j_store,
    hours_since_access: float,
    current_importance: float,
    stability: float,
) -> float:
    """
    Apply decay to a single memory and return new importance.

    This can be called on-demand for specific memories.
    """
    settings = get_settings()
    base_decay_rate = settings.importance_decay_rate

    # Stability reduces decay rate
    effective_decay = base_decay_rate * (1 - stability)

    # Apply exponential decay
    new_importance = current_importance * ((1 - effective_decay) ** hours_since_access)
    new_importance = max(0.01, new_importance)

    if abs(new_importance - current_importance) > 0.001:
        await qdrant_store.update_importance(memory_id, new_importance)
        await neo4j_store.update_importance(memory_id, new_importance)

    return new_importance
