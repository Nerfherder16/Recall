#!/usr/bin/env node
/**
 * Stop hook: Block stopping if Autopilot build mode is active with pending tasks.
 *
 * Prevents declaring "done" while an autonomous build is in progress.
 * Exit code 2 blocks the stop.
 *
 * CRITICAL: Checks stop_hook_active to prevent infinite loops.
 */

const { existsSync, readFileSync } = require("fs");
const path = require("path");

function readStdin() {
  return new Promise((resolve) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
    setTimeout(() => resolve(data), 2000);
  });
}

function findAutopilotDir(startDir) {
  let dir = startDir;
  for (let i = 0; i < 10; i++) {
    const autopilotDir = path.join(dir, ".autopilot");
    if (existsSync(autopilotDir)) {
      return autopilotDir;
    }
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return null;
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

  const cwd = parsed.cwd || process.cwd();
  const autopilotDir = findAutopilotDir(cwd);

  if (!autopilotDir) {
    // No autopilot session — allow stop
    process.exit(0);
  }

  // Check mode
  const modeFile = path.join(autopilotDir, "mode");
  if (!existsSync(modeFile)) {
    process.exit(0);
  }

  const mode = readFileSync(modeFile, "utf8").trim();
  if (mode !== "build" && mode !== "fix") {
    // Not in build/fix mode — allow stop
    process.exit(0);
  }

  // Check progress for pending tasks
  const progressFile = path.join(autopilotDir, "progress.json");
  if (!existsSync(progressFile)) {
    // Build mode but no progress file — warn but allow
    process.stderr.write(
      "\nAutopilot: Build mode active but no progress.json found. Allowing stop.\n",
    );
    process.exit(0);
  }

  let progress;
  try {
    progress = JSON.parse(readFileSync(progressFile, "utf8"));
  } catch {
    process.stderr.write(
      "\nAutopilot: Could not parse progress.json. Allowing stop.\n",
    );
    process.exit(0);
  }

  const tasks = progress.tasks || [];
  const pendingTasks = tasks.filter(
    (t) => t.status === "PENDING" || t.status === "IN_PROGRESS",
  );
  const doneTasks = tasks.filter((t) => t.status === "DONE");

  if (pendingTasks.length > 0) {
    const summary = pendingTasks
      .slice(0, 5)
      .map((t) => `  #${t.id}: ${t.description} (${t.status})`)
      .join("\n");

    const more =
      pendingTasks.length > 5
        ? `\n  ... and ${pendingTasks.length - 5} more`
        : "";

    process.stderr.write(
      `\nAutopilot build in progress! ${doneTasks.length}/${tasks.length} tasks complete.\n\nPending tasks:\n${summary}${more}\n\nTo stop anyway: update .autopilot/mode to empty or use stop_hook_active.\nTo pause gracefully: the build should save a handoff state first.\n`,
    );
    process.exit(2);
  }

  // All tasks done — allow stop
  process.exit(0);
}

main().catch(() => process.exit(0));
