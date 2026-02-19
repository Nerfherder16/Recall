"""
SessionWorker persona — Session lifecycle and signal pipeline.

Creates sessions, ingests conversation turns, checks/approves signals, ends sessions.
New session every ~5 cycles, 2 turns ingested per cycle.
Cycle interval: 6s.
"""

import random

from ..corpus import CONVERSATIONS
from .base import BasePersona


class SessionWorker(BasePersona):
    name = "session_worker"
    cycle_interval = 6.0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._conv_index = 0
        self._active_session: str | None = None
        self._active_turns: list[tuple[str, str]] = []
        self._turn_offset = 0

    def _next_conversation(self) -> dict:
        conv = CONVERSATIONS[self._conv_index % len(CONVERSATIONS)]
        self._conv_index += 1
        return conv

    async def _start_new_session(self):
        """Start a new session with the next conversation."""
        conv = self._next_conversation()
        await self.scheduler.acquire("ingest")
        sid = await self.client.create_session(task=conv["task"])
        if sid:
            self._active_session = sid
            self._active_turns = list(conv["turns"])
            self._turn_offset = 0
            self.count_op("sessions_started")
        else:
            self.record_error("session start failed")

    async def _ingest_turns(self):
        """Ingest the next 2 turns of the active conversation."""
        if not self._active_session or not self._active_turns:
            return

        remaining = self._active_turns[self._turn_offset:]
        batch = remaining[:2]
        if not batch:
            return

        turns = [{"role": role, "content": content} for role, content in batch]
        await self.scheduler.acquire("ingest")
        result = await self.client.ingest_turns(self._active_session, turns)
        if result:
            self._turn_offset += len(batch)
            self.count_op("turns_ingested", len(batch))
        else:
            self.record_error("turn ingestion failed")

    async def _check_signals(self):
        """Check for pending signals and approve the first one."""
        if not self._active_session:
            return

        await self.scheduler.acquire("ingest")
        signals = await self.client.get_signals(self._active_session)
        if signals:
            self.count_op("signals_detected", len(signals))
            # Approve the first pending signal
            await self.scheduler.acquire("ingest")
            result = await self.client.approve_signal(self._active_session, 0)
            if result:
                self.count_op("signals_approved")
                # Track the created memory ID
                mem_id = result.get("memory_id") or result.get("id")
                if mem_id:
                    self.client.tracked_ids.append(mem_id)

    async def _end_session(self):
        """End the active session."""
        if not self._active_session:
            return

        await self.scheduler.acquire("ingest")
        await self.client.end_session(self._active_session)
        self.count_op("sessions_ended")
        self._active_session = None
        self._active_turns = []
        self._turn_offset = 0

    async def cycle(self):
        # Every 5 cycles or no active session: start new session
        if self._active_session is None or self.cycles % 5 == 0:
            if self._active_session is not None:
                await self._end_session()
            await self._start_new_session()
            return

        # Ingest turns if we have remaining
        if self._turn_offset < len(self._active_turns):
            await self._ingest_turns()

            # After ingesting all turns, check signals on next cycle
            if self._turn_offset >= len(self._active_turns):
                # Small delay for signal detection to process
                return
        else:
            # All turns ingested — check signals then end session
            await self._check_signals()
            await self._end_session()

    def summary(self) -> dict:
        base = super().summary()
        sessions = self.ops.get("sessions_started", 0)
        detected = self.ops.get("signals_detected", 0)
        approved = self.ops.get("signals_approved", 0)
        base["signal_detection_rate"] = round(detected / sessions, 2) if sessions > 0 else 0.0
        base["signal_approval_rate"] = round(approved / max(detected, 1), 3)
        return base
