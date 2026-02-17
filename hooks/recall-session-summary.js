#!/usr/bin/env node
/**
 * Stop hook: Summarize the session and store to Recall.
 *
 * Reads the transcript JSONL, extracts user messages,
 * builds a compact session summary, and stores it as an
 * episodic memory. This gives the next session continuity.
 *
 * Always exits 0 — never block stopping.
 */

const { readFileSync } = require("fs");

const RECALL_HOST = process.env.RECALL_HOST || "http://localhost:8200";
const RECALL_API_KEY = process.env.RECALL_API_KEY || "";
const MAX_TRANSCRIPT_LINES = 200;

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

    // Read last N lines to avoid memory issues on large transcripts
    const recentLines = lines.slice(-MAX_TRANSCRIPT_LINES);

    const userMessages = [];
    for (const line of recentLines) {
      try {
        const entry = JSON.parse(line);
        // Claude Code JSONL format: look for human/user messages
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

function buildSummary(cwd, userMessages) {
  if (userMessages.length === 0) return null;

  // First message usually states the intent
  const intent = userMessages[0].slice(0, 150);

  // Collect key topics from remaining messages
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

  // Cap at 2000 chars (API limit)
  return summary.slice(0, 2000);
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

  // Extract project name from cwd for domain tagging
  const projectName = cwd.split(/[/\\]/).filter(Boolean).pop() || "unknown";

  // Extract user messages from transcript
  const userMessages = extractUserMessages(transcriptPath);
  if (userMessages.length < 2) {
    // Too short — not worth summarizing
    process.exit(0);
  }

  const summary = buildSummary(cwd, userMessages);
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
        domain: projectName,
        source: "system",
        memory_type: "episodic",
        tags: ["session-summary", projectName],
        importance: 0.4,
      }),
      signal: AbortSignal.timeout(5000),
    });
  } catch {
    // Recall down — don't block stopping
  }

  process.exit(0);
}

main().catch(() => process.exit(0));
