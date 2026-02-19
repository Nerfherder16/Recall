"""
LLM Corpus Generator — Stage 1 of ML training data diversification.

Generates 500+ labeled developer conversations across a matrix of:
  - 8 programming languages
  - 10 development domains
  - 8 signal types + non-signal categories

Uses Ollama (qwen3:14b) to generate realistic developer<->assistant exchanges.

Usage:
    python -m tests.ml.generate_corpus
    python -m tests.ml.generate_corpus --samples 100  # smaller test run
    python -m tests.ml.generate_corpus --concurrency 3
"""

import argparse
import asyncio
import hashlib
import json
import random
import re
import time
from pathlib import Path

import httpx

OLLAMA_URL = "http://192.168.50.62:11434"
MODEL = "qwen3:14b"
OUTPUT_DIR = Path(__file__).parent / "datasets"

# ─── Matrix dimensions ───────────────────────────────────────────────

LANGUAGES = [
    "Python",
    "JavaScript/TypeScript",
    "Rust",
    "Go",
    "Java",
    "C#",
    "Ruby",
    "Shell/Bash",
]

DOMAINS = [
    "web-api",
    "frontend",
    "infrastructure",
    "database",
    "security",
    "ml-data",
    "mobile",
    "devops-ci",
    "testing",
    "systems",
]

SIGNAL_TYPES = {
    "error_fix": "a bug, error, or crash that was diagnosed and fixed",
    "decision": "an architectural or technology choice that was made with reasoning",
    "pattern": "a recurring issue or pattern that was identified",
    "preference": "a coding style, tool, or workflow preference that was stated",
    "fact": "a concrete technical fact (IP, port, version, config value) that was shared",
    "workflow": "a deployment, CI/CD, or development process step that was established",
    "contradiction": "an old assumption or practice that was discovered to be wrong",
    "warning": "a pitfall, anti-pattern, or dangerous practice that was identified",
}

NON_SIGNAL_CATEGORIES = [
    "greeting or small talk",
    "asking to read or show a file",
    "asking to run tests or a command",
    "asking a simple factual question with a short answer",
    "confirming something or saying thanks",
    "asking for a code formatting change or rename",
]

HARD_NEGATIVE_CATEGORIES = [
    "asking to explain what a function does (no new knowledge created)",
    "asking to list files in a directory",
    "asking to search for a string in the codebase",
    "asking what version of a tool is installed",
    "asking to refactor without any decision or pattern involved",
    "routine git operations (commit, push, pull) with no issues",
    "reading documentation without discovering anything new",
    "running a build that succeeds without any notable events",
]


# ─── Prompt templates ────────────────────────────────────────────────

SIGNAL_PROMPT = """\
Generate a realistic conversation between a developer \
and an AI coding assistant.

Context:
- Programming language: {language}
- Development domain: {domain}
- The conversation should contain {signal_desc}

Requirements:
- {turn_count} turns total (alternating user/assistant, starting with user)
- Developer talks like a real person — informal, terse, uses jargon
- The assistant is helpful and technical
- The signal should emerge organically, not be forced
- Include realistic details (file names, error messages, config values)

Return as JSON object:
{{"turns": [{{"role": "user", "content": "..."}}, \
{{"role": "assistant", "content": "..."}}]}}"""

NON_SIGNAL_PROMPT = """\
Generate a short, mundane conversation between a developer \
and an AI coding assistant.

Context:
- Programming language: {language}
- This is: {category}

Requirements:
- {turn_count} turns total (alternating user/assistant, starting with user)
- Should NOT contain memorable decisions, bug fixes, or important facts
- Keep it routine and forgettable
- The developer talks like a real person

Return as JSON object:
{{"turns": [{{"role": "user", "content": "..."}}, \
{{"role": "assistant", "content": "..."}}]}}"""

HARD_NEGATIVE_PROMPT = """\
Generate a conversation between a developer and an AI assistant \
that sounds technical but contains NO memorable signal.

Context:
- Programming language: {language}
- Domain: {domain}
- Activity: {category}

Requirements:
- {turn_count} turns total (alternating user/assistant, starting with user)
- Should sound technical and use real jargon, but NOT contain:
  - A bug fix or error resolution
  - A decision or architectural choice
  - A new fact worth remembering
- Just routine work — reading code, running things, basic questions

Return as JSON object:
{{"turns": [{{"role": "user", "content": "..."}}, \
{{"role": "assistant", "content": "..."}}]}}"""


# ─── Generation logic ────────────────────────────────────────────────


