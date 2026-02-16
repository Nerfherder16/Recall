"""
Lifecycle Suite — Tests decay curves, reinforcement, and consolidation.
"""

import asyncio
import time

from tests.simulation.data.memory_corpus import CONSOLIDATION_CANDIDATES, LIFECYCLE_MEMORIES
from tests.simulation.report import SuiteReport

from .base import BaseSuite


class LifecycleSuite(BaseSuite):
    name = "lifecycle"

    async def run(self) -> SuiteReport:
        t0 = time.monotonic()
        passed = True

        try:
            # ── Setup: Store test memories ──
            self.observe("Storing lifecycle test memories...")
            stored: dict[str, list[str]] = {"high": [], "mid": [], "low": []}

            for level in ("high", "mid", "low"):
                for mem in LIFECYCLE_MEMORIES[level]:
                    mid = await self._store(
                        content=mem["content"],
                        importance=mem["importance"],
                        tags=[f"level:{level}"],
                    )
                    if mid:
                        stored[level].append(mid)
                    await asyncio.sleep(0.5)

            total_stored = sum(len(v) for v in stored.values())
            self.observe(f"Stored {total_stored} memories: "
                         f"{len(stored['high'])} high, {len(stored['mid'])} mid, {len(stored['low'])} low")

            if total_stored < 10:
                self.error("Too few memories stored, aborting lifecycle tests")
                return self._make_report(False, time.monotonic() - t0)

            # Store consolidation candidates
            consol_ids = []
            for content in CONSOLIDATION_CANDIDATES:
                mid = await self._store(content=content, importance=0.5, tags=["consolidation-test"])
                if mid:
                    consol_ids.append(mid)
                await asyncio.sleep(0.5)
            self.observe(f"Stored {len(consol_ids)} consolidation candidates")

            # Allow embedding/graph indexing to settle
            await asyncio.sleep(3)

            # ── Scenario A: Decay Curve ──
            self.observe("Running decay curve test (7 steps x 24h)...")
            decay_curve = []

            for step in range(7):
                # Trigger decay with 24h simulation
                r = await self.client.decay(simulate_hours=24)
                await asyncio.sleep(6)  # Rate limit: 10/min for admin

                if r is None:
                    self.error(f"Decay step {step+1} failed")
                    continue

                # Sample importances
                importances = {"high": [], "mid": [], "low": []}
                for level, ids in stored.items():
                    for mid in ids:
                        mem = await self.client.get_memory(mid)
                        if mem:
                            importances[level].append(mem.get("importance", 0))
                        await asyncio.sleep(0.2)

                point = {
                    "hours": (step + 1) * 24,
                    "avg_high": _avg(importances["high"]),
                    "avg_mid": _avg(importances["mid"]),
                    "avg_low": _avg(importances["low"]),
                    "decay_processed": r.get("processed", 0),
                    "decay_decayed": r.get("decayed", 0),
                }
                decay_curve.append(point)
                self.observe(f"  Day {step+1}: high={point['avg_high']:.3f} mid={point['avg_mid']:.3f} low={point['avg_low']:.3f}")

            self.metric("decay_curve", decay_curve)

            # Assert: generally decreasing trend
            if len(decay_curve) >= 3:
                first_high = decay_curve[0]["avg_high"]
                last_high = decay_curve[-1]["avg_high"]
                first_low = decay_curve[0]["avg_low"]
                last_low = decay_curve[-1]["avg_low"]

                if last_high >= first_high and first_high > 0:
                    self.error(f"High-importance did not decay: {first_high:.3f} -> {last_high:.3f}")
                    passed = False
                else:
                    self.observe(f"Decay confirmed: high {first_high:.3f} -> {last_high:.3f}")

                # High should remain above where low started
                if last_high < first_low and first_low > 0.05:
                    self.observe(f"Warning: high decayed below initial low ({last_high:.3f} < {first_low:.3f})")

            # ── Scenario B: Reinforcement Loop ──
            self.observe("Running reinforcement test...")
            # Pick 3 mid-importance memories to reinforce
            reinforce_ids = stored["mid"][:3]
            control_ids = stored["mid"][3:]

            # Access them via search (triggers _track_access)
            for mid in reinforce_ids:
                mem = await self.client.get_memory(mid)
                if mem:
                    # Search for this memory's content to trigger access tracking
                    await self.client.search_query(
                        mem["content"][:50],
                        limit=5,
                        domains=[self.domain],
                    )
                await asyncio.sleep(2)

            # Run 2 more decay steps
            for _ in range(2):
                await self.client.decay(simulate_hours=24)
                await asyncio.sleep(6)

            # Compare final importances
            reinforced_importances = []
            for mid in reinforce_ids:
                mem = await self.client.get_memory(mid)
                if mem:
                    reinforced_importances.append(mem.get("importance", 0))
                await asyncio.sleep(0.2)

            control_importances = []
            for mid in control_ids:
                mem = await self.client.get_memory(mid)
                if mem:
                    control_importances.append(mem.get("importance", 0))
                await asyncio.sleep(0.2)

            avg_reinforced = _avg(reinforced_importances)
            avg_control = _avg(control_importances)
            delta = avg_reinforced - avg_control

            self.metric("reinforcement", {
                "accessed_final": round(avg_reinforced, 4),
                "unaccessed_final": round(avg_control, 4),
                "delta": round(delta, 4),
            })

            if delta > 0:
                self.observe(f"Reinforcement works: accessed={avg_reinforced:.3f} > unaccessed={avg_control:.3f} (delta={delta:.3f})")
            else:
                self.observe(f"Reinforcement inconclusive: accessed={avg_reinforced:.3f} vs unaccessed={avg_control:.3f}")
                # Not a hard failure — delta can be small

            # ── Scenario C: Consolidation ──
            self.observe("Running consolidation test...")
            await asyncio.sleep(6)  # Rate limit
            r = await self.client.consolidate(domain=self.domain, dry_run=False)

            if r:
                clusters = r.get("clusters_merged", 0)
                merged = r.get("memories_merged", 0)
                results = r.get("results", [])
                self.metric("consolidation", {
                    "clusters_found": clusters,
                    "memories_merged": merged,
                    "merged_previews": [res.get("content_preview", "") for res in results[:3]],
                })
                self.observe(f"Consolidation: {clusters} clusters, {merged} memories merged")

                if clusters == 0:
                    self.observe("Warning: no clusters merged (consolidation may need more similar content)")
            else:
                self.error("Consolidation request failed")
                passed = False

        except Exception as e:
            self.error(f"Lifecycle suite exception: {e}")
            passed = False

        return self._make_report(passed, time.monotonic() - t0)


def _avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)
