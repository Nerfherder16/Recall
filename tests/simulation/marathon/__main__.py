"""
Marathon simulation entry point and orchestrator.

Usage:
  python -m tests.simulation.marathon                    # 4-hour default
  python -m tests.simulation.marathon --duration 0.15    # 10-min dry run
  python -m tests.simulation.marathon --cleanup-only ID  # Cleanup previous run
"""

import asyncio
import sys
import time
from datetime import datetime, timezone

from ..client import TimedRecallClient
from .config import MarathonConfig, parse_args
from .metrics import MetricsCollector
from .report import MarathonReport
from .scheduler import RateLimitScheduler
from .personas.archivist import Archivist
from .personas.researcher import Researcher
from .personas.curator import Curator
from .personas.operator import Operator
from .personas.session_worker import SessionWorker


async def cleanup_run(client: TimedRecallClient, domain_prefix: str):
    """Tier 1 + Tier 2 cleanup of all marathon data."""
    print("  [cleanup] Tier 1: deleting tracked IDs...")
    await client.cleanup()

    # Tier 2: domain sweep for stragglers (consolidation/signal artifacts)
    print("  [cleanup] Tier 2: domain sweep for stragglers...")
    from .corpus import SUBDOMAINS
    total_swept = 0
    for sub in SUBDOMAINS:
        domain = f"{domain_prefix}-{sub}"
        for _ in range(10):  # Max 10 sweeps per domain
            entries = await client.search_timeline(limit=50, domain=domain)
            if not entries:
                break
            ids = [e["id"] for e in entries if "id" in e]
            if not ids:
                break
            await client.batch_delete(ids)
            total_swept += len(ids)
            await asyncio.sleep(0.5)

    if total_swept > 0:
        print(f"  [cleanup] Swept {total_swept} straggler memories")
    print("  [cleanup] Done")


async def run_marathon(config: MarathonConfig):
    """Main marathon orchestrator."""
    client = TimedRecallClient(config.api_url, config.api_key, config.run_id)
    domain_prefix = config.domain_prefix()
    scheduler = RateLimitScheduler()
    stop_event = asyncio.Event()

    print()
    print("=" * 70)
    print(f"  MARATHON SIMULATION — run {config.run_id}")
    print(f"  {datetime.now(timezone.utc).isoformat()}")
    print(f"  API: {config.api_url}")
    print(f"  Duration: {config.duration_hours}h | Domain prefix: {domain_prefix}")
    print("=" * 70)
    print()

    # Health check
    print("  [init] Health check...")
    health = await client.health()
    if not health:
        print("  [FATAL] API health check failed. Aborting.")
        await client.close()
        return
    print(f"  [init] API healthy: {health.get('status', 'ok')}")

    # Initial stats
    stats = await client.stats()
    if stats:
        print(f"  [init] Baseline: {stats.get('total_memories', '?')} memories, "
              f"{stats.get('graph', {}).get('nodes', '?')} graph nodes")

    # Create personas
    personas = [
        Archivist(client, scheduler, domain_prefix),
        Researcher(client, scheduler, domain_prefix),
        Curator(client, scheduler, domain_prefix),
        Operator(client, scheduler, domain_prefix),
        SessionWorker(client, scheduler, domain_prefix),
    ]

    # Create metrics collector
    metrics = MetricsCollector(client, scheduler, interval=config.snapshot_interval)

    # Progress reporter
    async def progress_loop():
        start = time.monotonic()
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=config.progress_interval)
                break
            except asyncio.TimeoutError:
                pass
            elapsed_m = (time.monotonic() - start) / 60.0
            total_ops = sum(sum(p.ops.values()) for p in personas)
            total_err = sum(len(p.errors) for p in personas)
            tracked = len(client.tracked_ids)
            print(f"  [{elapsed_m:.0f}m] ops={total_ops} tracked={tracked} "
                  f"errors={total_err} 429s={client.rate_limited} "
                  f"snapshots={len(metrics.snapshots)}")

    # Duration watchdog
    async def watchdog():
        duration_s = config.duration_hours * 3600
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=duration_s)
        except asyncio.TimeoutError:
            print(f"\n  [watchdog] Duration {config.duration_hours}h reached. Stopping...")
            stop_event.set()

    print(f"\n  [start] Launching 5 personas + metrics collector...")
    t0 = time.monotonic()

    # Launch all concurrent tasks
    tasks = []
    tasks.append(asyncio.create_task(watchdog()))
    tasks.append(asyncio.create_task(progress_loop()))
    tasks.append(asyncio.create_task(metrics.run_loop(stop_event)))
    for p in personas:
        tasks.append(asyncio.create_task(p.run_loop(stop_event)))

    # Wait for watchdog to fire (or Ctrl+C)
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        print("\n  [interrupt] Ctrl+C received. Stopping gracefully...")
        stop_event.set()
        # Give tasks a moment to wind down
        await asyncio.sleep(2)
    except Exception as e:
        print(f"\n  [error] Unexpected error: {e}")
        stop_event.set()
        await asyncio.sleep(1)

    duration = time.monotonic() - t0
    duration_hours = duration / 3600.0
    print(f"\n  [done] Ran for {duration_hours:.2f}h ({duration:.0f}s)")

    # Build report
    report = MarathonReport(
        run_id=config.run_id,
        duration_hours=duration_hours,
        snapshots=metrics.snapshots,
        rate_limit_hits=client.rate_limited,
        latency_summary=client.latency_stats(),
    )

    # Collect persona summaries and errors
    all_errors = []
    for p in personas:
        report.personas[p.name] = p.summary()
        all_errors.extend(p.errors)
    report.errors = all_errors

    # Save report
    filepath = report.save_json(config.report_dir)
    print(f"  [report] Saved to {filepath}")

    # Print summary
    report.print_summary()

    # Cleanup
    if not config.no_cleanup:
        print("  [cleanup] Starting cleanup...")
        await cleanup_run(client, domain_prefix)
    else:
        print(f"  [skip] Cleanup skipped. Run with --cleanup-only {config.run_id} later.")

    await client.close()


async def cleanup_only(run_id: str, config: MarathonConfig):
    """Standalone cleanup for a previous run."""
    client = TimedRecallClient(config.api_url, config.api_key, run_id)
    domain_prefix = f"sim-marathon-{run_id}"
    print(f"  [cleanup] Cleaning up run {run_id} (domain: {domain_prefix})")
    await cleanup_run(client, domain_prefix)
    await client.close()


def main():
    config = parse_args()

    if config.cleanup_only:
        asyncio.run(cleanup_only(config.cleanup_only, config))
    else:
        asyncio.run(run_marathon(config))


if __name__ == "__main__":
    main()
