#!/usr/bin/env node
/**
 * UserPromptSubmit hook: Query Recall for relevant memories before Claude responds.
 *
 * v2.9 "Always-On Sessions":
 * - Periodic checkpoints: every 25 prompts or 2 hours, stores a session checkpoint
 *   summary and submits feedback — sessions no longer need to end for the feedback
 *   loop to work.
 * - Re-retrieval feedback: if a previously-injected memory appears again in current
 *   results, it's marked useful. Stale entries (>2hr, never re-retrieved) are pruned.
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

// Checkpoint settings
const CHECKPOINT_PROMPT_INTERVAL = 25;
const CHECKPOINT_TIME_INTERVAL_MS = 2 * 60 * 60 * 1000; // 2 hours
const STALE_ENTRY_AGE_MS = 2 * 60 * 60 * 1000; // 2 hours

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

function getSessionStateFile(sessionId) {
  const sessionKey = sessionId || `ppid-${process.ppid}`;
  return join(CACHE_DIR, `session-state-${sessionKey}.json`);
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

/**
 * Load or initialize session state (prompt counter, last checkpoint time, recent prompts).
 */
function loadSessionState(stateFile) {
  try {
    if (existsSync(stateFile)) {
      return JSON.parse(readFileSync(stateFile, "utf8"));
    }
  } catch {}
  return {
    prompt_count: 0,
    last_checkpoint: new Date().toISOString(),
    recent_prompts: [],
  };
}

function saveSessionState(stateFile, state) {
  try {
    if (!existsSync(CACHE_DIR)) mkdirSync(CACHE_DIR, { recursive: true });
    writeFileSync(stateFile, JSON.stringify(state));
  } catch {}
}

/**
 * Check if it's time for a checkpoint (every N prompts or M hours).
 */
function needsCheckpoint(state) {
  if (state.prompt_count > 0 && state.prompt_count % CHECKPOINT_PROMPT_INTERVAL === 0) {
    return true;
  }
  const elapsed = Date.now() - new Date(state.last_checkpoint).getTime();
  if (elapsed >= CHECKPOINT_TIME_INTERVAL_MS && state.prompt_count > 0) {
    return true;
  }
  return false;
}

/**
 * Submit feedback for stale injected entries using re-retrieval heuristic.
 *
 * Logic: memories that appear in current search results AND were previously
 * injected = useful (they keep being relevant). Entries older than 2 hours
 * that were never re-retrieved = pruned without penalty.
 */
async function submitPeriodicFeedback(injectedFile, currentResultIds, headers) {
  let injected;
  try {
    injected = JSON.parse(readFileSync(injectedFile, "utf8"));
  } catch {
    return;
  }
  if (!injected || injected.length === 0) return;

  const now = Date.now();
  const currentIds = new Set(currentResultIds);
  const reRetrievedIds = [];
  const keepEntries = [];

  for (const entry of injected) {
    if (entry.source === "rehydrate") continue; // Skip rehydrate for feedback

    const age = now - new Date(entry.timestamp).getTime();

    if (age > STALE_ENTRY_AGE_MS) {
      // Old entry — check if it was re-retrieved (still relevant)
      if (currentIds.has(entry.memory_id)) {
        reRetrievedIds.push(entry.memory_id);
      }
      // Either way, don't keep stale entries
    } else {
      keepEntries.push(entry);
    }
  }

  // Also keep rehydrate entries that are recent
  for (const entry of injected) {
    if (entry.source === "rehydrate") {
      const age = now - new Date(entry.timestamp).getTime();
      if (age <= STALE_ENTRY_AGE_MS) keepEntries.push(entry);
    }
  }

  // Submit re-retrieved memories as useful (they keep coming back = genuinely relevant)
  if (reRetrievedIds.length > 0) {
    const uniqueIds = [...new Set(reRetrievedIds)];
    try {
      await fetch(`${RECALL_HOST}/memory/feedback`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          injected_ids: uniqueIds,
          // Use the memory IDs themselves as context — the feedback endpoint
          // will boost these since they appear in the "assistant text"
          assistant_text: `Re-retrieved memories still relevant: ${uniqueIds.join(", ")}`,
        }),
        signal: AbortSignal.timeout(3000),
      });
    } catch {}
  }

  // Write back only recent entries (prune stale)
  try {
    writeFileSync(injectedFile, JSON.stringify(keepEntries));
  } catch {}
}

/**
 * Store a checkpoint summary — captures what the user has been working on.
 */
async function storeCheckpointSummary(cwd, recentPrompts, domain, headers) {
  if (recentPrompts.length < 3) return;

  const projectName = cwd.split(/[/\\]/).filter(Boolean).pop() || "unknown";
  const promptSummary = recentPrompts
    .slice(-15) // Last 15 prompts
    .map((p, i) => `${i + 1}. ${p.slice(0, 100)}`)
    .join("\n");

  const content = `Session checkpoint in ${projectName} (${new Date().toISOString().slice(0, 16)}): ` +
    `${recentPrompts.length} prompts. Recent work:\n${promptSummary}`;

  try {
    await fetch(`${RECALL_HOST}/memory/store`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        content: content.slice(0, 2000),
        domain: domain || "general",
        source: "system",
        memory_type: "episodic",
        tags: ["session-checkpoint", projectName],
        importance: 0.4,
      }),
      signal: AbortSignal.timeout(3000),
    });
  } catch {}
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

  // Update session state
  const stateFile = getSessionStateFile(parsed.session_id);
  const state = loadSessionState(stateFile);
  state.prompt_count += 1;
  state.recent_prompts.push(prompt.slice(0, 200));
  if (state.recent_prompts.length > 50) {
    state.recent_prompts = state.recent_prompts.slice(-50);
  }

  try {
    // Build concurrent requests
    const searchBody = { query, limit: MAX_RESULTS };
    if (domain) searchBody.domains = [domain];

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
        body: JSON.stringify({ domain, max_entries: 10 }),
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

    if (results.length === 0 && rehydrateEntries.length === 0) {
      saveSessionState(stateFile, state);
      process.exit(0);
    }

    // Track injected memory IDs for feedback loop
    const currentResultIds = results.map((r) => r.id);
    try {
      if (!existsSync(CACHE_DIR)) mkdirSync(CACHE_DIR, { recursive: true });
      let injected = [];
      try { injected = JSON.parse(readFileSync(injectedFile, "utf8")); } catch {}

      const entries = results.map((r) => ({
        memory_id: r.id,
        source: "search",
        timestamp: new Date().toISOString(),
      }));
      // Track rehydrate entries separately (not submitted for feedback)
      for (const e of rehydrateEntries) {
        if (e.id) entries.push({ memory_id: e.id, source: "rehydrate", timestamp: new Date().toISOString() });
      }
      injected.push(...entries);
      if (injected.length > 500) injected = injected.slice(-500);
      writeFileSync(injectedFile, JSON.stringify(injected));
    } catch {} // Never block retrieval

    // Periodic checkpoint: feedback + summary for long-running sessions
    if (needsCheckpoint(state)) {
      // Fire-and-forget — don't delay the response
      submitPeriodicFeedback(injectedFile, currentResultIds, headers).catch(() => {});
      storeCheckpointSummary(cwd, state.recent_prompts, domain, headers).catch(() => {});
      state.last_checkpoint = new Date().toISOString();
      state.recent_prompts = []; // Reset after checkpoint
    }

    // Save updated state
    saveSessionState(stateFile, state);

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
