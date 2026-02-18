"""
Signal detector — the brain of auto-memory formation.

Analyzes conversation turns using an LLM and extracts signals
(facts, decisions, error fixes, workflows, etc.) that should
be persisted as memories.
"""

import json
import re

import structlog

from .config import get_settings
from .llm import LLMError, get_llm
from .models import DetectedSignal, MemorySource, MemoryType, SignalType

logger = structlog.get_logger()

# Map signal types to memory types
SIGNAL_TO_MEMORY_TYPE: dict[SignalType, MemoryType] = {
    SignalType.ERROR_FIX: MemoryType.EPISODIC,
    SignalType.DECISION: MemoryType.SEMANTIC,
    SignalType.PATTERN: MemoryType.SEMANTIC,
    SignalType.PREFERENCE: MemoryType.SEMANTIC,
    SignalType.FACT: MemoryType.SEMANTIC,
    SignalType.WORKFLOW: MemoryType.PROCEDURAL,
    SignalType.CONTRADICTION: MemoryType.SEMANTIC,
    SignalType.WARNING: MemoryType.SEMANTIC,
}

# Importance by signal type
SIGNAL_IMPORTANCE: dict[SignalType, float] = {
    SignalType.CONTRADICTION: 0.8,
    SignalType.ERROR_FIX: 0.7,
    SignalType.WORKFLOW: 0.7,
    SignalType.DECISION: 0.6,
    SignalType.FACT: 0.6,
    SignalType.PREFERENCE: 0.5,
    SignalType.PATTERN: 0.5,
    SignalType.WARNING: 0.7,
}

SIGNAL_DURABILITY: dict[SignalType, str] = {
    SignalType.FACT: "durable",
    SignalType.DECISION: "durable",
    SignalType.PATTERN: "durable",
    SignalType.WORKFLOW: "durable",
    SignalType.PREFERENCE: "durable",
    SignalType.ERROR_FIX: "ephemeral",
    SignalType.CONTRADICTION: "ephemeral",
    SignalType.WARNING: "durable",
}

PROMPT_TEMPLATE = """Extract signals from the conversation below. Return a JSON array.

Signal types: error_fix, decision, pattern, preference, fact, workflow, contradiction, warning
Durability: ephemeral (temp fixes), durable (decisions/patterns), permanent (IPs/ports/paths)

Each signal: {{"signal_type": str, "content": str, "confidence": 0.0-1.0, "importance": 1-10, "durability": str, "domain": str, "tags": [str]}}

Extract ALL signals you find. Return [] ONLY for casual greetings or trivial small talk.

Example input:
[user]: The Redis connection keeps dropping on CasaOS. I fixed it by setting tcp-keepalive 60 in redis.conf.
[assistant]: Good find. That's a common issue with Docker bridge networking.

Example output:
[{{"signal_type": "error_fix", "content": "Redis connections drop on CasaOS Docker. Fix: set tcp-keepalive 60 in redis.conf. Caused by Docker bridge networking.", "confidence": 0.9, "importance": 7, "durability": "durable", "domain": "redis", "tags": ["docker", "casaos", "networking"]}}]

Example input:
[user]: I prefer using bun over npm for all new projects.
[assistant]: Makes sense — bun is significantly faster for installs and scripts.

Example output:
[{{"signal_type": "preference", "content": "User prefers bun over npm for all new projects due to faster installs and script execution.", "confidence": 0.85, "importance": 4, "durability": "durable", "domain": "tooling", "tags": ["bun", "npm", "preference"]}}]

Conversation:
{turns}

JSON array:"""

RETRY_NUDGE = " Look again carefully for any facts, decisions, preferences, or workflows."


