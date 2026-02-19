#!/usr/bin/env node
/**
 * UserPromptSubmit hook: Query Recall for relevant memories before Claude responds.
 *
 * v2.8 "Sharpen the Blade":
 * - Query rewriting: extracts key terms instead of raw 500-char dump
 * - Domain mapping: project-aware canonical domains (not everything → "development")
 * - Rehydrate: first prompt of session gets a domain briefing via /search/rehydrate
 *
 * Output: hookSpecificOutput.additionalContext (discrete injection)
 * Timeout: 5s budget total (rehydrate + browse run concurrently on first prompt)
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

// Project directory → canonical domain (matches src/core/domains.py CANONICAL_DOMAINS)
// Unknown projects → empty string (no domain filter — search everything)
const PROJECT_DOMAINS = {
  "recall": "development",
  "system-recall": "development",
  "familyhub": "ai-ml",
  "family-hub": "ai-ml",
  "sadie": "ai-ml",
  "relay": "api",
  "media-server": "infrastructure",
  "jellyfin": "infrastructure",
  "homelab": "infrastructure",
};

// Stop words for query extraction
const STOP_WORDS = new Set([
  "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
  "have", "has", "had", "do", "does", "did", "will", "would", "could",
  "should", "may", "might", "shall", "can", "need", "must",
  "i", "me", "my", "we", "our", "you", "your", "he", "she", "it",
  "they", "them", "this", "that", "these", "those", "what", "which",
  "who", "whom", "how", "where", "when", "why",
  "in", "on", "at", "to", "for", "of", "with", "by", "from", "about",
  "into", "through", "during", "before", "after", "above", "below",
  "and", "but", "or", "nor", "not", "so", "if", "then", "else",
  "please", "help", "want", "like", "just", "also", "very", "really",
  "some", "any", "all", "each", "every", "both", "few", "more", "most",
  "other", "such", "only", "same", "than", "too", "very",
  "let", "lets", "make", "get", "got", "go", "going", "know", "think",
  "see", "look", "come", "take", "give", "tell", "say", "said",
]);

// Filler phrases to strip before tokenizing
const FILLER_PATTERNS = [
  /^(can you|could you|please|help me|i need to|i want to|let's|lets|i'd like to|would you)\s+/i,
  /^(hey|hi|hello|okay|ok|so|well|um|uh)\s*,?\s*/i,
];

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

/**
 * Extract key terms from a prompt for better vector search.
 *
 * Strategy:
 * 1. Strip filler phrases ("can you", "please help me", etc.)
 * 2. Pull out quoted strings (usually specific identifiers)
 * 3. Pull out code identifiers (snake_case, camelCase, dot.paths)
 * 4. Keep remaining non-stop-word terms
 * 5. Cap at 200 chars
 */
