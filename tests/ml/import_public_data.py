"""
Public Dataset Importer — Stage 2 of ML training data diversification.

Downloads ShareGPT52K conversations, filters for coding/technical content,
labels as signal/non-signal using heuristics, and optionally verifies
borderline cases with LLM.

Usage:
    python -m tests.ml.import_public_data
    python -m tests.ml.import_public_data --target 300
    python -m tests.ml.import_public_data --skip-llm   # heuristic only
"""

import argparse
import json
import random
import re
import time
from html import unescape
from pathlib import Path

import httpx

SHAREGPT_URL = "https://huggingface.co/datasets/RyokoAI/ShareGPT52K/resolve/main/sg_90k_part1.json"
OLLAMA_URL = "http://192.168.50.62:11434"
MODEL = "qwen3:14b"
OUTPUT_DIR = Path(__file__).parent / "datasets"

# ─── Filtering keywords ──────────────────────────────────────────────

CODE_INDICATORS = {
    "```",
    "def ",
    "function ",
    "class ",
    "import ",
    "const ",
    "let ",
    "var ",
    "async ",
    "await ",
    "return ",
    "print(",
    "console.log",
    "npm ",
    "pip ",
    "docker ",
    "git ",
    "error",
    "bug",
    "crash",
    "exception",
    "traceback",
    "deploy",
    "server",
    "database",
    "api",
    "endpoint",
    "query",
    "migration",
    "schema",
    "config",
    "env",
    "localhost",
    "port",
    "http://",
    "https://",
    ".py",
    ".js",
    ".ts",
    ".rs",
    ".go",
    ".java",
    ".rb",
    "SELECT ",
    "INSERT ",
    "CREATE TABLE",
    "ALTER ",
    "kubectl",
    "terraform",
    "ansible",
    "nginx",
    "webpack",
    "vite",
    "react",
    "vue",
    "angular",
    "pytest",
    "jest",
    "unittest",
    "cargo test",
}

SIGNAL_KEYWORDS = {
    "error",
    "fix",
    "bug",
    "crash",
    "fail",
    "resolved",
    "decided",
    "let's use",
    "should we",
    "chose",
    "agreed",
    "pattern",
    "noticed",
    "every time",
    "recurring",
    "prefer",
    "always",
    "never",
    "default to",
    "server",
    "port",
    "address",
    "ip",
    "host",
    "version",
    "deploy",
    "pipeline",
    "process",
    "workflow",
    "don't",
    "avoid",
    "dangerous",
    "vulnerability",
    "actually",
    "turns out",
    "was wrong",
    "misconception",
    "warning",
    "careful",
    "gotcha",
    "pitfall",
}

TYPE_KEYWORDS = {
    "error_fix": [
        "error",
        "fix",
        "bug",
        "crash",
        "timeout",
        "exception",
        "traceback",
        "resolved",
        "debugging",
        "stack trace",
    ],
    "decision": [
        "decided",
        "should we",
        "let's use",
        "chose",
        "agreed",
        "go with",
        "recommend",
        "trade-off",
        "vs",
    ],
    "pattern": [
        "pattern",
        "noticed",
        "every time",
        "recurring",
        "keep hitting",
        "common issue",
        "repeatedly",
    ],
    "preference": [
        "prefer",
        "always",
        "never",
        "like to",
        "convention",
        "style",
        "standard",
        "our way",
    ],
    "fact": [
        "server",
        "port",
        "address",
        "ip",
        "host",
        "version",
        "runs on",
        "located at",
        "configured",
        "set to",
    ],
    "workflow": [
        "deploy",
        "pipeline",
        "process",
        "step",
        "command",
        "ci/cd",
        "build",
        "release",
        "migration",
    ],
    "contradiction": [
        "actually",
        "turns out",
        "was wrong",
        "misconception",
        "not true",
        "outdated",
        "no longer",
        "changed",
    ],
    "warning": [
        "don't",
        "avoid",
        "dangerous",
        "vulnerability",
        "careful",
        "gotcha",
        "pitfall",
        "anti-pattern",
    ],
}


# ─── HTML cleanup ─────────────────────────────────────────────────────


def strip_html(text: str) -> str:
    """Remove HTML tags and decode entities from ShareGPT responses."""
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ─── Filtering and labeling ──────────────────────────────────────────