class SignalDetector:
    """Detects auto-saveable signals from conversation turns."""

    def __init__(self):
        self.settings = get_settings()

    async def detect(self, turns: list[dict]) -> list[DetectedSignal]:
        """
        Analyze conversation turns and extract signals.

        Args:
            turns: List of {role, content, timestamp?} dicts

        Returns:
            List of DetectedSignal objects
        """
        if not turns:
            return []

        formatted = self._format_turns(turns)
        prompt = PROMPT_TEMPLATE.format(turns=formatted)

        try:
            llm = await get_llm()
            raw = await llm.generate(prompt, format_json=True, temperature=0.4)
            logger.debug("signal_detection_raw_response", raw=raw[:500])
            signals = self._parse_response(raw)

            # Retry once on empty response for non-trivial conversations
            if not signals:
                total_chars = sum(len(t.get("content", "")) for t in turns)
                if total_chars > 100:
                    logger.info("signal_detection_retry", total_chars=total_chars)
                    retry_prompt = prompt + RETRY_NUDGE
                    raw = await llm.generate(retry_prompt, format_json=True, temperature=0.6)
                    logger.debug("signal_detection_retry_response", raw=raw[:500])
                    signals = self._parse_response(raw)

            logger.info(
                "signals_detected",
                count=len(signals),
                types=[s.signal_type.value for s in signals],
            )
            return signals

        except LLMError as e:
            logger.error("signal_detection_llm_error", error=str(e))
            return []
        except Exception as e:
            logger.error("signal_detection_error", error=str(e))
            return []

    def _format_turns(self, turns: list[dict]) -> str:
        """Format turns for the prompt, truncating long content."""
        max_chars = 2000
        lines = []
        for turn in turns:
            role = turn.get("role", "unknown")
            content = turn.get("content", "")
            if len(content) > max_chars:
                content = content[:max_chars] + "... [truncated]"
            lines.append(f"[{role}]: {content}")
        return "\n\n".join(lines)

    def _parse_response(self, raw: str) -> list[DetectedSignal]:
        """Parse LLM JSON response into DetectedSignal objects."""
        text = raw.strip()

        # Strip markdown code blocks if present
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*\n?", "", text)
            text = re.sub(r"\n?```\s*$", "", text)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("signal_detection_json_parse_error", raw=text[:200])
            return []

        if not isinstance(data, list):
            # LLM may wrap array in various keys
            if isinstance(data, dict):
                # Try common wrapper keys
                for key in ("signals", "results", "items", "data"):
                    if key in data and isinstance(data[key], list):
                        data = data[key]
                        break
                else:
                    # Single signal object? Wrap it.
                    if "signal_type" in data and "content" in data:
                        data = [data]
                    else:
                        logger.warning(
                            "signal_detection_unexpected_format",
                            type=type(data).__name__,
                            keys=list(data.keys()),
                        )
                        return []
            else:
                logger.warning("signal_detection_unexpected_format", type=type(data).__name__)
                return []

        signals = []
        for item in data:
            try:
                signal_type = SignalType(item["signal_type"])
                confidence = float(item.get("confidence", 0.5))
                confidence = max(0.0, min(1.0, confidence))

                # Parse LLM-provided importance (1-10 scale → 0.0-1.0)
                suggested_importance = None
                raw_importance = item.get("importance")
                if raw_importance is not None:
                    try:
                        imp_val = float(raw_importance)
                        # Clamp to 1-10, then map to 0.0-1.0
                        imp_val = max(1.0, min(10.0, imp_val))
                        suggested_importance = imp_val / 10.0
                    except (ValueError, TypeError):
                        pass

                # Parse durability classification
                suggested_durability = None
                raw_durability = item.get("durability")
                if raw_durability and raw_durability in ("ephemeral", "durable", "permanent"):
                    suggested_durability = raw_durability

                signal = DetectedSignal(
                    signal_type=signal_type,
                    content=item["content"],
                    confidence=confidence,
                    source=MemorySource.SYSTEM,
                    suggested_domain=item.get("domain"),
                    suggested_tags=item.get("tags", []),
                    suggested_importance=suggested_importance,
                    suggested_durability=suggested_durability,
                )
                signals.append(signal)

            except (KeyError, ValueError) as e:
                logger.debug("signal_parse_skip", error=str(e), item=item)
                continue

        return signals
