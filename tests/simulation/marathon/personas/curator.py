"""
Curator persona — Feedback, pinning, and durability management.

Retrieves stored memories, submits feedback (60% useful / 40% not-useful).
Every 10th cycle: pins high-importance memories.
Every 15th cycle: sets durability tiers.
Cycle interval: 12s.
"""

import random

from .base import BasePersona


class Curator(BasePersona):
    name = "curator"
    cycle_interval = 12.0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._feedback_pool: list[str] = []  # memory IDs eligible for feedback

    async def cycle(self):
        # Refresh feedback pool from tracked IDs periodically
        if self.cycles % 5 == 0 or not self._feedback_pool:
            self._feedback_pool = list(self.client.tracked_ids[-100:])

        # Main action: submit feedback
        if len(self._feedback_pool) >= 2:
            # Pick 1-3 memory IDs for feedback
            sample_size = min(random.randint(1, 3), len(self._feedback_pool))
            sample_ids = random.sample(self._feedback_pool, sample_size)

            # 60% useful (assistant mentions the content), 40% not useful
            is_useful = random.random() < 0.6
            if is_useful:
                assistant_text = (
                    "Based on the memory about this topic, here's the relevant information. "
                    "The stored knowledge was directly applicable to the current task."
                )
            else:
                assistant_text = (
                    "I'll help with that request. Let me look into the specific details "
                    "and provide a fresh analysis of the situation."
                )

            await self.scheduler.acquire("default")
            result = await self.client.submit_feedback(sample_ids, assistant_text)
            if result:
                self.count_op("feedback_useful" if is_useful else "feedback_not_useful")
                self.count_op("feedback_total")
            else:
                self.record_error("feedback submission failed")

        # Every 10th cycle: pin a high-importance memory
        if self.cycles % 10 == 0 and self.client.tracked_ids:
            target_id = random.choice(self.client.tracked_ids[-50:])
            await self.scheduler.acquire("default")
            result = await self.client.pin_memory(target_id)
            if result:
                self.count_op("pins")
            else:
                self.record_error(f"pin failed for {target_id[:12]}")

        # Every 15th cycle: set durability tier
        if self.cycles % 15 == 0 and self.client.tracked_ids:
            target_id = random.choice(self.client.tracked_ids[-50:])
            tier = random.choices(
                ["ephemeral", "durable", "permanent"],
                weights=[0.3, 0.5, 0.2],
            )[0]
            await self.scheduler.acquire("default")
            result = await self.client.put_durability(target_id, tier)
            if result:
                self.count_op(f"durability_{tier}")
                self.count_op("durability_total")
            else:
                self.record_error(f"durability set failed for {target_id[:12]}")

    def summary(self) -> dict:
        base = super().summary()
        total_fb = self.ops.get("feedback_total", 0)
        useful = self.ops.get("feedback_useful", 0)
        base["useful_feedback_ratio"] = round(useful / total_fb, 3) if total_fb > 0 else 0.0
        return base
