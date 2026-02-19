#!/usr/bin/env node
/**
 * Stop hook: Summarize the session and store to Recall.
 *
 * v2.8 "Sharpen the Blade":
 * - LLM-powered summaries via Ollama (qwen3:14b) for sessions with 3+ messages
 * - Proper domain mapping (not raw dir name)
 * - Falls back to string concat if Ollama is unavailable
 *
 * Always exits 0 — never block stopping.
 */

const { readFileSync, writeFileSync, existsSync, unlinkSync } = require("fs");
const { join } = require("path");

const RECALL_HOST = process.env.RECALL_HOST || "http://localhost:8200";
const RECALL_API_KEY = process.env.RECALL_API_KEY || "";
const OLLAMA_HOST = process.env.OLLAMA_HOST || "http://192.168.50.62:11434";
const MAX_TRANSCRIPT_LINES = 200;
const CACHE_DIR = join(process.env.HOME || process.env.USERPROFILE || "/tmp", ".cache", "recall");

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

function readStdin() {
  return new Promise((resolve) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
    setTimeout(() => resolve(data), 2000);
  });
}

function extractUserMessages(transcriptPath) {
  try {
    const content = readFileSync(transcriptPath, "utf8");
    const lines = content.trim().split("\n");
    const recentLines = lines.slice(-MAX_TRANSCRIPT_LINES);

    const userMessages = [];
    for (const line of recentLines) {
      try {
        const entry = JSON.parse(line);
        if (entry.type === "human" || entry.role === "user") {
          const text =
            typeof entry.content === "string"
              ? entry.content
              : Array.isArray(entry.content)
                ? entry.content
                    .filter((c) => c.type === "text")
                    .map((c) => c.text)
                    .join(" ")
                : "";
          if (text && text.length > 5 && !text.startsWith("/")) {
            userMessages.push(text.slice(0, 200));
          }
        }
      } catch {
        // Skip malformed lines
      }
    }
    return userMessages;
  } catch {
    return [];
  }
}

/**
 * Build a session summary using string concatenation (fallback).
 */
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

/**
 * Generate a summary using Ollama LLM.
 * Returns null on any failure (timeout, network, bad response).
 */
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
        options: { temperature: 0.3, num_predict: 300, think: false },
      }),
      signal: AbortSignal.timeout(8000),
    });

    if (!resp.ok) return null;

    const data = await resp.json();
    const text = (data.response || "").trim();

    // Sanity check: must be reasonable length
    if (text.length < 20 || text.length > 2000) return null;

    return text;
  } catch {
    return null;
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
  if (!injectedFile) return;

  let injected;
  try {
    injected = JSON.parse(readFileSync(injectedFile, "utf8"));
  } catch {
    return;
  }
  if (!injected || injected.length === 0) return;

  const ids = [...new Set(injected.map((e) => e.memory_id))];
  const assistantText = extractAssistantText(transcriptPath);
  if (!assistantText || assistantText.length < 50) return;

  const headers = { "Content-Type": "application/json" };
  if (RECALL_API_KEY) {
    headers["Authorization"] = `Bearer ${RECALL_API_KEY}`;
  }

  try {
    await fetch(`${RECALL_HOST}/memory/feedback`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        injected_ids: ids,
        assistant_text: assistantText.slice(0, 10000),
      }),
      signal: AbortSignal.timeout(8000),
    });
  } catch {
    // Never block stopping
  }

  try {
    unlinkSync(injectedFile);
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

  const transcriptPath = parsed.transcript_path;
  const cwd = parsed.cwd || "unknown";

  if (!transcriptPath) process.exit(0);

  const projectName = cwd.split(/[/\\]/).filter(Boolean).pop() || "unknown";
  const domain = PROJECT_DOMAINS[projectName.toLowerCase()] || projectName;

  const userMessages = extractUserMessages(transcriptPath);
  if (userMessages.length < 2) {
    process.exit(0);
  }

  // Submit feedback for injected memories before storing summary
  await submitFeedback(transcriptPath, parsed.session_id || "");

  // Build summary: try LLM for substantial sessions, fall back to string concat
  let summary = null;
  let importance = 0.4;
  const totalChars = userMessages.reduce((sum, m) => sum + m.length, 0);

  if (userMessages.length >= 3 && totalChars > 200) {
    summary = await buildLLMSummary(cwd, userMessages);
    if (summary) importance = 0.5; // LLM summaries are higher quality
  }

  if (!summary) {
    summary = buildFallbackSummary(cwd, userMessages);
  }

  if (!summary) process.exit(0);

  // Store to Recall
  const headers = { "Content-Type": "application/json" };
  if (RECALL_API_KEY) {
    headers["Authorization"] = `Bearer ${RECALL_API_KEY}`;
  }

  try {
    await fetch(`${RECALL_HOST}/memory/store`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        content: summary,
        domain,
        source: "system",
        memory_type: "episodic",
        tags: ["session-summary", projectName],
        importance,
      }),
      signal: AbortSignal.timeout(5000),
    });
  } catch {
    // Recall down — don't block stopping
  }

  process.exit(0);
}

main().catch(() => process.exit(0));
