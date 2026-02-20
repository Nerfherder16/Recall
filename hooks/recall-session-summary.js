#!/usr/bin/env node
/**
 * Stop hook: Summarize the session and store to Recall.
 *
 * v2.9.4 "Actually Submit Feedback":
 * - Hardcoded correct RECALL_HOST/API_KEY defaults (localhost doesn't work)
 * - Fire-and-forget: detach from parent process so Claude Code's 10s timeout
 *   doesn't kill us mid-flight
 * - Run feedback + summary in parallel
 * - Debug logging to ~/.cache/recall/session-summary-debug.log
 *
 * Always exits 0 — never block stopping.
 */

const { readFileSync, appendFileSync, existsSync, unlinkSync, mkdirSync } = require("fs");
const { join } = require("path");

const RECALL_HOST = process.env.RECALL_HOST || "http://192.168.50.19:8200";
const RECALL_API_KEY = process.env.RECALL_API_KEY || "recall-admin-key-change-me";
const OLLAMA_HOST = process.env.OLLAMA_HOST || "http://192.168.50.62:11434";
const MAX_TRANSCRIPT_LINES = 200;
const CACHE_DIR = join(process.env.HOME || process.env.USERPROFILE || "/tmp", ".cache", "recall");
const DEBUG_LOG = join(CACHE_DIR, "session-summary-debug.log");

// Same mapping as recall-retrieve.js — project dir → canonical domain
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

function debug(msg) {
  try {
    mkdirSync(CACHE_DIR, { recursive: true });
    appendFileSync(DEBUG_LOG, `[${new Date().toISOString()}] ${msg}\n`);
  } catch {}
}

function readStdin() {
  return new Promise((resolve) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
    setTimeout(() => resolve(data), 2000);
  });
}

function extractMessages(transcriptPath) {
  try {
    const content = readFileSync(transcriptPath, "utf8");
    const lines = content.trim().split("\n");
    const recentLines = lines.slice(-MAX_TRANSCRIPT_LINES);

    const userMessages = [];
    const allMessages = [];
    for (const line of recentLines) {
      try {
        const entry = JSON.parse(line);
        const isUser = entry.type === "human" || entry.role === "user";
        const isAssistant = entry.type === "assistant" || entry.role === "assistant";
        if (!isUser && !isAssistant) continue;

        const text =
          typeof entry.content === "string"
            ? entry.content
            : Array.isArray(entry.content)
              ? entry.content
                  .filter((c) => c.type === "text")
                  .map((c) => c.text)
                  .join(" ")
              : "";
        if (!text || text.length < 5) continue;

        const role = isUser ? "User" : "Assistant";
        allMessages.push({ role, text: text.slice(0, 500) });

        if (isUser && !text.startsWith("/")) {
          userMessages.push(text.slice(0, 200));
        }
      } catch {
        // Skip malformed lines
      }
    }
    return { userMessages, allMessages };
  } catch {
    return { userMessages: [], allMessages: [] };
  }
}

function buildFallbackSummary(cwd, userMessages) {
  if (userMessages.length === 0) return null;

  const intent = userMessages[0].slice(0, 150);
  const topics = userMessages
    .slice(1)
    .filter((m) => m.length > 20)
    .slice(0, 5)
    .map((m) => m.slice(0, 80));

  let summary = `Claude Code session in ${cwd}: "${intent}"`;
  if (topics.length > 0) {
    summary += `. Follow-up topics: ${topics.map((t) => `"${t}"`).join("; ")}`;
  }
  summary += `. (${userMessages.length} user messages total)`;

  return summary.slice(0, 2000);
}

