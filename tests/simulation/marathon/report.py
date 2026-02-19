"""
MarathonReport — JSON report generation with analysis derivation and console summary.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .metrics import MetricSnapshot


@dataclass
class MarathonReport:
    """Full marathon simulation report."""

    run_id: str
    duration_hours: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    snapshots: list[MetricSnapshot] = field(default_factory=list)
    personas: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    rate_limit_hits: int = 0
    latency_summary: dict[str, Any] = field(default_factory=dict)

    def derive_analysis(self) -> dict[str, Any]:
        """Compute trend analysis from snapshots."""
        analysis: dict[str, Any] = {}

        if len(self.snapshots) < 2:
            return analysis

        # Memory population trend
        pop = [s.total_memories for s in self.snapshots]
        analysis["memory_population"] = pop

        # Net growth rate (memories per hour)
        first, last = self.snapshots[0], self.snapshots[-1]
        elapsed_h = max(last.elapsed_minutes - first.elapsed_minutes, 1) / 60.0
        analysis["net_memory_growth_rate"] = round(
            (last.total_memories - first.total_memories) / elapsed_h, 1
        )

        # Edge growth rate
        edges = [s.graph_edges for s in self.snapshots]
        analysis["edge_growth_rate"] = round(
            (last.graph_edges - first.graph_edges) / elapsed_h, 1
        )

        # Retrieval score trend (from researcher persona if available)
        researcher = self.personas.get("researcher", {})
        if "score_trend" in researcher:
            analysis["retrieval_score_trend"] = researcher["score_trend"]

        # Importance distribution trend (from snapshots)
        imp_trend = []
        for s in self.snapshots:
            if s.importance_distribution:
                imp_trend.append(s.importance_distribution)
        if imp_trend:
            analysis["importance_trend"] = [imp_trend[0], imp_trend[-1]]

        # Reranker CV trend
        cv_scores = [
            s.reranker_cv_score for s in self.snapshots
            if s.reranker_cv_score is not None
        ]
        if cv_scores:
            analysis["reranker_cv_trend"] = cv_scores

        # Useful feedback ratio trend (from curator)
        curator = self.personas.get("curator", {})
        if "useful_feedback_ratio" in curator:
            analysis["useful_feedback_ratio"] = curator["useful_feedback_ratio"]

        # Latency trend: compare first half vs second half p50
        if len(self.snapshots) >= 4:
            mid = len(self.snapshots) // 2
            first_half = self.snapshots[:mid]
            second_half = self.snapshots[mid:]
            lat_trend: dict[str, dict] = {}
            for op in set().union(
                *(s.latency_p50.keys() for s in self.snapshots if s.latency_p50)
            ):
                p50_first = [s.latency_p50.get(op, 0) for s in first_half if op in s.latency_p50]
                p50_second = [s.latency_p50.get(op, 0) for s in second_half if op in s.latency_p50]
                if p50_first and p50_second:
                    lat_trend[op] = {
                        "first_half_p50": round(sum(p50_first) / len(p50_first) * 1000, 1),
                        "second_half_p50": round(sum(p50_second) / len(p50_second) * 1000, 1),
                    }
            if lat_trend:
                analysis["latency_trend"] = lat_trend

        return analysis

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "duration_hours": round(self.duration_hours, 2),
            "timestamp": self.timestamp,
            "snapshots": [s.to_dict() for s in self.snapshots],
            "personas": self.personas,
            "analysis": self.derive_analysis(),
            "errors": self.errors,
            "rate_limit_hits": self.rate_limit_hits,
            "latency_summary": self.latency_summary,
        }

    def save_json(self, report_dir: str) -> str:
        """Save report as JSON. Returns the file path."""
        os.makedirs(report_dir, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"marathon_{self.run_id}_{ts}.json"
        filepath = os.path.join(report_dir, filename)

        with open(filepath, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)

        return filepath

    def print_summary(self):
        """Print human-readable console summary."""
        print()
        print("=" * 70)
        print(f"  MARATHON REPORT — run {self.run_id}")
        print(f"  {self.timestamp} | Duration: {self.duration_hours:.2f}h")
        print("=" * 70)
        print()

        # Persona summaries
        print(f"  {'Persona':<18} {'Cycles':>8} {'Ops':>8} {'Errors':>8} {'Key Metric'}")
        print(f"  {'-'*18} {'-'*8} {'-'*8} {'-'*8} {'-'*25}")

        for name, data in self.personas.items():
            cycles = data.get("cycles", 0)
            total_ops = sum(data.get("ops", {}).values())
            errors = data.get("error_count", 0)
            key = _persona_key_metric(name, data)
            print(f"  {name:<18} {cycles:>8} {total_ops:>8} {errors:>8} {key}")

        print()

        # Analysis highlights
        analysis = self.derive_analysis()
        if analysis:
            print("  Analysis:")
            rate = analysis.get("net_memory_growth_rate", 0)
            print(f"    Memory growth: {rate:.1f}/hour")
            edge_rate = analysis.get("edge_growth_rate", 0)
            print(f"    Edge growth:   {edge_rate:.1f}/hour")
            if "retrieval_score_trend" in analysis:
                trend = analysis["retrieval_score_trend"]
                print(f"    Score trend:   {trend}")
            if "reranker_cv_trend" in analysis:
                cv = analysis["reranker_cv_trend"]
                print(f"    Reranker CV:   first={cv[0]}, last={cv[-1]}")
            print()

        # Latency highlights
        if self.latency_summary:
            print("  Top Latencies (p95):")
            sorted_ops = sorted(
                ((op, s) for op, s in self.latency_summary.items()
                 if isinstance(s, dict) and s.get("count", 0) > 0),
                key=lambda x: x[1].get("p95", 0),
                reverse=True,
            )
            for op, stats in sorted_ops[:8]:
                print(f"    {op:40} {stats['count']:>5} calls  "
                      f"p50={stats['p50']*1000:.0f}ms  p95={stats['p95']*1000:.0f}ms")
            print()

        if self.rate_limit_hits > 0:
            print(f"  Rate limited: {self.rate_limit_hits} requests")
            print()

        if self.errors:
            print(f"  Errors ({len(self.errors)} total):")
            for e in self.errors[:10]:
                print(f"    - {e}")
            if len(self.errors) > 10:
                print(f"    ... and {len(self.errors) - 10} more")
            print()

        snaps = len(self.snapshots)
        if snaps > 0:
            last = self.snapshots[-1]
            print(f"  Final state: {last.total_memories} memories, "
                  f"{last.graph_nodes} nodes, {last.graph_edges} edges")
        print(f"  Snapshots collected: {snaps}")
        print("=" * 70)
        print()


def _persona_key_metric(name: str, data: dict) -> str:
    """Extract the most interesting metric for each persona."""
    if name == "archivist":
        rate = data.get("retrieval_hit_rate", 0)
        stores = data.get("ops", {}).get("stores", 0)
        return f"stores={stores} hit_rate={rate:.0%}"
    elif name == "researcher":
        avg = data.get("avg_top_score", 0)
        searches = data.get("ops", {}).get("total_searches", 0)
        return f"searches={searches} avg_top={avg:.3f}"
    elif name == "curator":
        ratio = data.get("useful_feedback_ratio", 0)
        fb = data.get("ops", {}).get("feedback_total", 0)
        return f"feedback={fb} useful={ratio:.0%}"
    elif name == "operator":
        ops = data.get("ops", {})
        decays = ops.get("decay_runs", 0)
        return f"decays={decays} retrains={ops.get('reranker_retrains', 0)}"
    elif name == "session_worker":
        sessions = data.get("ops", {}).get("sessions_started", 0)
        det = data.get("signal_detection_rate", 0)
        return f"sessions={sessions} sig_rate={det:.1f}"
    return ""
