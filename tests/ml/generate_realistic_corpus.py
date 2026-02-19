"""
Realistic Corpus Generator — bridges the gap between LLM-generated
training data and real Claude Code sessions.

Generates short, terse developer conversations that match production
patterns: 2-4 turns, 30-100 char messages, practical developer tasks.

Usage:
    python -m tests.ml.generate_realistic_corpus
    python -m tests.ml.generate_realistic_corpus --samples 300
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

# ─── Realistic scenario matrix ─────────────────────────────────────

TOOLS = [
    "Redis",
    "PostgreSQL",
    "Docker",
    "Nginx",
    "FastAPI",
    "React",
    "Neo4j",
    "Qdrant",
    "pytest",
    "Git",
    "SSH",
    "systemd",
    "npm",
    "pip",
    "webpack",
    "vite",
    "TypeScript",
    "ESLint",
    "mypy",
    "ruff",
]

SIGNAL_SCENARIOS = {
    "error_fix": [
        "ConnectionRefusedError connecting to {tool} on port {port}",
        "{tool} throwing timeout errors after upgrade",
        "Import error when running {tool} — module not found",
        "Memory leak in {tool} container, OOM after 2 hours",
        "{tool} returning 500 errors on POST requests",
        "SSL certificate expired on {tool} endpoint",
        "Segfault in {tool} when processing large payloads",
        "Race condition in {tool} worker causing duplicate entries",
        "{tool} config file syntax error after migration",
        "Permission denied accessing {tool} socket",
    ],
    "decision": [
        "Should we use {tool} or {tool2} for caching?",
        "Choosing between REST and GraphQL for the new API",
        "Deciding on {tool} vs {tool2} for the message queue",
        "Should we pin dependencies or use ranges?",
        "Monorepo vs separate repos for frontend/backend",
        "Choosing auth strategy: JWT vs session cookies",
        "Should we add {tool} to the stack or keep it simple?",
        "Database migration strategy: big bang or rolling?",
        "Container orchestration: Docker Compose vs K8s",
        "Feature flags vs branch-based deployment",
    ],
    "pattern": [
        "Every time I restart {tool}, the indexes get corrupted",
        "This same {tool} error keeps happening on Mondays",
        "Noticed all our {tool} timeouts happen during backup window",
        "The {tool} connection pool keeps getting exhausted",
        "Same deadlock pattern in {tool} every few days",
        "All slow queries hit the same {tool} table",
        "{tool} OOM is always after the batch job runs",
        "The flaky test always fails when {tool} is loaded",
        "Every deploy breaks {tool} health checks briefly",
        "Same CORS error whenever we add a new frontend route",
    ],
    "preference": [
        "I always use {tool} for this, never {tool2}",
        "Let's stick with snake_case everywhere",
        "I prefer explicit imports over star imports",
        "Always run {tool} before committing",
        "Never use force push on main",
        "I like keeping config in env vars, not files",
        "Always add type hints to public functions",
        "Prefer composition over inheritance",
        "Never store secrets in {tool} config files",
        "I always test with {tool} before deploying",
    ],
    "fact": [
        "{tool} runs on 192.168.50.{octet}:{port}",
        "The {tool} admin password is stored in Vault",
        "{tool} version is {version} in production",
        "Backup cron runs at 3am, {tool} at 4am",
        "The {tool} container needs 2GB RAM minimum",
        "{tool} API key is in the .env file",
        "Production {tool} is on port {port}, staging on {port2}",
        "The {tool} cert expires on March 15th",
        "{tool} data lives in /data/appdata/{tool_lower}/",
        "The {tool} rate limit is 100 req/min",
    ],
    "workflow": [
        "Deploy process: merge to main, {tool} builds, push to staging",
        "To restart {tool}: docker compose restart {tool_lower}",
        "Run {tool} migrations before deploying the API",
        "After changing {tool} config, restart both api and worker",
        "The {tool} release process: tag, build, push, deploy",
        "CI pipeline: lint, test, build {tool}, push image",
        "To add a new {tool} index: update schema, restart",
        "Rollback procedure: revert commit, rebuild, redeploy",
        "Database migration: backup first, run alembic, verify",
        "New developer setup: clone, .env, docker compose up",
    ],
    "contradiction": [
        "Actually {tool} doesn't need that config anymore",
        "Turns out the {tool} timeout was a red herring",
        "Was wrong about {tool} — it does support that",
        "The {tool} docs are outdated, the API changed",
        "Actually we don't need {tool} for this anymore",
        "{tool} 3.x changed the default behavior",
        "That {tool} workaround is no longer needed after the fix",
        "I was wrong — {tool} handles this natively now",
        "The old {tool} docs say X but it's actually Y now",
        "Turns out {tool} was already configured correctly",
    ],
    "warning": [
        "Don't restart {tool} during peak hours",
        "Never run {tool} migrations without a backup",
        "Careful with {tool} — it drops connections silently",
        "Watch out: {tool} has a known memory leak in v{version}",
        "Don't use {tool} with that flag, it corrupts data",
        "The {tool} API is rate limited, batch your requests",
        "Never expose {tool} port to the public internet",
        "Avoid running {tool} and {tool2} on the same box",
        "{tool} will silently truncate if input exceeds 10MB",
        "Don't forget to rotate {tool} credentials quarterly",
    ],
}

NONSIGNAL_TEMPLATES = [
    ("Can you read {file}?", "Here's the contents of {file}..."),
    ("Run the tests", "All 42 tests pass."),
    ("What's in this directory?", "Here are the files: main.py, utils.py..."),
    ("Show me the git log", "Here are the recent commits..."),
    ("Thanks", "You're welcome!"),
    ("Good morning", "Morning! What are we working on today?"),
    ("Just checking in", "I'm here, ready to help."),
    ("ls src/", "api/  core/  storage/  workers/"),
    ("git status", "On branch main, nothing to commit."),
    ("Never mind, figured it out", "Glad you got it sorted!"),
    ("What does this function do?", "It takes a list and returns the sum."),
    ("Format this file", "Done, formatted with ruff."),
    ("How many lines in {file}?", "{file} has 142 lines."),
    ("Can you search for '{query}'?", "Found 3 matches in src/core/..."),
    ("Push this to main", "Pushed 2 commits to origin/main."),
]

HARD_NEGATIVE_TEMPLATES = [
    (
        "Can you explain what {tool} does in this codebase?",
        "{tool} is used for caching. The config is in docker-compose.yml.",
        "Got it, thanks",
        "No problem! Let me know if you need more details.",
    ),
    (
        "Read the {tool} configuration file",
        "Here's the {tool_lower}.conf: port={port}, maxmemory=2gb...",
        "Ok",
        "Want me to change anything?",
    ),
    (
        "What version of {tool} are we running?",
        "Let me check... {tool} {version}.",
        "Cool",
        "Need anything else?",
    ),
    (
        "Search the codebase for {tool} references",
        "Found 12 references across 5 files: src/core/...",
    ),
    (
        "Show me the {tool} logs from today",
        "Here are the last 50 lines... mostly normal operations.",
    ),
    (
        "Run the {tool} health check",
        "Health check passed: status=ok, uptime=4d, connections=12",
    ),
]

FILES = [
    "src/core/retrieval.py",
    "src/api/routes/admin.py",
    "src/workers/signals.py",
    "docker-compose.yml",
    "src/core/models.py",
    "tests/integration/test_search.py",
    "dashboard/src/App.tsx",
    "src/storage/qdrant.py",
    ".env",
    "pyproject.toml",
    "src/core/health.py",
]

QUERIES = ["TODO", "import", "async def", "logger", "redis", "error"]


def _fill_template(text: str) -> str:
    """Fill template placeholders with random values."""
    tools = random.sample(TOOLS, min(2, len(TOOLS)))
    return (
        text.replace("{tool}", tools[0])
        .replace("{tool2}", tools[1] if len(tools) > 1 else "SQLite")
        .replace("{tool_lower}", tools[0].lower().replace(" ", "-"))
        .replace("{port}", str(random.randint(3000, 9999)))
        .replace("{port2}", str(random.randint(3000, 9999)))
        .replace("{octet}", str(random.randint(10, 99)))
        .replace("{version}", f"{random.randint(1, 5)}.{random.randint(0, 15)}")
        .replace("{file}", random.choice(FILES))
        .replace("{query}", random.choice(QUERIES))
    )


# ─── LLM generation for realistic conversations ───────────────────

REALISTIC_SIGNAL_PROMPT = """\
Generate a SHORT, realistic conversation between a developer and an \
AI coding assistant (like Claude Code).