function extractKeyTerms(prompt) {
  let text = prompt;

  // Strip filler phrases
  for (const pattern of FILLER_PATTERNS) {
    text = text.replace(pattern, "");
  }

  const terms = [];

  // Extract quoted strings (high signal — user is being specific)
  const quoted = text.match(/["'`]([^"'`]{2,60})["'`]/g);
  if (quoted) {
    for (const q of quoted) {
      terms.push(q.slice(1, -1).trim());
    }
  }

  // Extract code identifiers: snake_case, camelCase, dot.notation
  const codeIdents = text.match(/\b[a-zA-Z_]\w*(?:\.\w+)+\b|\b[a-z]+(?:_[a-z0-9]+)+\b|\b[a-z]+(?:[A-Z][a-z0-9]*)+\b/g);
  if (codeIdents) {
    for (const ident of codeIdents) {
      if (!terms.includes(ident)) terms.push(ident);
    }
  }

  // Tokenize remaining text, filter stop words
  const words = text
    .replace(/[^\w\s.-]/g, " ")
    .split(/\s+/)
    .filter((w) => w.length > 2 && !STOP_WORDS.has(w.toLowerCase()))
    .map((w) => w.toLowerCase());

  // Add unique non-stop-words
  for (const w of words) {
    if (!terms.some((t) => t.toLowerCase() === w)) {
      terms.push(w);
    }
  }

  const result = terms.join(" ").slice(0, 200).trim();

  // If extraction is too short, fall back to truncated prompt
  if (result.split(/\s+/).length < 3) {
    return prompt.slice(0, 300).trim();
  }

  return result;
}

function formatContext(results) {
  if (!results || results.length === 0) return "";

  const lines = results.map((r) => {
    const type = r.memory_type || "memory";
    const summary = r.summary || r.content || "";
    if (summary.startsWith("WARNING:")) {
      return `- [WARNING] ${summary}`;
    }
    return `- [${type}] ${summary}`;
  });

  return `Relevant context from Recall (previous sessions):\n${lines.join("\n")}`;
}

function formatRehydrate(entries, domain) {
  if (!entries || entries.length === 0) return "";

  const lines = entries.map((e) => {
    const type = e.memory_type || "memory";
    const text = e.summary || e.content || "";
    const prefix = e.is_anti_pattern ? "WARNING" : type;
    return `- [${prefix}] ${text.slice(0, 150)}`;
  });

  const label = domain || "this project";
  return `Domain briefing (recent context for ${label}):\n${lines.join("\n")}`;
}

function getInjectedFile(sessionId) {
  const sessionKey = sessionId || `ppid-${process.ppid}`;
  return join(CACHE_DIR, `injected-${sessionKey}.json`);
}

function isFirstPrompt(injectedFile) {
  try {
    if (!existsSync(injectedFile)) return true;
    const data = JSON.parse(readFileSync(injectedFile, "utf8"));
    return !data || data.length === 0;
  } catch {
    return true;
  }
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

  // Project → canonical domain
  const cwd = parsed.cwd || "";
  const projectName = cwd.split(/[/\\]/).filter(Boolean).pop() || "";
  const domain = PROJECT_DOMAINS[projectName.toLowerCase()] || "";

  // Extract key terms instead of raw prompt dump
  const query = extractKeyTerms(prompt);

  const headers = { "Content-Type": "application/json" };
  if (RECALL_API_KEY) {
    headers["Authorization"] = `Bearer ${RECALL_API_KEY}`;
  }

  const injectedFile = getInjectedFile(parsed.session_id);
  const firstPrompt = isFirstPrompt(injectedFile);

  try {
    // Build concurrent requests
    const searchBody = { query, limit: MAX_RESULTS };
    if (domain) searchBody.domain = domain;

    const browsePromise = fetch(`${RECALL_HOST}/search/browse`, {
      method: "POST",
      headers,
      body: JSON.stringify(searchBody),
      signal: AbortSignal.timeout(3500),
    });

    // First prompt: also fetch domain briefing via rehydrate
    let rehydratePromise = null;
    if (firstPrompt && domain) {
      rehydratePromise = fetch(`${RECALL_HOST}/search/rehydrate`, {
        method: "POST",
        headers,
        body: JSON.stringify({ domain, limit: 10 }),
        signal: AbortSignal.timeout(3500),
      }).catch(() => null);
    }

    // Run concurrently
    const [browseResp, rehydrateResp] = await Promise.all([
      browsePromise,
      rehydratePromise || Promise.resolve(null),
    ]);

    if (!browseResp.ok) process.exit(0);

    const data = await browseResp.json();
    const results = (data.results || []).filter(
      (r) => r.similarity >= MIN_SIMILARITY
    );

    // Parse rehydrate response
    let rehydrateEntries = [];
    if (rehydrateResp && rehydrateResp.ok) {
      try {
        const rData = await rehydrateResp.json();
        rehydrateEntries = rData.entries || [];
      } catch {}
    }

    if (results.length === 0 && rehydrateEntries.length === 0) process.exit(0);

    // Track injected memory IDs for feedback loop
    try {
      if (!existsSync(CACHE_DIR)) mkdirSync(CACHE_DIR, { recursive: true });
      let injected = [];
      try { injected = JSON.parse(readFileSync(injectedFile, "utf8")); } catch {}

      const entries = results.map((r) => ({
        memory_id: r.id,
        timestamp: new Date().toISOString(),
      }));
      // Also track rehydrate entries
      for (const e of rehydrateEntries) {
        if (e.id) entries.push({ memory_id: e.id, timestamp: new Date().toISOString() });
      }
      injected.push(...entries);
      if (injected.length > 500) injected = injected.slice(-500);
      writeFileSync(injectedFile, JSON.stringify(injected));
    } catch {} // Never block retrieval

    // Build context: rehydrate briefing first, then search results
    const parts = [];
    const rehydrateContext = formatRehydrate(rehydrateEntries, domain);
    if (rehydrateContext) parts.push(rehydrateContext);
    const searchContext = formatContext(results);
    if (searchContext) parts.push(searchContext);

    const context = parts.join("\n\n");
    if (!context) process.exit(0);

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
