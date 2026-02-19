"""
Time Acceleration Suite — Simulates weeks of memory lifecycle in minutes.
"""

import asyncio
import random
import time

from tests.simulation.data.memory_corpus import TIME_ACCEL_MEMORIES
from tests.simulation.report import SuiteReport

from .base import BaseSuite


class TimeAccelerationSuite(BaseSuite):
    name = "time_accel"

    async def run(self) -> SuiteReport:
        t0 = time.monotonic()
        passed = True

        try:
            weeks = self.config.time_accel_weeks
            step_hours = self.config.time_accel_step_hours
            total_days = weeks * 7

            # ── Setup: Store memories across 3 domains ──
            self.observe(f"Storing memories for {weeks}-week simulation...")
            all_ids: list[str] = []
            domain_ids: dict[str, list[str]] = {"infra": [], "code-patterns": [], "debug-notes": []}

            for subdomain, mems in TIME_ACCEL_MEMORIES.items():
                for mem in mems:
                    mid = await self._store(
                        content=mem["content"],
                        importance=mem["importance"],
                        tags=[f"subdomain:{subdomain}"],
                    )
                    if mid:
                        all_ids.append(mid)
                        domain_ids[subdomain].append(mid)
                    await asyncio.sleep(0.3)

            self.observe(f"Stored {len(all_ids)} memories across {len(domain_ids)} subdomains")

            if len(all_ids) < 20:
                self.error("Too few memories stored for time acceleration")
                return self._make_report(False, time.monotonic() - t0)

            await asyncio.sleep(3)

            # ── Simulation loop ──
            self.observe(f"Starting {total_days}-day simulation ({step_hours}h steps)...")
            population_timeline = []
            consolidations_performed = 0
            total_merged = 0

            for day in range(1, total_days + 1):
                # Step 1: Decay
                r = await self.client.decay(simulate_hours=step_hours)
                await asyncio.sleep(6)  # Rate limit: 10/min

                if r is None:
                    self.error(f"Decay failed on day {day}")
                    continue

                # Step 2: Reinforcement every 3rd day — access 5 random memories
                if day % 3 == 0:
                    sample_ids = random.sample(all_ids, min(5, len(all_ids)))
                    for mid in sample_ids:
                        mem = await self.client.get_memory(mid)
                        if mem:
                            await self.client.search_query(
                                mem.get("content", "")[:40],
                                limit=3,
                                tags=[self.run_tag],
                            )
                        await asyncio.sleep(1)

                # Step 3: Consolidation every 7th day
                if day % 7 == 0:
                    await asyncio.sleep(6)  # Rate limit
                    cr = await self.client.consolidate(domain=self.domain)
                    if cr:
                        clusters = cr.get("clusters_merged", 0)
                        merged = cr.get("memories_merged", 0)
                        consolidations_performed += 1
                        total_merged += merged
                        if clusters > 0:
                            self.observe(
                                f"  Day {day}: consolidated {clusters} clusters ({merged} memories)"
                            )

                # Step 4: Snapshot population
                if day % 7 == 0 or day == 1 or day == total_days:
                    importances = []
                    active_count = 0
                    archived_count = 0

                    # Sample a subset to avoid too many API calls
                    sample = random.sample(all_ids, min(15, len(all_ids)))
                    for mid in sample:
                        mem = await self.client.get_memory(mid)
                        if mem:
                            imp = mem.get("importance", 0)
                            importances.append(imp)
                            if imp > 0.05:
                                active_count += 1
                            else:
                                archived_count += 1
                        await asyncio.sleep(0.2)

                    if importances:
                        s = sorted(importances)
                        n = len(s)
                        snapshot = {
                            "day": day,
                            "sampled": n,
                            "active": active_count,
                            "archived": archived_count,
                            "importance_mean": round(sum(s) / n, 4),
                            "importance_p25": round(s[n // 4], 4),
                            "importance_p50": round(s[n // 2], 4),
                            "importance_p75": round(s[3 * n // 4], 4),
                        }
                        population_timeline.append(snapshot)

                        if day % 7 == 0 or day == total_days:
                            self.observe(
                                f"  Day {day}: active={active_count}/{n}, "
                                f"mean_imp={snapshot['importance_mean']:.3f}, "
                                f"p50={snapshot['importance_p50']:.3f}"
                            )

            # ── Survival curve ──
            survival_curve = []
            for snap in population_timeline:
                total = snap["active"] + snap["archived"]
                pct = snap["active"] / total * 100 if total > 0 else 0
                survival_curve.append(
                    {
                        "day": snap["day"],
                        "survival_pct": round(pct, 1),
                    }
                )

            # ── Metrics ──
            initial_pop = population_timeline[0] if population_timeline else {}
            final_pop = population_timeline[-1] if population_timeline else {}

            self.metric("population_timeline", population_timeline)
            self.metric("survival_curve", survival_curve)
            self.metric("consolidations_performed", consolidations_performed)
            self.metric("total_merged", total_merged)
            self.metric("initial_population", initial_pop.get("sampled", 0))
            self.metric("initial_active", initial_pop.get("active", 0))
            self.metric("final_active", final_pop.get("active", 0))
            self.metric("final_archived", final_pop.get("archived", 0))
            self.metric("simulated_days", total_days)

            self.observe(f"Simulation complete: {total_days} days simulated")
            if initial_pop and final_pop:
                self.observe(
                    f"Population: {initial_pop.get('active', '?')} active -> "
                    f"{final_pop.get('active', '?')} active, "
                    f"{final_pop.get('archived', '?')} archived"
                )
            self.observe(
                f"Consolidations: {consolidations_performed} runs, {total_merged} memories merged"
            )

        except Exception as e:
            self.error(f"Time acceleration suite exception: {e}")
            passed = False

        return self._make_report(passed, time.monotonic() - t0)
