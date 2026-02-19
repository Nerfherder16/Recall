"""
Archivist persona — Heavy writer that stores from corpus and verifies retrieval.

Stores 3-5 memories per cycle from the 200+ corpus, cycling through subdomains.
Every 3rd cycle: searches own recent stores to verify retrieval works.
Cycle interval: 15s (~4 cycles/min).
"""

import random

from ..corpus import MEMORIES, SUBDOMAINS
from .base import BasePersona


class Archivist(BasePersona):
    name = "archivist"
    cycle_interval = 15.0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Build flat list of (subdomain, memory) pairs for round-robin
        self._corpus: list[tuple[str, dict]] = []
        for sub in SUBDOMAINS:
            for mem in MEMORIES.get(sub, []):
                self._corpus.append((sub, mem))
        random.shuffle(self._corpus)
        self._index = 0
        self._recent_contents: list[str] = []

    def _next_batch(self, n: int) -> list[tuple[str, dict]]:
        """Get next N items from corpus, wrapping around."""
        batch = []
        for _ in range(n):
            batch.append(self._corpus[self._index % len(self._corpus)])
            self._index += 1
        return batch

    async def cycle(self):
        # Store 3-5 memories
        batch_size = random.randint(3, 5)
        batch = self._next_batch(batch_size)
        stored = 0

        for subdomain, mem in batch:
            await self.scheduler.acquire("default")
            result = await self.client.store_memory(
                content=mem["content"],
                domain=self.domain(subdomain),
                memory_type=mem.get("type", "semantic"),
                importance=mem.get("importance", 0.5),
                tags=[f"persona:archivist"],
            )
            if result and result.get("id"):
                stored += 1
                self._recent_contents.append(mem["content"])
                # Keep only last 30 for retrieval verification
                if len(self._recent_contents) > 30:
                    self._recent_contents = self._recent_contents[-30:]
            else:
                self.record_error(f"store failed for: {mem['content'][:50]}")

        self.count_op("stores", stored)

        # Every 3rd cycle: verify retrieval of a recent store
        if self.cycles % 3 == 0 and self._recent_contents:
            query_content = random.choice(self._recent_contents)
            # Use first 60 chars as search query
            query = query_content[:60]
            await self.scheduler.acquire("search")
            results = await self.client.search_browse(query, limit=5)
            self.count_op("verification_searches")

            if results:
                # Check if any result content matches what we stored
                found = any(
                    query_content[:40] in r.get("content", r.get("summary", ""))
                    for r in results
                )
                if found:
                    self.count_op("retrieval_hits")
                else:
                    self.count_op("retrieval_misses")
            else:
                self.count_op("retrieval_misses")

    def summary(self) -> dict:
        base = super().summary()
        searches = self.ops.get("verification_searches", 0)
        hits = self.ops.get("retrieval_hits", 0)
        base["retrieval_hit_rate"] = round(hits / searches, 3) if searches > 0 else 0.0
        return base
