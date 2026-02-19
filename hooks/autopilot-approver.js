#!/usr/bin/env node
/**
 * PreToolUse hook: Auto-approve Write, Edit, and Bash tool calls
 * when autopilot mode is active (build or fix).
 *
 * Determines project root by:
 *   - Write/Edit: walking up from tool_input.file_path
 *   - Bash: walking up from cwd, then checking tool_input.command for paths
 *
 * When .autopilot/mode contains "build" or "fix", tools are silently approved.
 * Otherwise, exits cleanly with no output — normal permission flow applies.
 */

const { existsSync, readFileSync } = require("fs");
const { join, dirname } = require("path");

function readStdin() {
  return new Promise((resolve) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
    setTimeout(() => resolve(data), 2000);
  });
}

/**
 * Walk up from dir to find .autopilot/mode.
 * Returns the trimmed mode string or null.
 */
function findAutopilotMode(startDir) {
  if (!startDir) return null;
  let dir = startDir;
  for (let i = 0; i < 15; i++) {
    const modeFile = join(dir, ".autopilot", "mode");
    if (existsSync(modeFile)) {
      try {
        const mode = readFileSync(modeFile, "utf8").trim();
        return mode || null;
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

/**
 * Extract candidate directories to search for .autopilot/mode.
 * Returns an array of directory paths to try.
 */
function getCandidateDirs(parsed) {
  const dirs = [];
  const toolInput = parsed.tool_input || {};

  // For Write/Edit: the file_path is the best signal
  if (toolInput.file_path) {
    dirs.push(dirname(toolInput.file_path));
  }

  // For Bash: extract absolute paths from the command string
  if (toolInput.command) {
    // Match Windows paths (C:/... or C:\...) with optional surrounding quotes
    const winPaths = toolInput.command.match(/[A-Za-z]:[/\\][^\s"';&|)]+/g);
    if (winPaths) {
      for (const p of winPaths) {
        const clean = p.replace(/[/\\]$/, "");
        dirs.push(clean);          // path itself (may be a directory)
        dirs.push(dirname(clean)); // parent (if path is a file)
      }
    }
    // Match Unix absolute paths that look like real dirs (not flags)
    const unixPaths = toolInput.command.match(/(?<=\s|^|"|')\/[a-zA-Z][^\s"';&|)]+/g);
    if (unixPaths) {
      for (const p of unixPaths) {
        dirs.push(p);
        dirs.push(dirname(p));
      }
    }
  }

  // Always try session cwd as fallback
  if (parsed.cwd) {
    dirs.push(parsed.cwd);
  }

  return dirs;
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

  // Try each candidate directory until we find an autopilot mode
  const candidates = getCandidateDirs(parsed);
  let mode = null;
  for (const dir of candidates) {
    mode = findAutopilotMode(dir);
    if (mode) break;
  }

  if (mode === "build" || mode === "fix") {
    process.stdout.write(
      JSON.stringify({
        hookSpecificOutput: {
          hookEventName: "PreToolUse",
          permissionDecision: "allow",
          permissionDecisionReason: `Autopilot mode "${mode}" active`,
        },
      }),
    );
  }

  process.exit(0);
}

main().catch(() => process.exit(0));