def is_coding_conversation(conv: list[dict]) -> bool:
    """Check if a conversation is about coding/technical topics."""
    text = " ".join(t.get("value", "") for t in conv).lower()
    hits = sum(1 for kw in CODE_INDICATORS if kw.lower() in text)
    return hits >= 3


def compute_signal_score(turns: list[dict]) -> float:
    """Score how likely a conversation contains a signal (0.0-1.0)."""
    text = " ".join(t.get("content", "") for t in turns).lower()
    word_count = len(text.split())

    if word_count < 30:
        return 0.1

    hits = sum(1 for kw in SIGNAL_KEYWORDS if kw in text)
    density = hits / max(word_count / 100, 1)

    # Length bonus — longer technical conversations are more signal-rich
    length_bonus = min(word_count / 500, 0.3)

    # Code block bonus
    code_blocks = text.count("```")
    code_bonus = min(code_blocks * 0.05, 0.2)

    score = min(density * 0.5 + length_bonus + code_bonus, 1.0)
    return round(score, 3)


def classify_signal_type(turns: list[dict]) -> str:
    """Classify the signal type using keyword matching."""
    text = " ".join(t.get("content", "") for t in turns).lower()
    scores: dict[str, int] = {}

    for sig_type, keywords in TYPE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[sig_type] = score

    if not scores:
        return "fact"
    return max(scores, key=scores.get)


def convert_turns(
    raw_turns: list[dict],
) -> list[dict[str, str]]:
    """Convert ShareGPT format to our format."""
    result = []
    for turn in raw_turns:
        role_map = {"human": "user", "gpt": "assistant"}
        role = role_map.get(turn.get("from", ""), None)
        if role is None:
            continue
        content = strip_html(turn.get("value", ""))
        if not content or len(content) < 5:
            continue
        # Truncate very long turns
        if len(content) > 2000:
            content = content[:2000] + "..."
        result.append({"role": role, "content": content})
    return result


# ─── LLM verification ────────────────────────────────────────────────

VERIFY_PROMPT = """\
Analyze this developer conversation and determine:
1. Does it contain a memorable signal worth storing in memory?
   (bug fix, decision, pattern, fact, workflow, warning, etc.)
2. If yes, what type?

Conversation:
{conversation}

Return JSON: {{"is_signal": true/false, "signal_type": "..."}}
Types: error_fix, decision, pattern, preference, fact, \
workflow, contradiction, warning
If not a signal, use "none" for signal_type."""


async def verify_with_llm(
    client: httpx.AsyncClient,
    turns: list[dict],
) -> dict | None:
    """Use LLM to verify/correct signal classification."""
    conv_text = "\n".join(f"[{t['role']}] {t['content'][:200]}" for t in turns)
    prompt = VERIFY_PROMPT.format(conversation=conv_text)

    try:
        resp = await client.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "think": False,
                "format": "json",
                "options": {"temperature": 0.1, "num_predict": 100},
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "")
        return json.loads(raw)
    except Exception:
        return None


# ─── Main pipeline ────────────────────────────────────────────────────


