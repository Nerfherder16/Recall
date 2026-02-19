"""
Operator persona — Admin operations and system monitoring.

Rotates through: health check, decay, consolidation, stats, audit, reconcile,
reranker status, reranker retrain (1x/hour).
One admin call per cycle to stay under 10/min.
Cycle interval: 8s.
"""

from .base import BasePersona


# Admin operations in rotation order
ADMIN_OPS = [
    "health",
    "stats",
    "decay",
    "domain_stats",
    "audit",
    "health_dashboard",
    "reconcile",
    "reranker_status",
    "consolidation",
    "stats",
    "decay",
    "ollama_info",
]


class Operator(BasePersona):
    name = "operator"
    cycle_interval = 8.0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._op_index = 0
        self._retrain_count = 0
        self._cycles_per_hour = int(3600 / self.cycle_interval)

    def _next_op(self) -> str:
        op = ADMIN_OPS[self._op_index % len(ADMIN_OPS)]
        self._op_index += 1
        return op

    async def cycle(self):
        # Reranker retrain once per hour
        if self.cycles > 0 and self.cycles % self._cycles_per_hour == 0:
            await self.scheduler.acquire("admin")
            result = await self.client._request("POST", "/admin/ml/retrain-ranker")
            if result:
                self.count_op("reranker_retrains")
                self._retrain_count += 1
            else:
                self.record_error("reranker retrain failed")
            return  # Skip normal rotation this cycle

        op = self._next_op()
        await self.scheduler.acquire("admin")

        if op == "health":
            result = await self.client.health()
            if result:
                self.count_op("health_checks")
            else:
                self.record_error("health check failed")

        elif op == "stats":
            result = await self.client.stats()
            if result:
                self.count_op("stats_checks")
            else:
                self.record_error("stats check failed")

        elif op == "decay":
            # Simulate 6 hours of decay
            result = await self.client.decay(simulate_hours=6.0)
            if result:
                self.count_op("decay_runs")
            else:
                self.record_error("decay run failed")

        elif op == "domain_stats":
            result = await self.client._request("GET", "/stats/domains")
            if result:
                self.count_op("domain_stats")
            else:
                self.record_error("domain stats failed")

        elif op == "audit":
            result = await self.client._request("GET", "/admin/audit?limit=10")
            if result:
                self.count_op("audit_checks")
            else:
                self.record_error("audit check failed")

        elif op == "health_dashboard":
            result = await self.client._request("GET", "/admin/health/dashboard")
            if result:
                self.count_op("health_dashboards")
            else:
                self.record_error("health dashboard failed")

        elif op == "reconcile":
            result = await self.client.reconcile(repair=False)
            if result:
                self.count_op("reconcile_checks")
            else:
                self.record_error("reconcile check failed")

        elif op == "reranker_status":
            result = await self.client._request("GET", "/admin/ml/reranker-status")
            if result:
                self.count_op("reranker_status_checks")
            else:
                self.record_error("reranker status failed")

        elif op == "consolidation":
            # Consolidate only sim domains
            result = await self.client.consolidate(
                domain=self.domain_prefix, dry_run=True,
            )
            if result:
                self.count_op("consolidation_runs")
            else:
                self.record_error("consolidation failed")

        elif op == "ollama_info":
            result = await self.client.ollama_info()
            if result:
                self.count_op("ollama_checks")
            else:
                self.record_error("ollama info failed")
