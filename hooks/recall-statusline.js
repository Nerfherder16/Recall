#!/usr/bin/env node
/**
 * Statusline script: displays context usage + triggers Ollama-based
 * session summary when context reaches 65% (before auto-compact at ~72-80%).
 *
 * Receives JSON on stdin with context_window.used_percentage, session_id,
 * transcript_path, cwd, model, cost, etc.
 *
 * Output: plain text with ANSI colors to stdout.
 * Side-effect at 65%: spawns background process to summarize via Ollama
 * and store to Recall.
 */

const { existsSync, writeFileSync, readFileSync, mkdirSync } = require("fs");
const { join, dirname } = require("path");
const { spawn } = require("child_process");

const RECALL_HOST = process.env.RECALL_HOST || "http://192.168.50.19:8200";
const RECALL_API_KEY = process.env.RECALL_API_KEY || "recall-admin-key-change-me";
const OLLAMA_HOST = process.env.OLLAMA_HOST || "http://192.168.50.62:11434";
const OLLAMA_MODEL = process.env.OLLAMA_MODEL || "qwen3:14b";
const THRESHOLD = 65;
const MAX_TRANSCRIPT_LINES = 300;

// ANSI colors
const GREEN = "\x1b[32m";
const YELLOW = "\x1b[33m";
const RED = "\x1b[31m";
const BOLD = "\x1b[1m";
const DIM = "\x1b[2m";
const RESET = "\x1b[0m";

function readStdin() {
  return new Promise((resolve) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
    setTimeout(() => resolve(data), 2000);
  });
}

function getColor(pct) {
  if (pct >= 80) return RED;
  if (pct >= 50) return YELLOW;
  return GREEN;
}

function progressBar(pct, width = 20) {
  const filled = Math.round((pct / 100) * width);
  const empty = width - filled;
  return "█".repeat(filled) + "░".repeat(empty);
}

/**
 * Walk up from cwd looking for .autopilot/progress.json.
 * Returns a short status string like "[build: 4/8]" or null.
 */