async def generate_one(
    client: httpx.AsyncClient,
    prompt: str,
    semaphore: asyncio.Semaphore,
) -> list[dict] | None:
    """Call Ollama and parse the response as a turn list."""
    async with semaphore:
        try:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.9, "num_predict": 1500},
                    "think": False,
                    "format": "json",
                },
                timeout=120.0,
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "")
        except Exception as e:
            print(f"  [ERROR] Ollama call failed: {e}")
            return None

        # Parse JSON — handle both array and object-wrapped formats
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                turns = parsed
            elif isinstance(parsed, dict):
                # LLM might wrap in {"turns": [...]} or {"conversation": [...]}
                for key in ("turns", "conversation", "messages", "dialog"):
                    if key in parsed and isinstance(parsed[key], list):
                        turns = parsed[key]
                        break
                else:
                    return None
            else:
                return None
        except json.JSONDecodeError:
            # Try to extract JSON array from text
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                try:
                    turns = json.loads(match.group())
                except json.JSONDecodeError:
                    return None
            else:
                return None

        # Validate structure
        if not isinstance(turns, list) or len(turns) < 2:
            return None
        for turn in turns:
            if not isinstance(turn, dict):
                return None
            if "role" not in turn or "content" not in turn:
                return None
            if turn["role"] not in ("user", "assistant"):
                return None
            if not isinstance(turn["content"], str) or len(turn["content"]) < 5:
                return None

        # Reject too short or too long
        total_chars = sum(len(t["content"]) for t in turns)
        if total_chars < 50 or total_chars > 5000:
            return None

        return turns


def content_hash(turns: list[dict]) -> str:
    """Hash turn content for dedup."""
    text = " ".join(t["content"].lower() for t in turns)
    tokens = set(re.split(r"\W+", text))
    return hashlib.md5("|".join(sorted(tokens)).encode()).hexdigest()


async def generate_signal_samples(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    target: int,
) -> list[dict]:
    """Generate signal (positive) conversations."""
    samples = []
    seen_hashes = set()

    # Build task list: cross product of types x domains, pick random language
    tasks = []
    for signal_type, signal_desc in SIGNAL_TYPES.items():
        for domain in DOMAINS:
            lang = random.choice(LANGUAGES)
            turn_count = random.choice([4, 6, 8])
            tasks.append((signal_type, signal_desc, domain, lang, turn_count))

    # Shuffle and repeat to reach target
    random.shuffle(tasks)
    while len(tasks) < target:
        extra = list(tasks)
        random.shuffle(extra)
        for t in extra:
            # Re-roll language for variety
            tasks.append((t[0], t[1], t[2], random.choice(LANGUAGES), random.choice([4, 6, 8])))
            if len(tasks) >= target:
                break

    tasks = tasks[:target]

    # Generate in batches
    for i in range(0, len(tasks), 10):
        batch = tasks[i : i + 10]
        coros = []
        for signal_type, signal_desc, domain, lang, turn_count in batch:
            prompt = SIGNAL_PROMPT.format(
                language=lang,
                domain=domain,
                signal_desc=signal_desc,
                turn_count=turn_count,
            )
            coros.append(generate_one(client, prompt, semaphore))

        results = await asyncio.gather(*coros)

        for j, turns in enumerate(results):
            if turns is None:
                continue
            h = content_hash(turns)
            if h in seen_hashes:
                continue
            seen_hashes.add(h)

            signal_type = batch[j][0]
            domain = batch[j][2]
            lang = batch[j][3]

            samples.append(
                {
                    "turns": turns,
                    "is_signal": True,
                    "signal_type": signal_type,
                    "language": lang,
                    "domain": domain,
                    "source": "llm_generated",
                }
            )

        done = len(samples)
        print(f"  Signals: {done}/{target} generated (batch {i // 10 + 1})")

    return samples


async def generate_nonsignal_samples(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    target: int,
    hard_negative_ratio: float = 0.3,
) -> list[dict]:
    """Generate non-signal (negative) conversations."""
    samples = []
    seen_hashes = set()

    n_hard = int(target * hard_negative_ratio)
    n_easy = target - n_hard

    # Easy negatives
    easy_tasks = []
    for _ in range(n_easy):
        lang = random.choice(LANGUAGES)
        cat = random.choice(NON_SIGNAL_CATEGORIES)
        turn_count = random.choice([2, 2, 4])  # mostly short
        easy_tasks.append((cat, lang, turn_count, False))

    # Hard negatives
    hard_tasks = []
    for _ in range(n_hard):
        lang = random.choice(LANGUAGES)
        domain = random.choice(DOMAINS)
        cat = random.choice(HARD_NEGATIVE_CATEGORIES)
        turn_count = random.choice([4, 6])
        hard_tasks.append((cat, lang, turn_count, True, domain))

    all_tasks = easy_tasks + [
        (t[0], t[1], t[2], t[3], t[4] if len(t) > 4 else None) for t in hard_tasks
    ]
    random.shuffle(all_tasks)

    for i in range(0, len(all_tasks), 10):
        batch = all_tasks[i : i + 10]
        coros = []
        for task in batch:
            cat, lang, turn_count = task[0], task[1], task[2]
            is_hard = task[3] if len(task) > 3 else False
            domain = task[4] if len(task) > 4 else None

            if is_hard and domain:
                prompt = HARD_NEGATIVE_PROMPT.format(
                    language=lang,
                    domain=domain,
                    category=cat,
                    turn_count=turn_count,
                )
            else:
                prompt = NON_SIGNAL_PROMPT.format(
                    language=lang,
                    category=cat,
                    turn_count=turn_count,
                )
            coros.append(generate_one(client, prompt, semaphore))

        results = await asyncio.gather(*coros)

        for j, turns in enumerate(results):
            if turns is None:
                continue
            h = content_hash(turns)
            if h in seen_hashes:
                continue
            seen_hashes.add(h)

            task = batch[j]
            is_hard = task[3] if len(task) > 3 else False

            samples.append(
                {
                    "turns": turns,
                    "is_signal": False,
                    "signal_type": "none",
                    "language": task[1],
                    "domain": task[4] if len(task) > 4 and task[4] else "general",
                    "source": "llm_generated",
                    "is_hard_negative": is_hard,
                }
            )

        done = len(samples)
        print(f"  Non-signals: {done}/{target} generated (batch {i // 10 + 1})")

    return samples