async def run(args):
    """Download, filter, label, and save public dataset."""
    import asyncio

    random.seed(42)
    start = time.time()

    # Step 1: Download
    print("Downloading ShareGPT52K from HuggingFace...")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(SHAREGPT_URL, timeout=120.0)
            resp.raise_for_status()
            raw_data = resp.json()
        except Exception as e:
            print(f"ERROR: Download failed: {e}")
            # Try downloading with follow_redirects
            try:
                resp = await client.get(
                    SHAREGPT_URL,
                    timeout=120.0,
                    follow_redirects=True,
                )
                resp.raise_for_status()
                raw_data = resp.json()
            except Exception as e2:
                print(f"ERROR: Retry also failed: {e2}")
                return

    print(f"  Downloaded {len(raw_data)} conversations")

    # Step 2: Filter for coding conversations
    print("Filtering for coding/technical conversations...")
    coding_convs = []
    for item in raw_data:
        convs = item.get("conversations", [])
        if len(convs) < 2:
            continue
        if not is_coding_conversation(convs):
            continue
        turns = convert_turns(convs)
        if len(turns) < 2:
            continue
        # Skip very long conversations (> 10 turns)
        if len(turns) > 10:
            turns = turns[:10]
        coding_convs.append(turns)

    print(f"  {len(coding_convs)} coding conversations found")

    # Step 3: Score and label
    print("Labeling conversations...")
    scored = []
    for turns in coding_convs:
        score = compute_signal_score(turns)
        scored.append((turns, score))

    scored.sort(key=lambda x: -x[1])

    # Step 4: Select balanced samples
    # Take top signals + bottom non-signals + borderline
    target_signals = int(args.target * 0.45)
    target_nonsignals = args.target - target_signals

    # High-confidence signals (score > 0.5)
    high_signals = [(t, s) for t, s in scored if s > 0.5]
    # High-confidence non-signals (score < 0.2)
    high_nonsignals = [(t, s) for t, s in scored if s < 0.2]
    # Borderline (0.2 - 0.5)
    borderline = [(t, s) for t, s in scored if 0.2 <= s <= 0.5]

    print(
        f"  High signals: {len(high_signals)}, "
        f"High non-signals: {len(high_nonsignals)}, "
        f"Borderline: {len(borderline)}"
    )

    # Sample from each bucket
    random.shuffle(high_signals)
    random.shuffle(high_nonsignals)
    random.shuffle(borderline)

    selected_signals = high_signals[:target_signals]
    selected_nonsignals = high_nonsignals[:target_nonsignals]

    # Fill remaining from borderline
    remaining_sig = target_signals - len(selected_signals)
    remaining_nonsig = target_nonsignals - len(selected_nonsignals)

    if remaining_sig > 0:
        extra = borderline[:remaining_sig]
        selected_signals.extend(extra)
        borderline = borderline[remaining_sig:]
    if remaining_nonsig > 0:
        extra = borderline[:remaining_nonsig]
        selected_nonsignals.extend(extra)

    # Step 5: LLM verification on borderline cases
    llm_verified = 0
    if not args.skip_llm and borderline:
        print("Running LLM verification on borderline cases...")
        verify_targets = (
            selected_signals[-min(20, len(selected_signals)) :]
            + selected_nonsignals[-min(20, len(selected_nonsignals)) :]
        )
        semaphore = asyncio.Semaphore(2)

        async with httpx.AsyncClient() as client:
            for turns, score in verify_targets:
                async with semaphore:
                    result = await verify_with_llm(client, turns)
                    if result and isinstance(result.get("is_signal"), bool):
                        llm_verified += 1

        print(f"  LLM verified {llm_verified} borderline cases")

    # Step 6: Build output
    samples = []
    for turns, score in selected_signals:
        sig_type = classify_signal_type(turns)
        samples.append(
            {
                "turns": turns,
                "is_signal": True,
                "signal_type": sig_type,
                "source": "sharegpt52k",
                "signal_score": score,
            }
        )

    for turns, score in selected_nonsignals:
        samples.append(
            {
                "turns": turns,
                "is_signal": False,
                "signal_type": "none",
                "source": "sharegpt52k",
                "signal_score": score,
            }
        )

    random.shuffle(samples)

    # Stats
    elapsed = time.time() - start
    n_sig = sum(1 for s in samples if s["is_signal"])
    n_nonsig = len(samples) - n_sig

    type_dist: dict[str, int] = {}
    for s in samples:
        t = s.get("signal_type", "none")
        type_dist[t] = type_dist.get(t, 0) + 1

    print()
    print("=" * 60)
    print("PUBLIC DATASET IMPORT REPORT")
    print("=" * 60)
    print("Source:          ShareGPT52K (CC0-1.0)")
    print(f"Downloaded:      {len(raw_data)} total conversations")
    print(f"Coding filtered: {len(coding_convs)}")
    print(f"Selected:        {len(samples)}")
    print(f"Signals:         {n_sig} ({n_sig / len(samples) * 100:.0f}%)")
    print(f"Non-signals:     {n_nonsig}")
    print(f"LLM verified:    {llm_verified}")
    print(f"Elapsed:         {elapsed:.1f}s")
    print()
    print("Signal type distribution:")
    for t, c in sorted(type_dist.items(), key=lambda x: -x[1]):
        print(f"  {t:<20} {c:>4}")

    # Save
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "public_corpus.json"
    with open(output_path, "w") as f:
        json.dump(samples, f, indent=2)
    print(f"\nSaved to: {output_path}")


def main():
    import asyncio

    parser = argparse.ArgumentParser(
        description="Import public dataset for signal classifier training",
    )
    parser.add_argument(
        "--target",
        type=int,
        default=300,
        help="Target number of samples",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Skip LLM verification of borderline cases",
    )
    args = parser.parse_args()

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