async function buildLLMSummary(cwd, userMessages) {
  const messagesText = userMessages
    .map((m, i) => `[${i + 1}] ${m}`)
    .join("\n");

  const prompt = `Summarize this Claude Code session in 2-3 sentences. Focus on: what was accomplished, key decisions made, and any unfinished work. Be specific about file names, tools, and technologies. Do not include any preamble or thinking.

Working directory: ${cwd}

User messages:
${messagesText}

Summary:`;

  try {
    const resp = await fetch(`${OLLAMA_HOST}/api/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: "qwen3:14b",
        prompt,
        stream: false,
        think: false,
        options: { temperature: 0.3, num_predict: 300 },
      }),
      signal: AbortSignal.timeout(8000),
    });

    if (!resp.ok) return null;

    const data = await resp.json();
    const text = (data.response || "").trim();
    if (text.length < 20 || text.length > 2000) return null;
    return text;
  } catch {
    return null;
  }
}

async function extractKeyDecisions(cwd, allMessages) {
  if (allMessages.length < 10) return [];

  const transcript = allMessages
    .map((m) => `[${m.role}] ${m.text}`)
    .join("\n");

  const prompt = `Analyze this Claude Code session transcript and extract 2-5 KEY FINDINGS worth remembering permanently. Focus on:

- Troubleshooting discoveries (root cause of a bug, what fixed a crash)
- Configuration changes and WHY they were needed
- Architectural decisions and trade-offs
- Gotchas or patterns that would help in future sessions

Working directory: ${cwd}

Transcript:
${transcript.slice(0, 8000)}

Return a JSON array: [{"finding": "...", "domain": "...", "importance": 1-10, "tags": ["..."]}]

Domain must be one of: general, infrastructure, development, testing, security, api, database, frontend, devops, networking, ai-ml, tooling, configuration, documentation, sessions

Rules:
- Each finding should be a complete, self-contained fact (readable without session context)
- Include the specific file paths, commands, or values involved
- importance 7+ for troubleshooting fixes, 5-6 for config changes, 3-4 for minor tweaks
- Return [] if the session was trivial (just reading files, simple questions)`;

  try {
    const resp = await fetch(`${OLLAMA_HOST}/api/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: "qwen3:14b",
        prompt,
        stream: false,
        think: false,
        options: { temperature: 0.2, num_predict: 1000 },
      }),
      signal: AbortSignal.timeout(15000),
    });

    if (!resp.ok) return [];

    const data = await resp.json();
    const text = (data.response || "").trim();

    const jsonMatch = text.match(/\[[\s\S]*\]/);
    if (!jsonMatch) return [];

    const findings = JSON.parse(jsonMatch[0]);
    if (!Array.isArray(findings)) return [];

    return findings.filter(
      (f) => f.finding && f.finding.length >= 20 && f.finding.length <= 1000
    );
  } catch {
    return [];
  }
}

function extractAssistantText(transcriptPath) {
  try {
    const content = readFileSync(transcriptPath, "utf8");
    const lines = content.trim().split("\n").slice(-MAX_TRANSCRIPT_LINES);
    const texts = [];
    for (const line of lines) {
      try {
        const entry = JSON.parse(line);
        if (entry.type === "assistant" || entry.role === "assistant") {
          const text =
            typeof entry.content === "string"
              ? entry.content
              : Array.isArray(entry.content)
                ? entry.content
                    .filter((c) => c.type === "text")
                    .map((c) => c.text)
                    .join(" ")
                : "";
          if (text.length > 10) texts.push(text);
        }
      } catch {
        // Skip malformed lines
      }
    }
    return texts.join(" ").toLowerCase();
  } catch {
    return "";
  }
}

async function submitFeedback(transcriptPath, sessionId) {
  const sessionFile = sessionId
    ? join(CACHE_DIR, `injected-${sessionId}.json`)
    : null;
  const legacyFile = join(CACHE_DIR, "injected.json");
  const injectedFile = (sessionFile && existsSync(sessionFile))
    ? sessionFile
    : existsSync(legacyFile) ? legacyFile : null;

  if (!injectedFile) {
    debug("feedback: no injected file found");
    return;
  }

  let injected;
  try {
    injected = JSON.parse(readFileSync(injectedFile, "utf8"));
  } catch {
    debug("feedback: failed to parse injected file");
    return;
  }
  if (!injected || injected.length === 0) {
    debug("feedback: injected file empty");
    return;
  }

  const searchEntries = injected.filter((e) => e.source !== "rehydrate");
  const ids = [...new Set(searchEntries.map((e) => e.memory_id))];
  debug(`feedback: ${ids.length} unique memory IDs from ${searchEntries.length} entries`);

  const assistantText = extractAssistantText(transcriptPath);
  if (!assistantText || assistantText.length < 50) {
    debug(`feedback: assistant text too short (${assistantText.length} chars)`);
    return;
  }

  const headers = { "Content-Type": "application/json" };
  if (RECALL_API_KEY) {
    headers["Authorization"] = `Bearer ${RECALL_API_KEY}`;
  }

  try {
    const resp = await fetch(`${RECALL_HOST}/memory/feedback`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        injected_ids: ids,
        assistant_text: assistantText.slice(0, 10000),
      }),
      signal: AbortSignal.timeout(8000),
    });
    debug(`feedback: response ${resp.status}`);
  } catch (err) {
    debug(`feedback: fetch error ${err.message}`);
  }

  try {
    unlinkSync(injectedFile);
    debug("feedback: cleaned up injected file");
  } catch {}
}