function getAutopilotStatus(cwd) {
  if (!cwd) return null;
  let dir = cwd;
  for (let i = 0; i < 10; i++) {
    const progressFile = join(dir, ".autopilot", "progress.json");
    if (existsSync(progressFile)) {
      try {
        const data = JSON.parse(readFileSync(progressFile, "utf8"));
        const status = (data.status || "").toUpperCase();
        if (status === "COMPLETE" || status === "PAUSED" || status === "FAILED") {
          return `[build: ${status}]`;
        }
        if (Array.isArray(data.tasks)) {
          const done = data.tasks.filter((t) => t.status === "DONE").length;
          const total = data.tasks.length;
          return `[build: ${done}/${total}]`;
        }
        return null;
      } catch {
        return null;
      }
    }
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

function getMarkerDir() {
  const tmpDir =
    process.env.TEMP || process.env.TMP || "/tmp";
  const markerDir = join(tmpDir, "recall-statusline");
  if (!existsSync(markerDir)) {
    try {
      mkdirSync(markerDir, { recursive: true });
    } catch {
      // ignore
    }
  }
  return markerDir;
}

function hasAlreadyFired(sessionId) {
  const marker = join(getMarkerDir(), `${sessionId}.fired`);
  return existsSync(marker);
}

function markAsFired(sessionId) {
  const marker = join(getMarkerDir(), `${sessionId}.fired`);
  try {
    writeFileSync(marker, new Date().toISOString());
  } catch {
    // ignore
  }
}

function extractTranscriptContext(transcriptPath) {
  try {
    const content = readFileSync(transcriptPath, "utf8");
    const lines = content.trim().split("\n");
    const recentLines = lines.slice(-MAX_TRANSCRIPT_LINES);

    const messages = [];
    for (const line of recentLines) {
      try {
        const entry = JSON.parse(line);
        const role = entry.type === "human" || entry.role === "user"
          ? "user"
          : entry.type === "assistant" || entry.role === "assistant"
            ? "assistant"
            : null;

        if (!role) continue;

        let text = "";
        if (typeof entry.content === "string") {
          text = entry.content;
        } else if (Array.isArray(entry.content)) {
          text = entry.content
            .filter((c) => c.type === "text")
            .map((c) => c.text)
            .join(" ");
        } else if (entry.message && typeof entry.message === "string") {
          text = entry.message;
        }

        if (text && text.length > 5) {
          // Truncate each message to keep total payload reasonable
          messages.push({ role, text: text.slice(0, 500) });
        }
      } catch {
        // Skip malformed
      }
    }
    return messages;
  } catch {
    return [];
  }
}

function buildOllamaPrompt(messages, cwd, cost) {
  const projectName = cwd.split(/[/\\]/).filter(Boolean).pop() || "unknown";

  // Build a condensed transcript excerpt for the LLM
  const transcript = messages
    .slice(-40) // Last 40 messages max
    .map((m) => `[${m.role}]: ${m.text}`)
    .join("\n");

  const costInfo = cost
    ? `Cost so far: $${cost.total_cost_usd?.toFixed(4) || "?"}, ` +
      `${cost.total_lines_added || 0} lines added, ` +
      `${cost.total_lines_removed || 0} lines removed.`
    : "";

  return `You are summarizing a Claude Code session for continuity. The context window is about to compact (90%+ used). Write a detailed handoff summary that a compacted session can use to continue the work seamlessly.

Project: ${projectName}
Working directory: ${cwd}
${costInfo}

Recent conversation (last ~40 exchanges):
${transcript}

Write a structured summary covering:
1. **What was being worked on** (the main task/feature/bug)
2. **What was completed** (files modified, features implemented, bugs fixed)
3. **Current state** (what works, what's broken, what's in progress)
4. **Key decisions made** (architectural choices, tradeoffs)
5. **Next steps** (what still needs to be done)

Be specific — include file paths, function names, and concrete details. This summary replaces the full conversation history.
Do NOT use <think> tags or internal reasoning — output only the summary.`;
}

async function triggerOllamaSummary(data) {
  const { transcript_path, cwd, session_id, cost } = data;

  if (!transcript_path) return;

  const messages = extractTranscriptContext(transcript_path);
  if (messages.length < 3) return; // Not enough to summarize

  const prompt = buildOllamaPrompt(messages, cwd || "unknown", cost);
  const projectName = (cwd || "").split(/[/\\]/).filter(Boolean).pop() || "unknown";

  try {
    // Call Ollama for summarization
    const ollamaResp = await fetch(`${OLLAMA_HOST}/api/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: OLLAMA_MODEL,
        prompt,
        stream: false,
        options: {
          temperature: 0.3,
          num_predict: 2000,
        },
        think: false,
      }),
      signal: AbortSignal.timeout(120000), // 2 min for 14b model
    });

    if (!ollamaResp.ok) return;

    const result = await ollamaResp.json();
    const summary = (result.response || "").trim();
    if (!summary || summary.length < 50) return;

    // Store to Recall
    const headers = { "Content-Type": "application/json" };
    if (RECALL_API_KEY) {
      headers["Authorization"] = `Bearer ${RECALL_API_KEY}`;
    }

    await fetch(`${RECALL_HOST}/memory/store`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        content: `[Context Handoff — ${projectName}] ${summary}`,
        domain: projectName,
        source: "system",
        memory_type: "episodic",
        tags: ["context-handoff", "session-summary", projectName],
        importance: 0.7, // Higher than regular session summaries
      }),
      signal: AbortSignal.timeout(10000),
    });
  } catch {
    // Ollama or Recall down — nothing we can do
  }
}

async function main() {
  const input = await readStdin();
  if (!input) process.exit(0);

  let data;
  try {
    data = JSON.parse(input);
  } catch {
    process.exit(0);
  }

  const pct = Math.floor(
    (data.context_window && data.context_window.used_percentage) || 0
  );
  const model = (data.model && data.model.display_name) || "?";
  const cost = data.cost && data.cost.total_cost_usd
    ? `$${data.cost.total_cost_usd.toFixed(3)}`
    : "";
  const sessionId = data.session_id || "unknown";

  // Build status line
  const color = getColor(pct);
  const bar = progressBar(pct);
  let line = `${color}${bar}${RESET} ${BOLD}${pct}%${RESET} ${DIM}${model}${RESET}`;
  if (cost) {
    line += ` ${DIM}${cost}${RESET}`;
  }

  const autopilotStatus = getAutopilotStatus(data.cwd);
  if (autopilotStatus) {
    line += ` \x1b[36m${autopilotStatus}\x1b[0m`;
  }

  // Check threshold
  const alreadyFired = hasAlreadyFired(sessionId);

  if (pct >= THRESHOLD && !alreadyFired) {
    markAsFired(sessionId);
    line += ` ${RED}${BOLD}⚡ HANDOFF${RESET}`;

    // Spawn background summarization — detached so statusline returns immediately
    const child = spawn(
      process.execPath,
      ["-e", `
        const fn = ${triggerOllamaSummary.toString()};
        fn(${JSON.stringify({
          transcript_path: data.transcript_path,
          cwd: data.cwd,
          session_id: sessionId,
          cost: data.cost,
        })}).then(() => process.exit(0)).catch(() => process.exit(0));
      `],
      {
        detached: true,
        stdio: "ignore",
        env: { ...process.env },
      }
    );
    child.unref();
  } else if (pct >= THRESHOLD && alreadyFired) {
    line += ` ${GREEN}${DIM}✓ handoff sent${RESET}`;
  } else if (pct >= 50) {
    line += ` ${YELLOW}${DIM}(handoff at ${THRESHOLD}%)${RESET}`;
  }

  process.stdout.write(line + "\n");
  process.exit(0);
}

main().catch(() => process.exit(0));
