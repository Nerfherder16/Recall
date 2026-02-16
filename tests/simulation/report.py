"""
Report generation — JSON reports, console summaries, and run comparison.
"""

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SuiteReport:
    """Report from a single test suite."""

    suite_name: str
    duration_seconds: float
    passed: bool
    metrics: dict[str, Any] = field(default_factory=dict)
    observations: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class TestbedReport:
    """Aggregated report from a full testbed run."""

    run_id: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    api_url: str = ""
    total_duration_seconds: float = 0.0
    health_baseline: dict[str, Any] = field(default_factory=dict)
    latency_summary: dict[str, Any] = field(default_factory=dict)
    suites: list[SuiteReport] = field(default_factory=list)
    rate_limited_count: int = 0

    @property
    def all_passed(self) -> bool:
        return all(s.passed for s in self.suites)

    def save_json(self, report_dir: str) -> str:
        """Save report as timestamped JSON. Returns the file path."""
        os.makedirs(report_dir, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"testbed_{self.run_id}_{ts}.json"
        filepath = os.path.join(report_dir, filename)

        data = {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "api_url": self.api_url,
            "total_duration_seconds": round(self.total_duration_seconds, 2),
            "all_passed": self.all_passed,
            "health_baseline": self.health_baseline,
            "latency_summary": self.latency_summary,
            "rate_limited_count": self.rate_limited_count,
            "suites": [asdict(s) for s in self.suites],
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)

        return filepath

    def print_summary(self):
        """Print a formatted console summary."""
        print()
        print("=" * 70)
        print(f"  TESTBED REPORT — run {self.run_id}")
        print(f"  {self.timestamp}")
        print("=" * 70)
        print()

        # Suite results table
        print(f"  {'Suite':<20} {'Status':<10} {'Duration':<12} {'Errors':<8} {'Observations'}")
        print(f"  {'-'*20} {'-'*10} {'-'*12} {'-'*8} {'-'*15}")

        for s in self.suites:
            status = "PASS" if s.passed else "FAIL"
            duration = f"{s.duration_seconds:.1f}s"
            errors = str(len(s.errors))
            obs = str(len(s.observations))
            print(f"  {s.suite_name:<20} {status:<10} {duration:<12} {errors:<8} {obs}")

        print()

        # Key metrics per suite
        for s in self.suites:
            if s.metrics:
                print(f"  [{s.suite_name}] Key metrics:")
                _print_metrics(s.metrics, indent=4)
                print()

            if s.errors:
                print(f"  [{s.suite_name}] Errors:")
                for e in s.errors[:5]:
                    print(f"    - {e}")
                if len(s.errors) > 5:
                    print(f"    ... and {len(s.errors) - 5} more")
                print()

        # Latency summary
        if self.latency_summary:
            print("  Latency Summary:")
            for op, stats in sorted(self.latency_summary.items()):
                if isinstance(stats, dict) and stats.get("count", 0) > 0:
                    print(f"    {op}: {stats['count']} calls, "
                          f"p50={stats.get('p50', 0)*1000:.0f}ms, "
                          f"p95={stats.get('p95', 0)*1000:.0f}ms, "
                          f"p99={stats.get('p99', 0)*1000:.0f}ms")
            print()

        if self.rate_limited_count > 0:
            print(f"  Rate limited: {self.rate_limited_count} requests")
            print()

        overall = "ALL PASSED" if self.all_passed else "FAILURES DETECTED"
        total_time = f"{self.total_duration_seconds:.1f}s"
        print(f"  Result: {overall} in {total_time}")
        print("=" * 70)
        print()


def _print_metrics(metrics: dict, indent: int = 0):
    """Recursively print metrics dict with indentation."""
    prefix = " " * indent
    for key, value in metrics.items():
        if isinstance(value, dict):
            print(f"{prefix}{key}:")
            _print_metrics(value, indent + 2)
        elif isinstance(value, list) and len(value) > 3:
            print(f"{prefix}{key}: [{len(value)} items]")
        elif isinstance(value, float):
            print(f"{prefix}{key}: {value:.4f}")
        else:
            print(f"{prefix}{key}: {value}")


def compare_reports(path_a: str, path_b: str):
    """Load two JSON reports and print a side-by-side comparison."""
    with open(path_a) as f:
        a = json.load(f)
    with open(path_b) as f:
        b = json.load(f)

    print()
    print("=" * 70)
    print("  TESTBED COMPARISON")
    print("=" * 70)
    print()
    print(f"  {'':25} {'Run A':>20} {'Run B':>20}")
    print(f"  {'-'*25} {'-'*20} {'-'*20}")
    print(f"  {'Run ID':25} {a['run_id']:>20} {b['run_id']:>20}")
    print(f"  {'Timestamp':25} {a['timestamp'][:19]:>20} {b['timestamp'][:19]:>20}")
    print(f"  {'Duration':25} {a['total_duration_seconds']:>19.1f}s {b['total_duration_seconds']:>19.1f}s")
    print(f"  {'All passed':25} {str(a['all_passed']):>20} {str(b['all_passed']):>20}")
    print(f"  {'Rate limited':25} {a.get('rate_limited_count', 0):>20} {b.get('rate_limited_count', 0):>20}")
    print()

    # Suite-by-suite comparison
    suites_a = {s["suite_name"]: s for s in a.get("suites", [])}
    suites_b = {s["suite_name"]: s for s in b.get("suites", [])}
    all_names = sorted(set(list(suites_a.keys()) + list(suites_b.keys())))

    for name in all_names:
        sa = suites_a.get(name)
        sb = suites_b.get(name)
        print(f"  [{name}]")

        if sa and sb:
            status_a = "PASS" if sa["passed"] else "FAIL"
            status_b = "PASS" if sb["passed"] else "FAIL"
            print(f"    {'Status':23} {status_a:>20} {status_b:>20}")
            print(f"    {'Duration':23} {sa['duration_seconds']:>19.1f}s {sb['duration_seconds']:>19.1f}s")
            print(f"    {'Errors':23} {len(sa.get('errors', [])):>20} {len(sb.get('errors', [])):>20}")

            # Compare common metrics
            ma = sa.get("metrics", {})
            mb = sb.get("metrics", {})
            common_keys = sorted(set(list(ma.keys())) & set(list(mb.keys())))
            for key in common_keys:
                va = ma[key]
                vb = mb[key]
                if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                    delta = vb - va
                    sign = "+" if delta > 0 else ""
                    print(f"    {key:23} {va:>20.4f} {vb:>20.4f}  ({sign}{delta:.4f})")
        elif sa:
            print(f"    Only in Run A")
        else:
            print(f"    Only in Run B")
        print()

    # Latency comparison
    la = a.get("latency_summary", {})
    lb = b.get("latency_summary", {})
    common_ops = sorted(set(list(la.keys())) & set(list(lb.keys())))

    if common_ops:
        print("  Latency Comparison (p50 ms):")
        for op in common_ops:
            p50_a = la[op].get("p50", 0) * 1000
            p50_b = lb[op].get("p50", 0) * 1000
            delta = p50_b - p50_a
            sign = "+" if delta > 0 else ""
            print(f"    {op:40} {p50_a:>8.0f} {p50_b:>8.0f}  ({sign}{delta:.0f})")
        print()

    print("=" * 70)
    print()
