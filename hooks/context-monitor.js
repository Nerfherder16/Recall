#!/usr/bin/env node
/**
 * PostToolUse hook: Estimate context window usage.
 *
 * Checks transcript file size and warns when approaching limits.
 * Async, non-blocking — informational only.
 */

const { statSync } = require("fs");

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

  const transcriptPath = parsed.transcript_path;
  if (!transcriptPath) process.exit(0);

  try {
    const stats = statSync(transcriptPath);
    const estimatedTokens = Math.round(stats.size / 4);

    if (estimatedTokens > 150000) {
      const warning = JSON.stringify({
        additionalContext: `WARNING: Context window ~${Math.round(estimatedTokens / 1000)}K tokens estimated. Consider committing work and starting a fresh session to avoid degraded output quality.`,
      });
      process.stdout.write(warning);
    }
  } catch {
    // File not found or inaccessible — ignore
  }

  process.exit(0);
}

main().catch(() => process.exit(0));