async function main() {
  debug("--- hook started ---");
  debug(`RECALL_HOST=${RECALL_HOST}`);
  debug(`env RECALL_HOST=${process.env.RECALL_HOST || "(unset)"}`);

  const input = await readStdin();
  if (!input) {
    debug("no stdin, exiting");
    process.exit(0);
  }

  let parsed;
  try {
    parsed = JSON.parse(input);
  } catch {
    debug("failed to parse stdin");
    process.exit(0);
  }

  const transcriptPath = parsed.transcript_path;
  const cwd = parsed.cwd || "unknown";
  const sessionId = parsed.session_id || "";

  debug(`cwd=${cwd} session=${sessionId}`);
  debug(`transcript=${transcriptPath}`);

  if (!transcriptPath) {
    debug("no transcript path, exiting");
    process.exit(0);
  }

  const projectName = cwd.split(/[/\\]/).filter(Boolean).pop() || "unknown";
  const domain = PROJECT_DOMAINS[projectName.toLowerCase()] || "general";

  const { userMessages, allMessages } = extractMessages(transcriptPath);
  debug(`messages: ${userMessages.length} user, ${allMessages.length} total`);

  if (userMessages.length < 2) {
    debug("< 2 user messages, exiting");
    process.exit(0);
  }

  const headers = { "Content-Type": "application/json" };
  if (RECALL_API_KEY) {
    headers["Authorization"] = `Bearer ${RECALL_API_KEY}`;
  }

  // Run feedback + summary in PARALLEL (not serial)
  const totalChars = userMessages.reduce((sum, m) => sum + m.length, 0);
  const [feedbackResult, summary] = await Promise.allSettled([
    submitFeedback(transcriptPath, sessionId),
    (userMessages.length >= 3 && totalChars > 200)
      ? buildLLMSummary(cwd, userMessages)
      : Promise.resolve(null),
  ]);

  debug(`feedback: ${feedbackResult.status}`);

  // Use LLM summary or fall back
  let finalSummary = summary.status === "fulfilled" ? summary.value : null;
  let importance = finalSummary ? 0.5 : 0.4;
  if (!finalSummary) {
    finalSummary = buildFallbackSummary(cwd, userMessages);
  }

  // Store episodic summary
  if (finalSummary) {
    try {
      const resp = await fetch(`${RECALL_HOST}/memory/store`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          content: finalSummary,
          domain,
          source: "system",
          memory_type: "episodic",
          tags: ["session-summary", projectName],
          importance,
        }),
        signal: AbortSignal.timeout(5000),
      });
      debug(`summary stored: ${resp.status}`);
    } catch (err) {
      debug(`summary store failed: ${err.message}`);
    }
  }

  // Extract key decisions (fire-and-forget — don't let this block exit)
  extractKeyDecisions(cwd, allMessages).then(async (decisions) => {
    debug(`decisions extracted: ${decisions.length}`);
    for (const d of decisions.slice(0, 5)) {
      try {
        const imp = Math.max(0.1, Math.min(1.0, (d.importance || 5) / 10.0));
        await fetch(`${RECALL_HOST}/memory/store`, {
          method: "POST",
          headers,
          body: JSON.stringify({
            content: d.finding,
            domain: d.domain || domain,
            source: "system",
            memory_type: "semantic",
            tags: ["session-decision", projectName, ...(d.tags || [])],
            importance: imp,
          }),
          signal: AbortSignal.timeout(5000),
        });
      } catch {}
    }
    debug("--- decisions done ---");
  }).catch(() => {});

  debug("--- main done (decisions may still be running) ---");
}

main().catch((err) => {
  debug(`fatal: ${err.message}`);
  process.exit(0);
});
