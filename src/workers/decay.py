"""
Memory decay worker.

Implements the "forgetting curve" - memories lose importance over time
unless they are accessed (reinforced), have high stability, or have
positive feedback history.

v2.8: Added access frequency and feedback ratio modifiers.
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
        effective_decay = base * (1 - stability) * access_mod * feedback_mod
        new_importance = importance * (1 - effective_decay) ^ hours

    Modifiers:
    - stability: high stability = slow decay (existing)
    - access_modifier: frequently accessed = slow decay (v2.8)
    - feedback_modifier: useful memories = slow decay (v2.8)
    - durability: permanent=immune, durable=0.15x (existing)
    - pinned: immune (existing)
    """

    def __init__(self, qdrant_store, neo4j_store):
        self.qdrant = qdrant_store
        self.neo4j = neo4j_store
        self.settings = get_settings()

    async def run(
        self,
        hours_offset: float = 0.0,
        feedback_stats: dict[str, dict[str, int]] | None = None,
    ) -> dict[str, Any]:
        """
        Run decay on all memories.

        Args:
            hours_offset: Extra hours to simulate time passing.
            feedback_stats: Pre-loaded per-memory feedback counts.
                If None, attempts to load from Postgres.

        Returns statistics about the decay run.
        """
        stats = {
            "processed": 0,
            "decayed": 0,
            "archived": 0,
            "stable": 0,
        }

        # Load feedback stats once for the entire run
        if feedback_stats is None:
            feedback_stats = await self._load_feedback_stats()

        # Scroll through ALL memories (unbiased, no limit)
        results = await self.qdrant.scroll_all(
            include_superseded=False,
        )

        now = datetime.utcnow()
        archive_threshold = 0.05
        base_decay_rate = self.settings.importance_decay_rate

        for memory_id, payload in results:
            stats["processed"] += 1

            # Pinned memories are immune to decay
            if payload.get("pinned") == "true":
                stats["stable"] += 1
                continue

            # Permanent memories never decay
            durability = payload.get("durability")
            if durability == "permanent":
                stats["stable"] += 1
                continue

            # Null durability defaults to durable (safe default)
            if durability is None:
                durability = "durable"

            importance = payload.get("importance", 0.5)
            stability = payload.get("stability", 0.1)
            last_accessed_str = payload.get("last_accessed")
            access_count = payload.get("access_count", 0)

            if not last_accessed_str:
                continue

            last_accessed = datetime.fromisoformat(
                last_accessed_str,
            )
            hours_since = (now - last_accessed).total_seconds() / 3600 + hours_offset

            # Base decay modulated by stability
            effective_decay = base_decay_rate * (1 - stability)

            # Access frequency: more accesses = slower decay
            # 10 accesses → 0.5x, 20 → 0.33x, 0 → 1.0x
            access_mod = 1.0 / (1.0 + 0.1 * access_count)
            effective_decay *= access_mod

            # Feedback ratio: useful memories decay slower
            fb = feedback_stats.get(memory_id)
            if fb:
                useful = fb.get("useful", 0)
                not_useful = fb.get("not_useful", 0)
                total_fb = useful + not_useful
                if total_fb > 0:
                    ratio = useful / total_fb
                    # 100% useful → 0.5x decay, 0% → 1.0x
                    feedback_mod = 1.0 - (0.5 * ratio)
                    effective_decay *= feedback_mod

            # Durable memories decay 85% slower
            if durability == "durable":
                effective_decay *= 0.15

            # Apply decay
            new_importance = importance * ((1 - effective_decay) ** hours_since)

            # Clamp to minimum — floor at 0.05 so memories never become invisible
            new_importance = max(0.05, new_importance)

            if abs(new_importance - importance) > 0.001:
                await self.qdrant.update_importance(
                    memory_id,
                    new_importance,
                )
                await self.neo4j.update_importance(
                    memory_id,
                    new_importance,
                )
                stats["decayed"] += 1

                # Archive audit on significant decay
                if new_importance < archive_threshold and stability < 0.3:
                    stats["archived"] += 1
                    try:
                        from src.storage import get_postgres_store

                        pg = await get_postgres_store()
                        await pg.log_audit(
                            "decay",
                            memory_id,
                            actor="decay",
                            details={
                                "old_importance": round(
                                    importance,
                                    4,
                                ),
                                "new_importance": round(
                                    new_importance,
                                    4,
                                ),
                            },
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

    async def _load_feedback_stats(
        self,
    ) -> dict[str, dict[str, int]]:
        """Load per-memory feedback stats from Postgres.

        Returns empty dict on any failure (graceful degradation).
        """
        try:
            from src.storage import get_postgres_store

            pg = await get_postgres_store()
            return await pg.get_all_memory_feedback_stats()
        except Exception as e:
            logger.debug(
                "decay_feedback_stats_unavailable",
                error=str(e),
            )
            return {}


async def apply_decay_to_memory(
    memory_id: str,
    qdrant_store,
    neo4j_store,
    hours_since_access: float,
    current_importance: float,
    stability: float,
    access_count: int = 0,
    durability: str | None = None,
    feedback_stats: dict[str, int] | None = None,
) -> float:
    """
    Apply decay to a single memory and return new importance.

    Mirrors the full DecayWorker.run() formula including v2.8
    access/feedback/durability modifiers.
    """
    settings = get_settings()
    base_decay_rate = settings.importance_decay_rate

    # Stability reduces decay rate
    effective_decay = base_decay_rate * (1 - stability)

    # Access frequency modifier (v2.8)
    access_mod = 1.0 / (1.0 + 0.1 * access_count)
    effective_decay *= access_mod

    # Feedback ratio modifier (v2.8)
    if feedback_stats:
        useful = feedback_stats.get("useful", 0)
        not_useful = feedback_stats.get("not_useful", 0)
        total_fb = useful + not_useful
        if total_fb > 0:
            feedback_mod = 1.0 - (0.5 * (useful / total_fb))
            effective_decay *= feedback_mod

    # Durability modifier
    if durability == "durable" or durability is None:
        effective_decay *= 0.15

    # Apply exponential decay
    new_importance = current_importance * ((1 - effective_decay) ** hours_since_access)
    new_importance = max(0.05, new_importance)

    if abs(new_importance - current_importance) > 0.001:
        await qdrant_store.update_importance(
            memory_id,
            new_importance,
        )
        await neo4j_store.update_importance(
            memory_id,
            new_importance,
        )

    return new_importance
