"""
TestbedConfig — Configuration for testbed runs.
"""

import argparse
import os
import secrets
from dataclasses import dataclass, field


@dataclass
class TestbedConfig:
    """Configuration for a testbed run."""

    api_url: str = "http://localhost:8200"
    api_key: str = "test"
    run_id: str = field(default_factory=lambda: secrets.token_hex(6))

    # Which suites to run
    suites: list[str] = field(default_factory=lambda: ["all"])

    # General
    timeout_minutes: int = 10
    verbose: bool = False
    no_cleanup: bool = False

    # Stress suite
    stress_concurrency: int = 10
    stress_duration_seconds: int = 60

    # Time acceleration suite
    time_accel_weeks: int = 4
    time_accel_step_hours: int = 24

    # Signal quality suite
    signal_wait_seconds: int = 90

    # Report
    report_dir: str = "tests/simulation/reports"

    # Compare mode
    compare_files: list[str] = field(default_factory=list)

    # Cleanup-only mode
    cleanup_only: str | None = None

    @property
    def all_suite_names(self) -> list[str]:
        return ["lifecycle", "retrieval", "stress", "signals", "time_accel", "adaptive",
                "durability", "documents"]

    @property
    def resolved_suites(self) -> list[str]:
        if "all" in self.suites:
            return self.all_suite_names
        return self.suites


def parse_args() -> TestbedConfig:
    """Parse CLI arguments into a TestbedConfig."""
    parser = argparse.ArgumentParser(
        description="Recall Simulation & Stress Test Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m tests.simulation.testbed                          # Full run
  python -m tests.simulation.testbed --suites lifecycle,retrieval
  python -m tests.simulation.testbed --suites stress --stress-concurrency 20
  python -m tests.simulation.testbed --compare reports/a.json reports/b.json
  python -m tests.simulation.testbed --cleanup-only abc123def456
""",
    )

    parser.add_argument("--api", default=None, help="Recall API URL")
    parser.add_argument("--api-key", default=None, help="API key")
    parser.add_argument("--suites", default="all", help="Comma-separated suite names or 'all'")
    parser.add_argument("--timeout", type=int, default=10, help="Timeout in minutes (default: 10)")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--no-cleanup", action="store_true", help="Skip cleanup after run")

    parser.add_argument("--stress-concurrency", type=int, default=10)
    parser.add_argument("--stress-duration", type=int, default=60)
    parser.add_argument("--time-accel-weeks", type=int, default=4)
    parser.add_argument("--time-accel-step", type=int, default=24)
    parser.add_argument("--signal-wait", type=int, default=90)

    parser.add_argument("--report-dir", default="tests/simulation/reports")
    parser.add_argument("--compare", nargs=2, metavar="FILE", help="Compare two JSON reports")
    parser.add_argument("--cleanup-only", metavar="RUN_ID", help="Clean up a previous run")

    args = parser.parse_args()

    config = TestbedConfig(
        api_url=args.api or os.environ.get("RECALL_API_URL", "http://localhost:8200"),
        api_key=args.api_key or os.environ.get("RECALL_API_KEY", "test"),
        suites=[s.strip() for s in args.suites.split(",")],
        timeout_minutes=args.timeout,
        verbose=args.verbose,
        no_cleanup=args.no_cleanup,
        stress_concurrency=args.stress_concurrency,
        stress_duration_seconds=args.stress_duration,
        time_accel_weeks=args.time_accel_weeks,
        time_accel_step_hours=args.time_accel_step,
        signal_wait_seconds=args.signal_wait,
        report_dir=args.report_dir,
        compare_files=args.compare or [],
        cleanup_only=args.cleanup_only,
    )

    return config
