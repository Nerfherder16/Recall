#!/usr/bin/env node
/**
 * UserPromptSubmit hook: Query Recall for relevant memories before Claude responds.
 *
 * This is the RETRIEVAL side of organic memory. On every user prompt,
 * it searches Recall for relevant context and injects it so Claude
 * naturally sees past knowledge without needing CLAUDE.md instructions.
 *
 * Output: hookSpecificOutput.additionalContext (discrete injection)
 * Timeout: 5s budget — Recall browse is fast but network can lag.
 * Failure mode: silent — never block the user.
 */

const { writeFileSync, mkdirSync, existsSync, readFileSync } = require("fs");
const { join } = require("path");

const RECALL_HOST = process.env.RECALL_HOST || "http://localhost:8200";
const RECALL_API_KEY = process.env.RECALL_API_KEY || "";
const MIN_PROMPT_LENGTH = 15;
const MAX_RESULTS = 5;
const MIN_SIMILARITY = 0.25;
const CACHE_DIR = join(process.env.HOME || process.env.USERPROFILE || "/tmp", ".cache", "recall");
const INJECTED_FILE = join(CACHE_DIR, "injected.json");

function readStdin() {
  return new Promise((resolve) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
    setTimeout(() => resolve(data), 2000);
  });
}

function shouldSkip(prompt) {
  if (!prompt || prompt.length < MIN_PROMPT_LENGTH) return true;

  const trimmed = prompt.trim().toLowerCase();

  // Skip slash commands
  if (trimmed.startsWith("/")) return true;

  // Skip bare confirmations
  const trivial = [
    "yes", "no", "ok", "okay", "sure", "thanks", "thank you",
    "y", "n", "yep", "nope", "do it", "go ahead", "continue",
    "looks good", "lgtm", "approved", "ship it",
  ];
  if (trivial.includes(trimmed)) return true;

  // Skip greetings
  const greetings = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening"];
  if (greetings.some((g) => trimmed === g || trimmed.startsWith(g + " "))) return true;

  return false;
}

function formatContext(results) {
  if (!results || results.length === 0) return "";

  const lines = results.map((r) => {
    const type = r.memory_type || "memory";
    const summary = r.summary || r.content || "";
    // Anti-pattern warnings get special formatting
    if (summary.startsWith("WARNING:")) {
      return `- [WARNING] ${summary}`;
    }
    return `- [${type}] ${summary}`;
  });

  return `Relevant context from Recall (previous sessions):\n${lines.join("\n")}`;
}

async function main() {
  const input = await readStdin();
  if (!input) process.exit(0);

  let parsed;
  try {
    parsed = JSON.parse(input);
  } catch {
    process.exit(0);
  }

  const prompt = parsed.prompt || "";
  if (shouldSkip(prompt)) process.exit(0);

  // Extract project name from cwd for domain filtering (not query pollution)
  const cwd = parsed.cwd || "";
  const projectName = cwd.split(/[/\\]/).filter(Boolean).pop() || "";

  // Normalize common project names to canonical domains
  const DOMAIN_ALIASES = {
    "recall": "development", "system-recall": "development",
    "familyhub": "development", "sadie": "development",
    "relay": "development",
  };
  const domain = DOMAIN_ALIASES[projectName.toLowerCase()] || "";
  const query = prompt.slice(0, 500);

  // Query Recall browse endpoint
  const headers = { "Content-Type": "application/json" };
  if (RECALL_API_KEY) {
    headers["Authorization"] = `Bearer ${RECALL_API_KEY}`;
  }

  const searchBody = { query, limit: MAX_RESULTS };
  if (domain) searchBody.domain = domain;

  try {
    const resp = await fetch(`${RECALL_HOST}/search/browse`, {
      method: "POST",
      headers,
      body: JSON.stringify(searchBody),
      signal: AbortSignal.timeout(3500),
    });

    if (!resp.ok) process.exit(0);

    const data = await resp.json();
    const results = (data.results || []).filter(
      (r) => r.similarity >= MIN_SIMILARITY
    );

    if (results.length === 0) process.exit(0);

    // Track injected memory IDs for feedback loop
    try {
      if (!existsSync(CACHE_DIR)) mkdirSync(CACHE_DIR, { recursive: true });
      let injected = [];
      try { injected = JSON.parse(readFileSync(INJECTED_FILE, "utf8")); } catch {}

      const entries = results.map((r) => ({
        memory_id: r.id,
        timestamp: new Date().toISOString(),
      }));
      injected.push(...entries);
      if (injected.length > 500) injected = injected.slice(-500);
      writeFileSync(INJECTED_FILE, JSON.stringify(injected));
    } catch {} // Never block retrieval

    const context = formatContext(results);
    if (!context) process.exit(0);

    // Inject context discretely via hookSpecificOutput
    const output = JSON.stringify({
      hookSpecificOutput: {
        hookEventName: "UserPromptSubmit",
        additionalContext: context,
      },
    });
    process.stdout.write(output);
  } catch {
    // Recall down or timeout — don't block
  }

  process.exit(0);
}

main().catch(() => process.exit(0));
