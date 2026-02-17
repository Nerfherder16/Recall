"""
Testbed — CLI entry point and orchestrator for Recall simulation suites.

Usage:
    python -m tests.simulation.testbed                          # Full run
    python -m tests.simulation.testbed --suites lifecycle,retrieval
    python -m tests.simulation.testbed --suites stress --stress-concurrency 20
    python -m tests.simulation.testbed --compare reports/a.json reports/b.json
    python -m tests.simulation.testbed --cleanup-only <run_id>
"""

import asyncio
import io
import sys
import time

from tests.simulation.cleanup import cleanup_run
from tests.simulation.client import TimedRecallClient
from tests.simulation.config import TestbedConfig, parse_args
from tests.simulation.report import TestbedReport, compare_reports
from tests.simulation.suites.lifecycle import LifecycleSuite
from tests.simulation.suites.retrieval_quality import RetrievalQualitySuite
from tests.simulation.suites.signal_quality import SignalQualitySuite
from tests.simulation.suites.stress import StressSuite
from tests.simulation.suites.adaptive import AdaptiveSuite
from tests.simulation.suites.time_acceleration import TimeAccelerationSuite

SUITE_MAP = {
    "lifecycle": LifecycleSuite,
    "retrieval": RetrievalQualitySuite,
    "stress": StressSuite,
    "signals": SignalQualitySuite,
    "time_accel": TimeAccelerationSuite,
    "adaptive": AdaptiveSuite,
}


async def run_testbed(config: TestbedConfig):
    """Main orchestrator: connect, run suites, report."""
    t0 = time.monotonic()

    client = TimedRecallClient(
        base_url=config.api_url,
        api_key=config.api_key,
        run_id=config.run_id,
    )

    report = TestbedReport(
        run_id=config.run_id,
        api_url=config.api_url,
    )

    try:
        # ── Health check ──
        print(f"\nConnecting to Recall at {config.api_url}...")
        health = await client.health()
        if not health:
            print("ERROR: Cannot connect to Recall API. Aborting.")
            return
        print(f"Connected! Status: {health.get('status')}")
        report.health_baseline = health

        # ── Resolve suites ──
        suite_names = config.resolved_suites
        valid_names = [n for n in suite_names if n in SUITE_MAP]

        if not valid_names:
            print(f"ERROR: No valid suites. Available: {list(SUITE_MAP.keys())}")
            return

        print(f"Run ID: {config.run_id}")
        print(f"Suites: {', '.join(valid_names)}")
        print()

        # ── Execute suites sequentially ──
        for name in valid_names:
            suite_cls = SUITE_MAP[name]
            suite = suite_cls(client, config)

            print(f"{'─' * 60}")
            print(f"  Running: {name}")
            print(f"{'─' * 60}")

            suite_report = await suite.run()
            report.suites.append(suite_report)

            status = "PASS" if suite_report.passed else "FAIL"
            print(f"  Result: {status} ({suite_report.duration_seconds:.1f}s)")
            if suite_report.errors:
                for e in suite_report.errors[:3]:
                    print(f"  Error: {e}")
            print()

        # ── Cleanup ──
        if not config.no_cleanup:
            print("Cleaning up testbed data...")
            await client.cleanup()
            print("Cleanup complete.")
        else:
            print(f"Skipping cleanup (--no-cleanup). Run ID for manual cleanup: {config.run_id}")

        # ── Finalize report ──
        report.total_duration_seconds = time.monotonic() - t0
        report.latency_summary = client.latency_stats()
        report.rate_limited_count = client.rate_limited

        # Save JSON report
        filepath = report.save_json(config.report_dir)
        print(f"\nReport saved: {filepath}")

        # Print console summary
        report.print_summary()

    finally:
        await client.close()


def main():
    # Fix Windows console encoding + line buffering
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

    config = parse_args()

    # ── Compare mode ──
    if config.compare_files:
        compare_reports(config.compare_files[0], config.compare_files[1])
        return

    # ── Cleanup-only mode ──
    if config.cleanup_only:
        print(f"Cleaning up run {config.cleanup_only}...")
        asyncio.run(cleanup_run(config.api_url, config.api_key, config.cleanup_only, verbose=True))
        return

    # ── Normal run ──
    print("=" * 60)
    print("  RECALL TESTBED — Simulation & Stress Test Framework")
    print("=" * 60)
    print(f"  API:    {config.api_url}")
    print(f"  Suites: {', '.join(config.resolved_suites)}")
    print(f"  Run ID: {config.run_id}")
    print("=" * 60)

    asyncio.run(run_testbed(config))


if __name__ == "__main__":
    main()
