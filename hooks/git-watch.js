#!/usr/bin/env node
/**
 * PostToolUse hook: Detect git commits and send diff data to Recall
 * for memory invalidation checking.
 *
 * Fires when tool_name is "Bash" and stdout contains a commit hash.
 * Runs `git diff HEAD~1 --unified=0` to get the actual changes,
 * then POSTs extracted values to /observe/git-diff.
 *
 * Async, non-blocking — Recall being offline should never block coding.
 */

const { execSync } = require("child_process");

const RECALL_HOST = process.env.RECALL_HOST || "http://localhost:8200";
const RECALL_API_KEY = process.env.RECALL_API_KEY || "";

// Pattern: git commit output like "[branch abc1234] message"
const COMMIT_HASH_PATTERN = /\[[\w/.-]+\s+([a-f0-9]{7,40})\]/;

function readStdin() {
  return new Promise((resolve) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
    setTimeout(() => resolve(data), 3000);
  });
}

function getDiff() {
  try {
    return execSync("git diff HEAD~1 --unified=0", {
      encoding: "utf8",
      timeout: 5000,
      stdio: ["pipe", "pipe", "pipe"],
    });
  } catch {
    return null;
  }
}

function getChangedFiles(diffText) {
  const pattern = /^diff --git a\/(.+?) b\//gm;
  const files = [];
  let match;
  while ((match = pattern.exec(diffText)) !== null) {
    files.push(match[1]);
  }
  return files;
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

  // Only fire on Bash tool
  if (parsed.tool_name !== "Bash") process.exit(0);

  const stdout = parsed.tool_result?.stdout || parsed.tool_result?.content || "";
  if (typeof stdout !== "string") process.exit(0);

  // Check for git commit hash in output
  const commitMatch = stdout.match(COMMIT_HASH_PATTERN);
  if (!commitMatch) process.exit(0);

  const commitHash = commitMatch[1];

  // Get the diff
  const diffText = getDiff();
  if (!diffText) process.exit(0);

  const changedFiles = getChangedFiles(diffText);

  // POST to Recall for invalidation checking
  const headers = { "Content-Type": "application/json" };
  if (RECALL_API_KEY) {
    headers["Authorization"] = `Bearer ${RECALL_API_KEY}`;
  }

  try {
    await fetch(`${RECALL_HOST}/observe/git-diff`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        commit_hash: commitHash,
        changed_files: changedFiles,
        diff_text: diffText.slice(0, 50000),
      }),
      signal: AbortSignal.timeout(5000),
    });
  } catch {
    // Recall offline — silently ignore
  }
}

main().catch(() => process.exit(0));
