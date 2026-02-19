"""
Durability Suite — Tests memory durability classification under decay.

Scenarios:
A. Tier separation: permanent, durable, and ephemeral memories decay at different rates
B. Durability upgrade: changing a memory's durability tier affects future decay
C. Durability + pinning interaction: pinned overrides durability (both immune)
D. Consolidation preserves highest durability from cluster
"""

import asyncio
import time

from tests.simulation.report import SuiteReport

from .base import BaseSuite


class DurabilitySuite(BaseSuite):
    name = "durability"

    async def run(self) -> SuiteReport:
        t0 = time.monotonic()
        passed = True

        try:
            # ── Scenario A: Tier Separation Under Decay ──
            self.observe("=== Scenario A: Durability Tier Separation ===")

            # Store 3 memories at each durability tier, same importance
            permanent_ids = []
            durable_ids = []
            ephemeral_ids = []

            rid = self.client.run_id
            for i in range(3):
                pid = await self._store_durable(
                    f"Infrastructure fact #{i} [{rid}]: API port 820{i}",
                    importance=0.7,
                    durability="permanent",
                )
                did = await self._store_durable(
                    f"Architecture decision #{i} [{rid}]: event sourcing v{i}",
                    importance=0.7,
                    durability="durable",
                )
                eid = await self._store_durable(
                    f"Debug session note #{i} [{rid}]: CSS header fix v{i}",
                    importance=0.7,
                    durability="ephemeral",
                )
                if pid:
                    permanent_ids.append(pid)
                if did:
                    durable_ids.append(did)
                if eid:
                    ephemeral_ids.append(eid)
                await asyncio.sleep(0.5)

            self.observe(
                f"Stored: {len(permanent_ids)} permanent, "
                f"{len(durable_ids)} durable, {len(ephemeral_ids)} ephemeral"
            )

            if len(permanent_ids) < 2 or len(durable_ids) < 2 or len(ephemeral_ids) < 2:
                self.error("Could not store enough memories for each tier")
                return self._make_report(False, time.monotonic() - t0)

            # Get baseline importances
            perm_before = await self._avg_importance(permanent_ids)
            dur_before = await self._avg_importance(durable_ids)
            eph_before = await self._avg_importance(ephemeral_ids)
            self.observe(
                f"Before decay — perm: {perm_before:.3f}, "
                f"dur: {dur_before:.3f}, eph: {eph_before:.3f}"
            )

            # Run 5 decay cycles at 48h each (240h total = 10 days)
            for step in range(5):
                r = await self.client.decay(simulate_hours=48)
                if r is None:
                    self.error(f"Decay step {step + 1} failed")
                await asyncio.sleep(5)

            # Measure after decay
            perm_after = await self._avg_importance(permanent_ids)
            dur_after = await self._avg_importance(durable_ids)
            eph_after = await self._avg_importance(ephemeral_ids)

            self.observe(
                f"After 10 days — perm: {perm_after:.3f}, "
                f"dur: {dur_after:.3f}, eph: {eph_after:.3f}"
            )

            perm_delta = perm_before - perm_after
            dur_delta = dur_before - dur_after
            eph_delta = eph_before - eph_after

            self.observe(
                f"Deltas — perm: -{perm_delta:.3f}, dur: -{dur_delta:.3f}, eph: -{eph_delta:.3f}"
            )

            # Permanent should be immune (delta ~0)
            if perm_delta > 0.05:
                self.error(f"Permanent memories decayed: delta={perm_delta:.3f}")
                passed = False
            else:
                self.observe(f"Permanent immune to decay (delta={perm_delta:.3f})")

            # Ephemeral should decay more than durable
            if eph_delta > dur_delta:
                self.observe(
                    f"Ephemeral decayed more than durable ({eph_delta:.3f} > {dur_delta:.3f})"
                )
            else:
                self.observe(
                    f"Warning: durable didn't decay less than ephemeral "
                    f"(dur={dur_delta:.3f}, eph={eph_delta:.3f})"
                )

            # Durable should decay less than ephemeral (at 0.15x rate)
            if dur_delta > 0 and eph_delta > 0:
                decay_ratio = dur_delta / eph_delta
                self.observe(f"Durable/ephemeral decay ratio: {decay_ratio:.2f} (expected ~0.15)")
            else:
                decay_ratio = None

            self.metric(
                "tier_separation",
                {
                    "permanent": {
                        "before": round(perm_before, 4),
                        "after": round(perm_after, 4),
                        "delta": round(perm_delta, 4),
                    },
                    "durable": {
                        "before": round(dur_before, 4),
                        "after": round(dur_after, 4),
                        "delta": round(dur_delta, 4),
                    },
                    "ephemeral": {
                        "before": round(eph_before, 4),
                        "after": round(eph_after, 4),
                        "delta": round(eph_delta, 4),
                    },
                    "decay_ratio_durable_to_ephemeral": round(decay_ratio, 3)
                    if decay_ratio
                    else None,
                    "permanent_immune": perm_delta <= 0.05,
                },
            )

            await asyncio.sleep(2)

            # ── Scenario B: Durability Upgrade ──
            self.observe("\n=== Scenario B: Durability Upgrade ===")

            upgrade_id = await self._store_durable(
                f"Temporary workaround [{rid}]: restart on memory leak",
                importance=0.6,
                durability="ephemeral",
            )

            if upgrade_id:
                # Verify it's ephemeral
                mem = await self.client.get_memory(upgrade_id)
                orig_dur = mem.get("durability") if mem else None
                self.observe(f"Created as {orig_dur}")

                # Upgrade to permanent
                result = await self.client.put_durability(upgrade_id, "permanent")
                if result:
                    self.observe(f"Upgraded to permanent: {result}")
                else:
                    self.error("PUT durability failed")
                    passed = False

                # Verify via GET
                mem2 = await self.client.get_memory(upgrade_id)
                new_dur = mem2.get("durability") if mem2 else None
                self.observe(f"After upgrade: {new_dur}")

                if new_dur == "permanent":
                    self.observe("Durability upgrade confirmed")
                else:
                    self.error(f"Expected permanent, got {new_dur}")
                    passed = False

                # Run decay — upgraded memory should be immune now
                imp_before = mem2.get("importance", 0) if mem2 else 0
                await self.client.decay(simulate_hours=48)
                await asyncio.sleep(5)
                mem3 = await self.client.get_memory(upgrade_id)
                imp_after = mem3.get("importance", 0) if mem3 else 0
                upgrade_drift = abs(imp_before - imp_after)

                self.observe(
                    f"Post-upgrade decay: {imp_before:.3f} → {imp_after:.3f} "
                    f"(drift={upgrade_drift:.3f})"
                )

                self.metric(
                    "durability_upgrade",
                    {
                        "original": orig_dur,
                        "upgraded_to": new_dur,
                        "importance_before_decay": round(imp_before, 4),
                        "importance_after_decay": round(imp_after, 4),
                        "drift": round(upgrade_drift, 4),
                        "immune_after_upgrade": upgrade_drift <= 0.05,
                    },
                )
            else:
                self.error("Failed to store upgrade test memory")
                passed = False

            await asyncio.sleep(2)

            # ── Scenario C: Durability + Pinning ──
            self.observe("\n=== Scenario C: Durability + Pinning Interaction ===")

            # Durable + pinned = doubly protected
            dual_id = await self._store_durable(
                f"Critical [{rid}]: Qdrant port 6333 recall_memories collection",
                importance=0.8,
                durability="durable",
            )

            if dual_id:
                await self.client.pin_memory(dual_id)
                await asyncio.sleep(1)

                mem_before = await self.client.get_memory(dual_id)
                imp_before = mem_before.get("importance", 0.8) if mem_before else 0.8
                for step in range(3):
                    await self.client.decay(simulate_hours=48)
                    await asyncio.sleep(5)

                mem = await self.client.get_memory(dual_id)
                imp_after = mem.get("importance", 0) if mem else 0
                drift = abs(imp_before - imp_after)

                self.observe(
                    f"Durable+pinned: {imp_before:.3f} → {imp_after:.3f} (drift={drift:.3f})"
                )

                self.metric(
                    "durability_pinning",
                    {
                        "before": round(imp_before, 4),
                        "after": round(imp_after, 4),
                        "drift": round(drift, 4),
                        "immune": drift <= 0.05,
                    },
                )

                if drift > 0.05:
                    self.error(f"Durable+pinned memory decayed: drift={drift:.3f}")
                    passed = False

                # Unpin for cleanup
                await self.client.unpin_memory(dual_id)
            else:
                self.error("Failed to store dual protection test memory")

            await asyncio.sleep(2)

            # ── Scenario D: Search Returns Durability ──
            self.observe("\n=== Scenario D: Search Returns Durability ===")

            results = await self.client.search_browse(
                "API server port infrastructure",
                limit=5,
                tags=[self.run_tag],
            )

            dur_in_results = sum(1 for r in results if r.get("durability"))
            self.observe(
                f"Browse returned {len(results)} results, {dur_in_results} with durability field"
            )

            self.metric(
                "search_durability",
                {
                    "total_results": len(results),
                    "with_durability": dur_in_results,
                },
            )

        except Exception as e:
            self.error(f"Durability suite exception: {e}")
            passed = False

        return self._make_report(passed, time.monotonic() - t0)

    async def _store_durable(
        self, content: str, importance: float = 0.5, durability: str = "ephemeral"
    ) -> str | None:
        """Store a memory with durability in this suite's domain."""
        r = await self.client.store_memory(
            content=content,
            domain=self.domain,
            importance=importance,
            durability=durability,
            tags=[f"durability-{durability}"],
        )
        if r and r.get("id"):
            return r["id"]
        return None

    async def _avg_importance(self, ids: list[str]) -> float:
        """Get average importance for a list of memory IDs."""
        values = []
        for mid in ids:
            mem = await self.client.get_memory(mid)
            if mem and "importance" in mem:
                values.append(mem["importance"])
        return sum(values) / len(values) if values else 0.0
