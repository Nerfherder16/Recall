"""
Signal Quality Suite — Tests signal detection rate, confidence, and type accuracy.

Requires Ollama + qwen3:14b available. Skips gracefully if not.

Checks both pending signals (medium-confidence) and auto-stored signals
(high-confidence) via session status polling.
"""

import asyncio
import time

from tests.simulation.data.conversation_turns import TEST_CONVERSATIONS
from tests.simulation.report import SuiteReport

from .base import BaseSuite


class SignalQualitySuite(BaseSuite):
    name = "signals"

    async def _poll_signals_detected(self, sid: str, timeout: float = 30.0) -> int:
        """Poll session status until signals_detected > 0 or timeout."""
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            status = await self.client.get_session_status(sid)
            if status:
                detected = int(status.get("signals_detected", 0))
                if detected > 0:
                    return detected
            await asyncio.sleep(5)
        # Final check
        status = await self.client.get_session_status(sid)
        return int(status.get("signals_detected", 0)) if status else 0

    async def run(self) -> SuiteReport:
        t0 = time.monotonic()
        passed = True

        try:
            # Check Ollama availability
            self.observe("Checking Ollama availability...")
            ollama = await self.client.ollama_info()

            if not ollama or ollama.get("version") in ("unreachable", "error"):
                self.observe("Ollama not available — skipping signal quality suite")
                self.metric("skipped", True)
                self.metric("skip_reason", "Ollama unavailable")
                return self._make_report(True, time.monotonic() - t0)

            models = [m.get("name", "") for m in ollama.get("models", [])]
            has_qwen = any("qwen3" in m for m in models)
            if not has_qwen:
                self.observe(f"qwen3 model not found (available: {models}) — skipping")
                self.metric("skipped", True)
                self.metric("skip_reason", "qwen3 model not available")
                return self._make_report(True, time.monotonic() - t0)

            self.observe(f"Ollama v{ollama.get('version')} available with qwen3")

            # ── Run each test conversation ──
            wait_seconds = self.config.signal_wait_seconds
            per_conversation: list[dict] = []
            all_signals: list[dict] = []
            match_count = 0
            total_auto_stored = 0

            for conv in TEST_CONVERSATIONS:
                desc = conv["description"]
                expected = conv["expected_signals"]
                turns = conv["turns"]

                self.observe(f"Running conversation: {desc}")

                # Start session
                sid = await self.client.create_session(f"signal-test: {desc}")
                if not sid:
                    self.error(f"Failed to create session for: {desc}")
                    continue

                # Ingest turns
                turn_dicts = [
                    {"role": role, "content": content}
                    for role, content in turns
                ]
                r = await self.client.ingest_turns(sid, turn_dicts)
                await asyncio.sleep(3)  # Rate limit: 20/min for ingest

                if r is None:
                    self.error(f"Failed to ingest turns for: {desc}")
                    await self.client.end_session(sid)
                    continue

                # Poll for signal detection (checks session status for signals_detected)
                self.observe(f"  Polling for signals (up to {wait_seconds}s)...")
                auto_stored = await self._poll_signals_detected(sid, timeout=wait_seconds)

                # Also check pending signals (medium-confidence)
                pending_signals = await self.client.get_signals(sid)
                detected_types = [s.get("signal_type", "") for s in pending_signals]
                confidences = [s.get("confidence", 0.0) for s in pending_signals]

                # Total signal count = auto-stored (from session) + pending
                total_signals = auto_stored + len(pending_signals)
                total_auto_stored += auto_stored

                # Check if expected types appeared
                match = False
                if not expected:
                    # No signals expected — success if few/no signals
                    match = total_signals <= 1
                else:
                    # At least one expected type in pending, OR auto-stored > 0
                    match = (
                        any(et in detected_types for et in expected)
                        or auto_stored > 0
                    )

                if match:
                    match_count += 1

                conv_result = {
                    "description": desc,
                    "expected_types": expected,
                    "detected_types": detected_types,
                    "pending_count": len(pending_signals),
                    "auto_stored_count": auto_stored,
                    "total_signals": total_signals,
                    "match": match,
                    "confidences": [round(c, 3) for c in confidences],
                }
                per_conversation.append(conv_result)
                all_signals.extend(pending_signals)

                self.observe(
                    f"  Detected {total_signals} signals "
                    f"(auto={auto_stored}, pending={len(pending_signals)}) "
                    f"match={match}"
                )

                # End session
                await self.client.end_session(sid)
                await asyncio.sleep(3)

            # ── Aggregate metrics ──
            total_convs = len(per_conversation)
            convs_with_signals = sum(1 for c in per_conversation if c["total_signals"] > 0)
            detection_rate = convs_with_signals / total_convs if total_convs > 0 else 0.0
            match_rate = match_count / total_convs if total_convs > 0 else 0.0

            all_confidences = [s.get("confidence", 0) for s in all_signals]
            avg_signals = (
                sum(c["total_signals"] for c in per_conversation) / total_convs
                if total_convs > 0
                else 0
            )

            # Type distribution (from pending signals only — auto-stored don't carry type info)
            type_dist: dict[str, int] = {}
            for s in all_signals:
                st = s.get("signal_type", "unknown")
                type_dist[st] = type_dist.get(st, 0) + 1

            self.metric("detection_rate", round(detection_rate, 4))
            self.metric("expected_type_match_rate", round(match_rate, 4))
            self.metric("avg_signals_per_conversation", round(avg_signals, 2))
            self.metric("total_auto_stored", total_auto_stored)
            self.metric("type_distribution", type_dist)
            self.metric("confidence_distribution", {
                "mean": round(sum(all_confidences) / len(all_confidences), 3) if all_confidences else 0,
                "min": round(min(all_confidences), 3) if all_confidences else 0,
                "max": round(max(all_confidences), 3) if all_confidences else 0,
                "median": round(sorted(all_confidences)[len(all_confidences) // 2], 3) if all_confidences else 0,
            })
            self.metric("per_conversation", per_conversation)

            self.observe(f"Detection rate: {detection_rate:.1%} ({convs_with_signals}/{total_convs})")
            self.observe(f"Type match rate: {match_rate:.1%} ({match_count}/{total_convs})")
            self.observe(f"Avg signals/conversation: {avg_signals:.1f}")
            self.observe(f"Auto-stored (high-confidence): {total_auto_stored}")
            self.observe(f"Type distribution (pending only): {type_dist}")

            if detection_rate < 0.3:
                self.error(f"Detection rate too low: {detection_rate:.1%}")
                passed = False

        except Exception as e:
            self.error(f"Signal quality suite exception: {e}")
            passed = False

        return self._make_report(passed, time.monotonic() - t0)
