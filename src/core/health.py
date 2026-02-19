"""
Health dashboard computation module.

Aggregates system health metrics from Postgres, Neo4j, Qdrant,
and Redis into a unified dashboard view.
"""

import asyncio
import math
from datetime import datetime
from typing import Any

import structlog

from src.core import get_settings
from src.storage import get_neo4j_store, get_postgres_store, get_qdrant_store, get_redis_store

logger = structlog.get_logger()


class HealthComputer:
    """Computes system health metrics for the dashboard."""

    def __init__(self, pg, qdrant, neo4j, redis):
        self.pg = pg
        self.qdrant = qdrant
        self.neo4j = neo4j
        self.redis = redis
        self.settings = get_settings()

    async def compute_dashboard(self) -> dict[str, Any]:
        """Compute the full health dashboard."""
        (
            feedback,
            population,
            graph,
            pins,
            importance,
            similarity_dist,
        ) = await asyncio.gather(
            self._feedback_metrics(),
            self._population_balance(),
            self._graph_cohesion(),
            self._pin_ratio(),
            self._importance_distribution(),
            self._feedback_similarity(),
        )

        return {
            "generated_at": datetime.utcnow().isoformat(),
            "feedback": feedback,
            "population": population,
            "graph": graph,
            "pins": pins,
            "importance_distribution": importance,
            "feedback_similarity": similarity_dist,
        }

    async def compute_forces(self, memory_id: str) -> dict[str, Any]:
        """Compute per-memory force profile."""
        # Get memory data
        result = await self.qdrant.get(memory_id)
        if not result:
            return None

        _, payload = result

        importance = payload.get("importance", 0.5)
        stability = payload.get("stability", 0.1)
        access_count = payload.get("access_count", 0)
        pinned = payload.get("pinned") == "true"
        durability = payload.get("durability")

        # Decay pressure (projected for next 30-min cycle)
        # Mirrors actual decay formula from workers/decay.py
        base_decay = self.settings.importance_decay_rate
        effective_decay = base_decay * (1 - stability)

        # Access frequency modifier: 10 accesses → 0.5x, 20 → 0.33x
        access_mod = 1.0 / (1.0 + 0.1 * access_count)
        effective_decay *= access_mod

        # Feedback modifier: useful memories decay slower
        feedback_entries = await self.pg.get_feedback_for_memory(memory_id)
        useful_count = sum(1 for e in feedback_entries if (e.get("details") or {}).get("useful"))
        not_useful_count = sum(
            1 for e in feedback_entries if (e.get("details") or {}).get("useful") is False
        )
        total_fb = useful_count + not_useful_count
        if total_fb > 0:
            feedback_mod = 1.0 - (0.5 * (useful_count / total_fb))
            effective_decay *= feedback_mod

        if durability == "permanent" or pinned:
            decay_pressure = 0.0
        elif durability == "durable":
            decay_pressure = -(effective_decay * 0.15 * importance)
        else:
            decay_pressure = -(effective_decay * importance)

        # Retrieval lift (diminishing returns — log scale matches other forces)
        retrieval_lift = 0.02 * math.log1p(access_count)

        # Feedback signal (net importance delta from feedback)
        # feedback_entries already loaded above for decay pressure
        feedback_delta = 0.0
        for entry in feedback_entries:
            details = entry.get("details", {})
            if details.get("useful"):
                feedback_delta += 0.05
            elif details.get("useful") is False:
                feedback_delta -= 0.02

        # Co-retrieval gravity (sum of relationship strengths)
        try:
            rels = await self.neo4j.get_relationships_for_memory(memory_id)
            co_retrieval = sum(
                r.get("strength", 0.5)
                for r in rels
                if r.get("rel_type", "").upper() == "RELATED_TO"
            )
            # Normalize to 0-1 range
            co_retrieval = min(co_retrieval / 5.0, 1.0)
        except Exception:
            co_retrieval = 0.0

        # Pin force
        pin_force = 1.0 if pinned else 0.0

        # Durability shield
        durability_shield = 0.0
        if durability == "permanent":
            durability_shield = 1.0
        elif durability == "durable":
            durability_shield = 0.5

        # Importance timeline
        timeline = await self.pg.get_importance_timeline(memory_id)

        return {
            "memory_id": memory_id,
            "current_importance": importance,
            "forces": {
                "decay_pressure": round(decay_pressure, 6),
                "retrieval_lift": round(retrieval_lift, 4),
                "feedback_signal": round(feedback_delta, 4),
                "co_retrieval_gravity": round(co_retrieval, 4),
                "pin_status": pin_force,
                "durability_shield": durability_shield,
            },
            "importance_timeline": timeline,
        }

    async def compute_conflicts(self) -> list[dict[str, Any]]:
        """Detect potential conflicts in the memory system."""
        # Build set of active (non-superseded) memory IDs + payloads for filtering
        active_memories = await self.qdrant.scroll_all(include_superseded=False)
        active_ids = {mid for mid, _ in active_memories}
        active_payloads = {mid: payload for mid, payload in active_memories}

        conflicts = []

        # Noisy memories (excessive negative feedback)
        noisy = await self.pg.get_noisy_memories(min_negative=3, days=7)
        for m in noisy:
            if m["memory_id"] not in active_ids:
                continue
            conflicts.append(
                {
                    "type": "noisy",
                    "severity": "warning",
                    "memory_id": m["memory_id"],
                    "description": (
                        f"Memory received {m['negative_count']} negative feedback in 7 days"
                    ),
                }
            )

        # Feedback-starved memories (cross-reference with Qdrant access_count)
        starved = await self.pg.get_feedback_starved_memories()
        for m in starved:
            mid = m["memory_id"]
            if mid not in active_ids:
                continue
            payload = active_payloads.get(mid, {})
            access_count = payload.get("access_count", 0)
            if access_count >= 5:
                conflicts.append(
                    {
                        "type": "feedback_starved",
                        "severity": "info",
                        "memory_id": mid,
                        "description": f"Memory accessed {access_count} times with no feedback",
                    }
                )

        # Orphan hubs (high graph centrality, low importance)
        try:
            orphan_hubs = await self.neo4j.get_high_gravity_memories(min_strength=2.0)
            for hub in orphan_hubs:
                mem_id = hub["id"]
                if mem_id not in active_ids:
                    continue
                total_strength = hub["total_strength"]
                imp = hub.get("importance", 0.5)
                # Skip high-access memories — they're actively useful, not orphans
                access_count = active_payloads.get(mem_id, {}).get("access_count", 0)
                if imp < 0.3 and access_count < 5:
                    conflicts.append(
                        {
                            "type": "orphan_hub",
                            "severity": "warning",
                            "memory_id": mem_id,
                            "description": (
                                f"High graph connectivity (strength={total_strength:.1f})"
                                f" but low importance ({imp:.2f})"
                            ),
                        }
                    )
        except Exception:
            pass

        return conflicts

    # --- Private helpers ---

    async def _feedback_metrics(self) -> dict[str, Any]:
        return await self.pg.get_feedback_stats(days=30)

    async def _population_balance(self) -> dict[str, Any]:
        counts = await self.pg.get_action_counts(days=30)
        stores = counts.get("create", 0)
        deletes = counts.get("delete", 0)
        decays = counts.get("decay", 0)
        net = stores - deletes - decays
        return {
            "stores": stores,
            "deletes": deletes,
            "decays": decays,
            "net_growth": net,
            "action_breakdown": counts,
        }

    async def _graph_cohesion(self) -> dict[str, Any]:
        try:
            avg_strength, edge_count = await self.neo4j.get_avg_edge_strength()
            return {
                "avg_edge_strength": round(avg_strength, 4),
                "edge_count": edge_count,
            }
        except Exception:
            return {"avg_edge_strength": 0.0, "edge_count": 0}

    async def _pin_ratio(self) -> dict[str, Any]:
        pinned = await self.qdrant.count_pinned()
        total = await self.qdrant.count()
        ratio = pinned / total if total > 0 else 0.0
        return {
            "pinned": pinned,
            "total": total,
            "ratio": round(ratio, 4),
            "warning": ratio > 0.3,
        }

    async def _importance_distribution(self) -> list[dict[str, Any]]:
        return await self.qdrant.get_importance_distribution()

    async def _feedback_similarity(self) -> list[dict[str, Any]]:
        return await self.pg.get_feedback_similarity_distribution(days=30)


async def create_health_computer() -> HealthComputer:
    """Factory to create a HealthComputer with all stores initialized."""
    pg = await get_postgres_store()
    qdrant = await get_qdrant_store()
    neo4j = await get_neo4j_store()
    redis = await get_redis_store()
    return HealthComputer(pg, qdrant, neo4j, redis)
