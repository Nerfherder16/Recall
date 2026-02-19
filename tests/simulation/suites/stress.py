"""
Stress Suite — Concurrent load, throughput, and dedup under concurrency.
"""

import asyncio
import random
import time

from tests.simulation.report import SuiteReport

from .base import BaseSuite


class StressSuite(BaseSuite):
    name = "stress"

    async def run(self) -> SuiteReport:
        t0 = time.monotonic()
        passed = True
        concurrency = self.config.stress_concurrency

        try:
            # ── Scenario A: Concurrent Stores ──
            self.observe(f"Running concurrent stores (3 rounds x {concurrency} parallel)...")
            store_metrics = []

            for round_num in range(3):
                tasks = []
                for i in range(concurrency):
                    content = (
                        f"Stress test memory round={round_num} idx={i}: "
                        f"Testing concurrent write throughput with unique content "
                        f"to verify the system handles parallel stores correctly. "
                        f"Random salt: {random.randint(10000, 99999)}"
                    )
                    tasks.append(self._timed_store(content, f"round-{round_num}"))

                round_start = time.monotonic()
                results = await asyncio.gather(*tasks, return_exceptions=True)
                round_elapsed = time.monotonic() - round_start

                successes = sum(1 for r in results if not isinstance(r, Exception) and r)
                errors = sum(1 for r in results if isinstance(r, Exception) or not r)
                ops_per_sec = successes / round_elapsed if round_elapsed > 0 else 0

                store_metrics.append(
                    {
                        "round": round_num,
                        "successes": successes,
                        "errors": errors,
                        "duration_seconds": round(round_elapsed, 2),
                        "ops_per_sec": round(ops_per_sec, 2),
                    }
                )
                self.observe(
                    f"  Round {round_num}: {successes}/{concurrency} ok, {ops_per_sec:.1f} ops/s"
                )
                await asyncio.sleep(2)

            self.metric("concurrent_stores", store_metrics)

            # ── Scenario B: Concurrent Searches ──
            self.observe(f"Running concurrent searches ({concurrency} parallel)...")
            await asyncio.sleep(2)

            search_queries = [
                "concurrent write throughput",
                "stress test parallel",
                "unique content verification",
                "system handles correctly",
                "testing concurrent stores",
                "random salt value",
                "write throughput test",
                "parallel store operations",
                "verify system handles",
                "stress test memory",
            ]

            search_tasks = []
            for i in range(concurrency):
                query = search_queries[i % len(search_queries)]
                search_tasks.append(self._timed_search(query))

            search_start = time.monotonic()
            search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
            search_elapsed = time.monotonic() - search_start

            search_successes = sum(
                1 for r in search_results if not isinstance(r, Exception) and r is not None
            )
            search_ops = search_successes / search_elapsed if search_elapsed > 0 else 0

            self.metric(
                "concurrent_searches",
                {
                    "successes": search_successes,
                    "errors": concurrency - search_successes,
                    "duration_seconds": round(search_elapsed, 2),
                    "ops_per_sec": round(search_ops, 2),
                },
            )
            self.observe(
                f"Concurrent searches: {search_successes}/{concurrency} ok, {search_ops:.1f} ops/s"
            )

            # ── Scenario C: Mixed Read/Write ──
            self.observe("Running mixed read/write workload (70% read, 30% write)...")
            total_ops = 50
            sem = asyncio.Semaphore(concurrency)
            mixed_tasks = []
            read_latencies = []
            write_latencies = []

            for i in range(total_ops):
                if random.random() < 0.7:
                    mixed_tasks.append(
                        self._sem_search(sem, f"stress test memory {i}", read_latencies)
                    )
                else:
                    content = (
                        f"Mixed workload write {i}: random content {random.randint(10000, 99999)}"
                    )
                    mixed_tasks.append(self._sem_store(sem, content, write_latencies))

            mixed_start = time.monotonic()
            await asyncio.gather(*mixed_tasks, return_exceptions=True)
            mixed_elapsed = time.monotonic() - mixed_start

            self.metric(
                "mixed_workload",
                {
                    "total_ops": total_ops,
                    "duration_seconds": round(mixed_elapsed, 2),
                    "throughput_ops_per_sec": round(total_ops / mixed_elapsed, 2)
                    if mixed_elapsed > 0
                    else 0,
                    "read_latency_p50_ms": round(_percentile(read_latencies, 0.5) * 1000, 1)
                    if read_latencies
                    else 0,
                    "read_latency_p95_ms": round(_percentile(read_latencies, 0.95) * 1000, 1)
                    if read_latencies
                    else 0,
                    "write_latency_p50_ms": round(_percentile(write_latencies, 0.5) * 1000, 1)
                    if write_latencies
                    else 0,
                    "write_latency_p95_ms": round(_percentile(write_latencies, 0.95) * 1000, 1)
                    if write_latencies
                    else 0,
                },
            )
            self.observe(f"Mixed workload: {total_ops} ops in {mixed_elapsed:.1f}s")

            # ── Scenario D: Dedup Under Concurrency ──
            self.observe("Running dedup-under-concurrency test (10 identical stores)...")
            dedup_content = (
                f"Dedup test: this exact content should only be "
                f"stored once. Run ID: {self.client.run_id}"
            )
            dedup_tasks = [self._store_raw(dedup_content) for _ in range(10)]
            dedup_results = await asyncio.gather(*dedup_tasks, return_exceptions=True)

            created_count = 0
            dup_count = 0
            for r in dedup_results:
                if isinstance(r, Exception):
                    continue
                if r and r.get("created"):
                    created_count += 1
                elif r and not r.get("created"):
                    dup_count += 1

            self.metric(
                "dedup_concurrency",
                {
                    "created": created_count,
                    "duplicates_detected": dup_count,
                    "expected_created": 1,
                },
            )
            self.observe(f"Dedup: {created_count} created, {dup_count} detected as dup")

            if created_count > 1:
                self.observe(
                    f"Warning: {created_count} creates (expected 1) — race condition in dedup check"
                )
                # Not a hard failure — concurrent dedup is best-effort

            # ── Scenario E: Batch Under Load ──
            self.observe("Running batch store under concurrent search load...")
            batch_items = [
                {
                    "content": (
                        f"Batch-under-load item {i}: testing batch operations "
                        f"while searches run. Salt: {random.randint(10000, 99999)}"
                    ),
                    "memory_type": "semantic",
                    "domain": self.domain,
                    "tags": [self.client.run_tag(), "batch-load-test"],
                    "importance": round(random.uniform(0.3, 0.7), 2),
                }
                for i in range(20)
            ]

            # Launch concurrent searches alongside batch store
            async def _batch_store():
                t = time.monotonic()
                r = await self.client.batch_store(batch_items)
                return time.monotonic() - t, r

            search_during_batch = [
                self._timed_search(f"batch operations test {i}") for i in range(5)
            ]

            batch_task = asyncio.create_task(_batch_store())
            search_tasks_during = [asyncio.create_task(s) for s in search_during_batch]

            batch_latency, batch_result = await batch_task
            search_during_results = await asyncio.gather(
                *search_tasks_during, return_exceptions=True
            )

            batch_created = 0
            if batch_result and "results" in batch_result:
                batch_created = sum(1 for r in batch_result["results"] if r.get("created"))

            self.metric(
                "batch_under_load",
                {
                    "batch_latency_ms": round(batch_latency * 1000, 1),
                    "batch_items_created": batch_created,
                    "concurrent_searches_completed": sum(
                        1
                        for r in search_during_results
                        if not isinstance(r, Exception) and r is not None
                    ),
                },
            )
            self.observe(
                f"Batch: {batch_created} created in "
                f"{batch_latency * 1000:.0f}ms with 5 concurrent searches"
            )

        except Exception as e:
            self.error(f"Stress suite exception: {e}")
            passed = False

        return self._make_report(passed, time.monotonic() - t0)

    # ── Helpers ──

    async def _timed_store(self, content: str, tag: str) -> str | None:
        return await self._store(content=content, tags=[tag])

    async def _timed_search(self, query: str) -> list[dict] | None:
        return await self.client.search_query(query, limit=5, tags=[self.run_tag])

    async def _store_raw(self, content: str) -> dict | None:
        """Store without helper wrapping — returns raw response for dedup check."""
        return await self.client.store_memory(
            content=content,
            domain=self.domain,
            memory_type="semantic",
            importance=0.5,
        )

    async def _sem_search(self, sem: asyncio.Semaphore, query: str, latencies: list):
        async with sem:
            t = time.monotonic()
            await self.client.search_query(query, limit=5, tags=[self.run_tag])
            latencies.append(time.monotonic() - t)

    async def _sem_store(self, sem: asyncio.Semaphore, content: str, latencies: list):
        async with sem:
            t = time.monotonic()
            await self._store(content=content)
            latencies.append(time.monotonic() - t)


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = int(len(s) * p)
    return s[min(idx, len(s) - 1)]
