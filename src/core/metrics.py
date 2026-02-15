"""
In-memory metrics collector with Prometheus text format output.

Lightweight, no external dependencies — counters and histograms
reset on process restart. Acceptable for homelab use.
"""

import threading
import time
from collections import defaultdict

import structlog

logger = structlog.get_logger()

# Maximum number of observations kept per histogram
_HISTOGRAM_CAP = 1000


class MetricsCollector:
    """Thread-safe in-memory metrics with Prometheus text rendering."""

    def __init__(self):
        self._lock = threading.Lock()
        self._counters: dict[str, int] = defaultdict(int)
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._gauges: dict[str, float] = defaultdict(float)
        self._start_time = time.time()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def increment(self, name: str, labels: dict[str, str] | None = None, value: int = 1):
        """Increment a counter."""
        key = self._key(name, labels)
        with self._lock:
            self._counters[key] += value

    def observe(self, name: str, labels: dict[str, str] | None = None, *, value: float):
        """Record an observation (e.g. latency) in a histogram."""
        key = self._key(name, labels)
        with self._lock:
            bucket = self._histograms[key]
            bucket.append(value)
            if len(bucket) > _HISTOGRAM_CAP:
                # Keep the most recent half
                self._histograms[key] = bucket[_HISTOGRAM_CAP // 2 :]

    def set_gauge(self, name: str, labels: dict[str, str] | None = None, *, value: float):
        """Set a gauge to an absolute value."""
        key = self._key(name, labels)
        with self._lock:
            self._gauges[key] = value

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def get_counter(self, name: str, labels: dict[str, str] | None = None) -> int:
        key = self._key(name, labels)
        with self._lock:
            return self._counters.get(key, 0)

    def get_histogram_stats(self, name: str, labels: dict[str, str] | None = None) -> dict:
        key = self._key(name, labels)
        with self._lock:
            values = self._histograms.get(key, [])
            if not values:
                return {"count": 0, "sum": 0.0, "avg": 0.0, "p50": 0.0, "p99": 0.0}
            sorted_v = sorted(values)
            return {
                "count": len(sorted_v),
                "sum": sum(sorted_v),
                "avg": sum(sorted_v) / len(sorted_v),
                "p50": sorted_v[len(sorted_v) // 2],
                "p99": sorted_v[min(int(len(sorted_v) * 0.99), len(sorted_v) - 1)],
            }

    # ------------------------------------------------------------------
    # Prometheus text format
    # ------------------------------------------------------------------

    def prometheus_format(self) -> str:
        """Render all metrics in Prometheus text exposition format."""
        lines: list[str] = []

        with self._lock:
            # Uptime gauge
            uptime = time.time() - self._start_time
            lines.append("# HELP recall_uptime_seconds Seconds since process start")
            lines.append("# TYPE recall_uptime_seconds gauge")
            lines.append(f"recall_uptime_seconds {uptime:.1f}")
            lines.append("")

            # Counters
            rendered_counter_names: set[str] = set()
            for key, val in sorted(self._counters.items()):
                base_name = key.split("{")[0] if "{" in key else key
                if base_name not in rendered_counter_names:
                    lines.append(f"# TYPE {base_name} counter")
                    rendered_counter_names.add(base_name)
                lines.append(f"{key} {val}")

            if self._counters:
                lines.append("")

            # Gauges
            rendered_gauge_names: set[str] = set()
            for key, val in sorted(self._gauges.items()):
                base_name = key.split("{")[0] if "{" in key else key
                if base_name not in rendered_gauge_names:
                    lines.append(f"# TYPE {base_name} gauge")
                    rendered_gauge_names.add(base_name)
                lines.append(f"{key} {val}")

            if self._gauges:
                lines.append("")

            # Histograms (summary-style: count, sum, avg)
            rendered_hist_names: set[str] = set()
            for key, values in sorted(self._histograms.items()):
                base_name = key.split("{")[0] if "{" in key else key
                if base_name not in rendered_hist_names:
                    lines.append(f"# TYPE {base_name} summary")
                    rendered_hist_names.add(base_name)
                if values:
                    sorted_v = sorted(values)
                    count = len(sorted_v)
                    total = sum(sorted_v)
                    lines.append(f"{key}_count {count}")
                    lines.append(f"{key}_sum {total:.4f}")

        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _key(name: str, labels: dict[str, str] | None) -> str:
        if not labels:
            return name
        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"


# Singleton
_collector: MetricsCollector | None = None


def get_metrics() -> MetricsCollector:
    """Get or create the metrics collector singleton."""
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector
