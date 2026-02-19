"""
Researcher persona — Heavy reader with varied search queries.

Picks from 40 search queries, searches via browse/query/timeline.
Tracks result counts and score trends over time.
Cycle interval: 8s (~7 cycles/min).
"""

import random

from ..corpus import SEARCH_QUERIES
from .base import BasePersona


class Researcher(BasePersona):
    name = "researcher"
    cycle_interval = 8.0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._query_index = 0
        self.score_history: list[dict] = []  # {query, top_score, avg_score, count}

    def _next_query(self) -> str:
        q = SEARCH_QUERIES[self._query_index % len(SEARCH_QUERIES)]
        self._query_index += 1
        return q

    async def cycle(self):
        query = self._next_query()

        # Default: browse search
        search_type = "browse"

        # Every 5th cycle: full query search
        if self.cycles % 5 == 0:
            search_type = "query"
        # Every 10th cycle: timeline scan
        elif self.cycles % 10 == 0:
            search_type = "timeline"

        await self.scheduler.acquire("search")

        if search_type == "browse":
            results = await self.client.search_browse(query, limit=10)
            self.count_op("browse_searches")
        elif search_type == "query":
            results = await self.client.search_query(query, limit=10)
            self.count_op("query_searches")
        else:
            results = await self.client.search_timeline(limit=20)
            self.count_op("timeline_scans")

        self.count_op("total_searches")

        # Track scores
        if results and search_type != "timeline":
            scores = [
                r.get("similarity", r.get("score", 0.0))
                for r in results
                if isinstance(r, dict)
            ]
            if scores:
                entry = {
                    "query": query[:40],
                    "type": search_type,
                    "top_score": round(max(scores), 4),
                    "avg_score": round(sum(scores) / len(scores), 4),
                    "count": len(results),
                }
                self.score_history.append(entry)
                # Cap history
                if len(self.score_history) > 500:
                    self.score_history = self.score_history[-300:]

    def summary(self) -> dict:
        base = super().summary()
        if self.score_history:
            top_scores = [e["top_score"] for e in self.score_history]
            avg_scores = [e["avg_score"] for e in self.score_history]
            base["avg_top_score"] = round(sum(top_scores) / len(top_scores), 4)
            base["avg_avg_score"] = round(sum(avg_scores) / len(avg_scores), 4)

            # Score trend: split into quarters
            n = len(top_scores)
            if n >= 4:
                q = n // 4
                base["score_trend"] = [
                    round(sum(top_scores[i*q:(i+1)*q]) / q, 4)
                    for i in range(4)
                ]
        return base
