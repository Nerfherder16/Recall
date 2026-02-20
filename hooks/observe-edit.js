#!/usr/bin/env node
/**
 * PostToolUse hook: Send Write/Edit data to Recall for auto-observation.
 *
 * Async, non-blocking — fires and forgets. Recall being offline
 * should never block coding.
 */

const { extname } = require("path");

const RECALL_HOST = process.env.RECALL_HOST || "http://localhost:8200";
const RECALL_API_KEY = process.env.RECALL_API_KEY || "";
const MAX_CONTENT_SIZE = 10000;

// Skip binary, generated, and irrelevant file types
const SKIP_EXTENSIONS = new Set([
  ".lock", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
  ".woff", ".woff2", ".ttf", ".eot", ".map", ".min.js", ".min.css",
  ".pyc", ".pyo", ".whl", ".zip", ".tar", ".gz", ".exe", ".dll",
  ".so", ".dylib", ".pdf", ".mp3", ".mp4", ".wav", ".avi",
]);
const SKIP_DIRS = ["node_modules", ".git", "__pycache__", "dist", "build", ".next", ".venv", "__tests__", ".autopilot"];

// Files matching these patterns get flagged as high-value — observer uses
// a richer prompt and sets higher default importance
const HIGH_VALUE_PATTERNS = [
  /\/\.claude\/hooks\//,        // Claude hook files
  /\/\.claude\/settings/,       // Claude settings
  /\/\.claude\/CLAUDE\.md$/,    // Project instructions
  /docker-compose\.(ya?ml)$/,   // Docker config
  /Dockerfile$/,                // Docker images
  /\.env(\.\w+)?$/,             // Environment files
  /nginx\.conf/,                // Reverse proxy
  /pyproject\.toml$/,           // Python project config
  /package\.json$/,             // Node project config
  /tsconfig.*\.json$/,          // TypeScript config
  /\.github\/workflows\//,     // CI/CD pipelines
  /hooks\/.*\.js$/,             // Any hooks directory
];

function shouldSkipFile(filePath) {
  if (!filePath) return true;
  const lower = filePath.replace(/\\/g, "/").toLowerCase();
  if (SKIP_DIRS.some((d) => lower.includes(`/${d}/`) || lower.includes(`\\${d}\\`))) return true;
  const ext = extname(lower);
  if (SKIP_EXTENSIONS.has(ext)) return true;
  // Check compound extensions like .min.js
  if (lower.endsWith(".min.js") || lower.endsWith(".min.css")) return true;
  // Skip test files by path pattern
  if (/\/(tests?|__tests__|spec|__mocks__)\//.test(lower)) return true;
  if (/\.(test|spec)\.(js|ts|jsx|tsx|py)$/.test(lower)) return true;
  return false;
}

function readStdin() {
  return new Promise((resolve) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
    setTimeout(() => resolve(data), 3000);
  });
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

  const toolInput = parsed.tool_input || {};
  const toolName = parsed.tool_name || "Write";
  const filePath = toolInput.file_path || toolInput.path || "";

  if (!filePath || shouldSkipFile(filePath)) process.exit(0);

  const normalized = filePath.replace(/\\/g, "/");
  const highValue = HIGH_VALUE_PATTERNS.some((p) => p.test(normalized));

  const body = {
    file_path: filePath,
    tool_name: toolName,
    high_value: highValue,
  };

  if (toolName === "Edit" || toolName === "edit") {
    body.old_string = (toolInput.old_string || "").slice(0, 5000);
    body.new_string = (toolInput.new_string || "").slice(0, 5000);
  } else {
    const content = toolInput.content || "";
    if (content.length > MAX_CONTENT_SIZE) {
      process.exit(0);
    }
    body.content = content;
  }

  const headers = { "Content-Type": "application/json" };
  if (RECALL_API_KEY) {
    headers["Authorization"] = `Bearer ${RECALL_API_KEY}`;
  }

  // Fire-and-forget — don't await, exit immediately
  fetch(`${RECALL_HOST}/observe/file-change`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(5000),
  }).catch(() => {}); // Swallow errors silently

  // Give fetch a moment to send the request, then exit
  setTimeout(() => process.exit(0), 100);
}

main().catch(() => process.exit(0));