async def run(args):
    """Main generation pipeline."""
    random.seed(42)
    start = time.time()

    n_signal = int(args.samples * 0.45)
    n_nonsignal = args.samples - n_signal

    print(f"Generating {args.samples} conversations:")
    print(f"  Signals: {n_signal}")
    print(f"  Non-signals: {n_nonsignal} (30% hard negatives)")
    print(f"  Concurrency: {args.concurrency}")
    print(f"  Model: {MODEL} @ {OLLAMA_URL}")
    print()

    semaphore = asyncio.Semaphore(args.concurrency)

    async with httpx.AsyncClient() as client:
        # Verify Ollama is reachable
        try:
            resp = await client.get(f"{OLLAMA_URL}/api/tags", timeout=10.0)
            models = [m["name"] for m in resp.json().get("models", [])]
            if not any(MODEL.split(":")[0] in m for m in models):
                print(f"WARNING: {MODEL} not found in Ollama. Available: {models}")
        except Exception as e:
            print(f"ERROR: Cannot reach Ollama at {OLLAMA_URL}: {e}")
            return

        print("Generating signal conversations...")
        signals = await generate_signal_samples(client, semaphore, n_signal)
        print(f"  => {len(signals)} signal samples\n")

        print("Generating non-signal conversations...")
        nonsignals = await generate_nonsignal_samples(client, semaphore, n_nonsignal)
        print(f"  => {len(nonsignals)} non-signal samples\n")

    # Combine and shuffle
    corpus = signals + nonsignals
    random.shuffle(corpus)

    # Stats
    elapsed = time.time() - start
    n_signals = sum(1 for s in corpus if s["is_signal"])
    n_nonsignals = len(corpus) - n_signals

    type_dist = {}
    lang_dist = {}
    domain_dist = {}
    for s in corpus:
        t = s.get("signal_type", "none")
        type_dist[t] = type_dist.get(t, 0) + 1
        lang = s.get("language", "?")
        lang_dist[lang] = lang_dist.get(lang, 0) + 1
        d = s.get("domain", "?")
        domain_dist[d] = domain_dist.get(d, 0) + 1

    print("=" * 60)
    print("CORPUS GENERATION REPORT")
    print("=" * 60)
    print(f"Total samples:   {len(corpus)}")
    if len(corpus) == 0:
        print("No samples generated — check Ollama connectivity.")
        return
    pct_sig = n_signals / len(corpus) * 100
    pct_nonsig = n_nonsignals / len(corpus) * 100
    per_sample = elapsed / len(corpus)
    print(f"Signals:         {n_signals} ({pct_sig:.0f}%)")
    print(f"Non-signals:     {n_nonsignals} ({pct_nonsig:.0f}%)")
    print(f"Elapsed:         {elapsed:.1f}s ({per_sample:.1f}s/sample)")
    print()
    print("Signal type distribution:")
    for t, c in sorted(type_dist.items(), key=lambda x: -x[1]):
        print(f"  {t:<20} {c:>4}")
    print()
    print("Language distribution:")
    for lang, c in sorted(lang_dist.items(), key=lambda x: -x[1]):
        print(f"  {lang:<25} {c:>4}")
    print()
    print("Domain distribution:")
    for d, c in sorted(domain_dist.items(), key=lambda x: -x[1]):
        print(f"  {d:<20} {c:>4}")

    # Save
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "generated_corpus.json"
    with open(output_path, "w") as f:
        json.dump(corpus, f, indent=2)
    print(f"\nSaved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate diverse training corpus via LLM")
    parser.add_argument("--samples", type=int, default=500, help="Total samples to generate")
    parser.add_argument("--concurrency", type=int, default=2, help="Max concurrent Ollama calls")
    args = parser.parse_args()

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
