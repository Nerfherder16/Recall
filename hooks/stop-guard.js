#!/usr/bin/env node
/**
 * Stop hook: Block if there are uncommitted git changes.
 *
 * Prevents declaring "done" with uncommitted work.
 * Exit code 2 blocks the stop until changes are committed.
 *
 * CRITICAL: Checks stop_hook_active to prevent infinite loops.
 */

const { execSync } = require("child_process");

function readStdin() {
  return new Promise((resolve) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
    setTimeout(() => resolve(data), 2000);
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

  // Prevent infinite loops — if this is a retry after a previous block, allow it
  if (parsed.stop_hook_active) {
    process.exit(0);
  }

  // Check for uncommitted changes
  try {
    const status = execSync("git status --porcelain", {
      encoding: "utf8",
      timeout: 10000,
      cwd: parsed.cwd || process.cwd(),
    }).trim();

    if (status) {
      const lineCount = status.split("\n").length;
      process.stderr.write(
        `\nUncommitted changes detected (${lineCount} files):\n${status}\n\nPlease commit or stash changes before stopping.\n`
      );
      process.exit(2);
    }
  } catch (e) {
    // Not a git repo or git not available — allow stop
  }

  process.exit(0);
}

main().catch(() => process.exit(0));
