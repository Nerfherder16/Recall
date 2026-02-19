"""
MarathonConfig — Configuration for marathon simulation runs.
"""

import argparse
import os
import secrets
from dataclasses import dataclass, field


@dataclass
class MarathonConfig:
    """Configuration for a marathon simulation run."""

    api_url: str = "http://localhost:8200"
    api_key: str = "test"
    run_id: str = field(default_factory=lambda: secrets.token_hex(6))

    # Duration in hours (0.15 = ~10min dry run, 4.0 = typical marathon)
    duration_hours: float = 4.0

    # General
    verbose: bool = False
    no_cleanup: bool = False

    # Metrics snapshot interval in seconds
    snapshot_interval: int = 300  # 5 minutes

    # Progress line interval in seconds
    progress_interval: int = 120  # 2 minutes

    # Report
    report_dir: str = "tests/simulation/reports/marathon"

    # Cleanup-only mode
    cleanup_only: str | None = None

    def domain_prefix(self) -> str:
        return f"sim-marathon-{self.run_id}"


def parse_args() -> MarathonConfig:
    """Parse CLI arguments into a MarathonConfig."""
    parser = argparse.ArgumentParser(
        description="Recall Marathon Simulation — Long-running unattended stress test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m tests.simulation.marathon                              # 4-hour default run
  python -m tests.simulation.marathon --duration 0.15              # 10-min dry run
  python -m tests.simulation.marathon --duration 6 --verbose       # 6-hour verbose run
  python -m tests.simulation.marathon --cleanup-only abc123def456  # Cleanup previous run
""",
    )

    parser.add_argument("--api", default=None, help="Recall API URL")
    parser.add_argument("--api-key", default=None, help="API key")
    parser.add_argument("--duration", type=float, default=4.0, help="Duration in hours (default: 4.0)")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--no-cleanup", action="store_true", help="Skip cleanup after run")
    parser.add_argument("--snapshot-interval", type=int, default=300, help="Metrics snapshot interval (seconds)")
    parser.add_argument("--progress-interval", type=int, default=120, help="Progress line interval (seconds)")
    parser.add_argument("--report-dir", default="tests/simulation/reports/marathon")
    parser.add_argument("--cleanup-only", metavar="RUN_ID", help="Clean up a previous run")

    args = parser.parse_args()

    return MarathonConfig(
        api_url=args.api or os.environ.get("RECALL_API_URL", "http://localhost:8200"),
        api_key=args.api_key or os.environ.get("RECALL_API_KEY", "test"),
        duration_hours=args.duration,
        verbose=args.verbose,
        no_cleanup=args.no_cleanup,
        snapshot_interval=args.snapshot_interval,
        progress_interval=args.progress_interval,
        report_dir=args.report_dir,
        cleanup_only=args.cleanup_only,
    )