Context: {scenario}
Signal type: {signal_type} — {signal_desc}

Requirements:
- EXACTLY {turn_count} turns (alternating user/assistant, starting with user)
- Developer messages are TERSE: 10-80 characters, informal, uses jargon
- Assistant responses are SHORT: 30-150 characters, practical, direct
- The entire conversation should be under 500 characters total
- Sounds like a real terminal session, not an essay

Return as JSON: {{"turns": [{{"role": "user", "content": "..."}}, \
{{"role": "assistant", "content": "..."}}]}}"""

REALISTIC_NONSIGNAL_PROMPT = """\
Generate a VERY SHORT, mundane conversation between a developer and \
an AI coding assistant.

Activity: {activity}

Requirements:
- EXACTLY {turn_count} turns (alternating user/assistant)
- Developer messages are 5-40 characters
- This is routine — no bugs, decisions, or new information
- Under 200 characters total

Return as JSON: {{"turns": [{{"role": "user", "content": "..."}}, \
{{"role": "assistant", "content": "..."}}]}}"""

SIGNAL_DESCRIPTIONS = {
    "error_fix": "a bug or error that was diagnosed and fixed",
    "decision": "a technology or architecture choice with reasoning",
    "pattern": "a recurring issue or pattern that was identified",
    "preference": "a personal coding style or tool preference stated",
    "fact": "a concrete config value, IP, port, or version shared",
    "workflow": "a deployment or process step that was established",
    "contradiction": "an old assumption found to be wrong",
    "warning": "a pitfall or dangerous practice identified",
}


async def generate_one(
    client: httpx.AsyncClient,
    prompt: str,
    semaphore: asyncio.Semaphore,
) -> list[dict] | None:
    """Call Ollama and parse response as turn list."""
    async with semaphore:
        try:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "think": False,
                    "format": "json",
                    "options": {"temperature": 0.9, "num_predict": 500},
                },
                timeout=60.0,
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "")
        except Exception:
            return None

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                for key in ("turns", "conversation", "messages"):
                    if key in parsed and isinstance(parsed[key], list):
                        turns = parsed[key]
                        break
                else:
                    return None
            elif isinstance(parsed, list):
                turns = parsed
            else:
                return None
        except json.JSONDecodeError:
            return None

        if not isinstance(turns, list) or len(turns) < 2:
            return None
        for turn in turns:
            if not isinstance(turn, dict):
                return None
            if turn.get("role") not in ("user", "assistant"):
                return None
            if not isinstance(turn.get("content"), str):
                return None
            if len(turn["content"]) < 3:
                return None

        # Enforce length limits — truncate verbose responses
        for turn in turns:
            if turn["role"] == "user" and len(turn["content"]) > 150:
                turn["content"] = turn["content"][:150]
            if turn["role"] == "assistant" and len(turn["content"]) > 300:
                turn["content"] = turn["content"][:300]

        total = sum(len(t["content"]) for t in turns)
        if total > 1500:
            return None

        return turns


def content_hash(turns: list[dict]) -> str:
    """Hash for dedup."""
    text = " ".join(t["content"].lower() for t in turns)
    tokens = set(re.split(r"\W+", text))
    return hashlib.md5("|".join(sorted(tokens)).encode()).hexdigest()


# ─── Template-based generation (fast, no LLM) ─────────────────────


def generate_template_signals(n: int) -> list[dict]:
    """Generate signal conversations from templates (no LLM needed)."""
    samples = []
    for _ in range(n):
        sig_type = random.choice(list(SIGNAL_SCENARIOS.keys()))
        scenario_template = random.choice(SIGNAL_SCENARIOS[sig_type])
        scenario = _fill_template(scenario_template)

        # Build a short conversation around the scenario
        if sig_type == "error_fix":
            turns = [
                {"role": "user", "content": scenario},
                {
                    "role": "assistant",
                    "content": _fill_template(
                        "Check the {tool} config — likely a binding or permissions issue."
                    ),
                },
                {"role": "user", "content": "Yeah that was it, fixed now."},
            ]
        elif sig_type == "decision":
            turns = [
                {"role": "user", "content": scenario},
                {
                    "role": "assistant",
                    "content": _fill_template(
                        "I'd go with {tool} — better ecosystem and we already use it elsewhere."
                    ),
                },
                {"role": "user", "content": "Good point, let's do that."},
                {"role": "assistant", "content": "I'll update the config."},
            ]
        elif sig_type == "fact":
            turns = [
                {"role": "user", "content": _fill_template("What's the {tool} connection info?")},
                {"role": "assistant", "content": scenario},
            ]
        elif sig_type == "warning":
            turns = [
                {"role": "user", "content": _fill_template("I'm about to update {tool}")},
                {"role": "assistant", "content": scenario},
                {"role": "user", "content": "Good to know, I'll be careful."},
            ]
        else:
            # pattern, preference, workflow, contradiction
            turns = [
                {"role": "user", "content": scenario},
                {"role": "assistant", "content": "Noted, I'll keep that in mind."},
            ]

        samples.append(
            {
                "turns": turns,
                "is_signal": True,
                "signal_type": sig_type,
                "source": "template_realistic",
            }
        )
    return samples


def generate_template_nonsignals(n: int) -> list[dict]:
    """Generate non-signal conversations from templates."""
    samples = []
    for _ in range(n):
        template = random.choice(NONSIGNAL_TEMPLATES)
        turns = []
        for i, content in enumerate(template):
            role = "user" if i % 2 == 0 else "assistant"
            turns.append({"role": role, "content": _fill_template(content)})
        samples.append(
            {
                "turns": turns,
                "is_signal": False,
                "signal_type": "none",
                "source": "template_realistic",
            }
        )
    return samples


def generate_template_hard_negatives(n: int) -> list[dict]:
    """Generate hard negative conversations from templates."""
    samples = []
    for _ in range(n):
        template = random.choice(HARD_NEGATIVE_TEMPLATES)
        turns = []
        for i, content in enumerate(template):
            role = "user" if i % 2 == 0 else "assistant"
            turns.append({"role": role, "content": _fill_template(content)})
        samples.append(
            {
                "turns": turns,
                "is_signal": False,
                "signal_type": "none",
                "source": "template_realistic",
                "is_hard_negative": True,
            }
        )
    return samples


# ─── LLM-augmented generation ─────────────────────────────────────


async def generate_llm_signals(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    n: int,
    weak_types: list[str] | None = None,
) -> list[dict]:
    """Generate signal conversations via LLM, weighted toward weak types."""
    samples = []
    seen = set()

    # Weight weak types 3x
    type_weights: dict[str, int] = {}
    for t in SIGNAL_SCENARIOS:
        type_weights[t] = 3 if (weak_types and t in weak_types) else 1

    tasks = []
    for _ in range(n):
        # Weighted random type selection
        total_w = sum(type_weights.values())
        r = random.random() * total_w
        cumulative = 0
        sig_type = list(type_weights.keys())[0]
        for t, w in type_weights.items():
            cumulative += w
            if r <= cumulative:
                sig_type = t
                break

        scenario = _fill_template(random.choice(SIGNAL_SCENARIOS[sig_type]))
        turn_count = random.choice([2, 2, 4, 4])
        tasks.append((sig_type, scenario, turn_count))

    for i in range(0, len(tasks), 10):
        batch = tasks[i : i + 10]
        coros = []
        for sig_type, scenario, turn_count in batch:
            prompt = REALISTIC_SIGNAL_PROMPT.format(
                scenario=scenario,
                signal_type=sig_type,
                signal_desc=SIGNAL_DESCRIPTIONS[sig_type],
                turn_count=turn_count,
            )
            coros.append(generate_one(client, prompt, semaphore))

        results = await asyncio.gather(*coros)
        for j, turns in enumerate(results):
            if turns is None:
                continue
            h = content_hash(turns)
            if h in seen:
                continue
            seen.add(h)
            samples.append(
                {
                    "turns": turns,
                    "is_signal": True,
                    "signal_type": batch[j][0],
                    "source": "llm_realistic",
                }
            )

        print(f"  LLM signals: {len(samples)}/{n} (batch {i // 10 + 1})")

    return samples


async def generate_llm_nonsignals(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    n: int,
) -> list[dict]:
    """Generate non-signal conversations via LLM."""
    samples = []
    seen = set()

    activities = [
        "reading a file",
        "checking git status",
        "running tests",
        "listing directory contents",
        "greeting the assistant",
        "asking to format code",
        "checking a version number",
        "saying thanks or goodbye",
        "asking to search for a string",
        "running a build command",
    ]

    tasks = []
    for _ in range(n):
        activity = random.choice(activities)
        turn_count = random.choice([2, 2, 4])
        tasks.append((activity, turn_count))

    for i in range(0, len(tasks), 10):
        batch = tasks[i : i + 10]
        coros = []
        for activity, turn_count in batch:
            prompt = REALISTIC_NONSIGNAL_PROMPT.format(
                activity=activity,
                turn_count=turn_count,
            )
            coros.append(generate_one(client, prompt, semaphore))

        results = await asyncio.gather(*coros)
        for j, turns in enumerate(results):
            if turns is None:
                continue
            h = content_hash(turns)
            if h in seen:
                continue
            seen.add(h)
            samples.append(
                {
                    "turns": turns,
                    "is_signal": False,
                    "signal_type": "none",
                    "source": "llm_realistic",
                }
            )

        print(f"  LLM non-signals: {len(samples)}/{n} (batch {i // 10 + 1})")

    return samples


# ─── Main pipeline ─────────────────────────────────────────────────


async def run(args):
    """Generate realistic corpus with template + LLM hybrid."""
    random.seed(42)
    start = time.time()

    n_signal = int(args.samples * 0.5)
    n_nonsig = args.samples - n_signal

    # Split between template and LLM generation
    n_template_sig = n_signal // 2
    n_llm_sig = n_signal - n_template_sig
    n_template_nonsig = n_nonsig // 3
    n_template_hard = n_nonsig // 3
    n_llm_nonsig = n_nonsig - n_template_nonsig - n_template_hard

    print(f"Generating {args.samples} realistic conversations:")
    print(f"  Template signals:     {n_template_sig}")
    print(f"  LLM signals:          {n_llm_sig} (3x weight on weak types)")
    print(f"  Template non-signals: {n_template_nonsig}")
    print(f"  Template hard negs:   {n_template_hard}")
    print(f"  LLM non-signals:      {n_llm_nonsig}")
    print()

    # Template generation (instant)
    print("Generating template conversations...")
    template_signals = generate_template_signals(n_template_sig)
    template_nonsigs = generate_template_nonsignals(n_template_nonsig)
    template_hards = generate_template_hard_negatives(n_template_hard)
    print(
        f"  Templates: {len(template_signals)} signals, "
        f"{len(template_nonsigs)} non-signals, "
        f"{len(template_hards)} hard negatives"
    )

    # LLM generation
    weak_types = ["error_fix", "pattern", "preference"]
    semaphore = asyncio.Semaphore(args.concurrency)

    async with httpx.AsyncClient() as client:
        # Verify Ollama
        try:
            resp = await client.get(f"{OLLAMA_URL}/api/tags", timeout=10.0)
            resp.raise_for_status()
        except Exception as e:
            print(f"WARNING: Cannot reach Ollama: {e}")
            print("Falling back to template-only generation.")
            n_llm_sig = 0
            n_llm_nonsig = 0

        llm_signals = []
        llm_nonsigs = []

        if n_llm_sig > 0:
            print("\nGenerating LLM signals (weak types 3x weighted)...")
            llm_signals = await generate_llm_signals(client, semaphore, n_llm_sig, weak_types)

        if n_llm_nonsig > 0:
            print("\nGenerating LLM non-signals...")
            llm_nonsigs = await generate_llm_nonsignals(client, semaphore, n_llm_nonsig)

    # Combine
    corpus = template_signals + llm_signals + template_nonsigs + template_hards + llm_nonsigs
    random.shuffle(corpus)

    # Stats
    elapsed = time.time() - start
    n_sig = sum(1 for s in corpus if s["is_signal"])
    n_nsig = len(corpus) - n_sig

    type_dist: dict[str, int] = {}
    source_dist: dict[str, int] = {}
    char_counts = []
    for s in corpus:
        t = s.get("signal_type", "none")
        type_dist[t] = type_dist.get(t, 0) + 1
        src = s.get("source", "?")
        source_dist[src] = source_dist.get(src, 0) + 1
        chars = sum(len(turn["content"]) for turn in s["turns"])
        char_counts.append(chars)

    avg_chars = sum(char_counts) / len(char_counts) if char_counts else 0
    avg_turns = sum(len(s["turns"]) for s in corpus) / len(corpus) if corpus else 0

    print()
    print("=" * 60)
    print("REALISTIC CORPUS GENERATION REPORT")
    print("=" * 60)
    print(f"Total samples:   {len(corpus)}")
    print(f"Signals:         {n_sig} ({n_sig / len(corpus) * 100:.0f}%)")
    print(f"Non-signals:     {n_nsig}")
    print(f"Avg chars/conv:  {avg_chars:.0f}")
    print(f"Avg turns/conv:  {avg_turns:.1f}")
    print(f"Elapsed:         {elapsed:.1f}s")
    print()
    print("Signal type distribution:")
    for t, c in sorted(type_dist.items(), key=lambda x: -x[1]):
        print(f"  {t:<20} {c:>4}")
    print()
    print("Source distribution:")
    for src, c in sorted(source_dist.items(), key=lambda x: -x[1]):
        print(f"  {src:<24} {c:>4}")

    # Save
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "realistic_corpus.json"
    with open(output_path, "w") as f:
        json.dump(corpus, f, indent=2)
    print(f"\nSaved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate realistic Claude Code training corpus",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=400,
        help="Target number of samples (default: 400)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=2,
        help="Max concurrent Ollama calls (default: 2)",
    )
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
