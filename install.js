#!/usr/bin/env node
/**
 * Recall Installer — configures Claude Code with:
 *   1. MCP server (recall) in ~/.claude.json
 *   2. Hooks (retrieve, observe, session-summary, etc.) in ~/.claude/settings.json
 *   3. Statusline (context % + auto-handoff) in ~/.claude/settings.json
 *   4. Env vars (RECALL_HOST, RECALL_API_KEY, OLLAMA_HOST) in settings.env
 *
 * Usage:
 *   node install.js                                      # Interactive
 *   node install.js --host URL --key KEY --ollama URL    # Non-interactive
 *   node install.js --uninstall                          # Remove only Recall config
 *
 * Safe to re-run — uses _tag:"__recall__" to identify and replace only Recall
 * hooks, preserving autopilot, UI, and any other hook systems.
 */

const fs = require("fs");
const path = require("path");
const os = require("os");
const readline = require("readline");

// ── Constants ────────────────────────────────────────────────────────────
const RECALL_TAG = "__recall__";
const RECALL_ENV_KEYS = ["RECALL_HOST", "RECALL_API_KEY", "OLLAMA_HOST"];
const RECALL_HOOK_FILES = [
  "recall-retrieve.js",
  "observe-edit.js",
  "session-save.js",
  "recall-session-summary.js",
];

// ── Paths ────────────────────────────────────────────────────────────────
const HOME = os.homedir();
const CLAUDE_JSON = path.join(HOME, ".claude.json");
const CLAUDE_DIR = path.join(HOME, ".claude");
const SETTINGS_JSON = path.join(CLAUDE_DIR, "settings.json");
const REPO_DIR = __dirname;
const HOOKS_DIR = path.join(REPO_DIR, "hooks");
const MCP_DIR = path.join(REPO_DIR, "mcp-server");

// Normalize to forward slashes for Claude Code (works on all platforms)
function fwd(p) {
  return p.replace(/\\/g, "/");
}

// ── Read/write JSON safely ───────────────────────────────────────────────
function readJson(filepath) {
  try {
    const raw = fs.readFileSync(filepath, "utf8");
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function writeJson(filepath, data) {
  const dir = path.dirname(filepath);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  if (fs.existsSync(filepath)) {
    const backupPath = filepath + ".backup";
    fs.copyFileSync(filepath, backupPath);
    console.log(`  Backed up ${filepath} → ${backupPath}`);
  }
  fs.writeFileSync(filepath, JSON.stringify(data, null, 2) + "\n");
}

// ── CLI arg helpers ──────────────────────────────────────────────────────
function getFlag(name) {
  const args = process.argv.slice(2);
  const idx = args.indexOf(name);
  return idx !== -1 && args[idx + 1] ? args[idx + 1] : null;
}

// ── Prompt helper ────────────────────────────────────────────────────────
function ask(question, defaultValue) {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });
  return new Promise((resolve) => {
    const prompt = defaultValue
      ? `${question} [${defaultValue}]: `
      : `${question}: `;
    rl.question(prompt, (answer) => {
      rl.close();
      resolve(answer.trim() || defaultValue || "");
    });
  });
}

// ── Build Recall hook configs (tagged) ───────────────────────────────────
function buildRecallHooks() {
  const node = "node";
  const h = (name) => fwd(path.join(HOOKS_DIR, name));

  return {
    UserPromptSubmit: [
      {
        hooks: [
          {
            type: "command",
            command: `${node} ${h("recall-retrieve.js")}`,
            timeout: 5,
            _tag: RECALL_TAG,
          },
        ],
      },
    ],
    PostToolUse: [
      {
        matcher: "Write|Edit",
        hooks: [
          {
            type: "command",
            command: `${node} ${h("observe-edit.js")}`,
            async: true,
            timeout: 10,
            _tag: RECALL_TAG,
          },
        ],
      },
    ],
    Stop: [
      {
        hooks: [
          {
            type: "command",
            command: `${node} ${h("session-save.js")}`,
            timeout: 10,
            _tag: RECALL_TAG,
          },
          {
            type: "command",
            command: `${node} ${h("recall-session-summary.js")}`,
            timeout: 10,
            _tag: RECALL_TAG,
          },
        ],
      },
    ],
  };
}

function buildStatusLineConfig() {
  return {
    type: "command",
    command: `node ${fwd(path.join(HOOKS_DIR, "recall-statusline.js"))}`,
    padding: 1,
    _tag: RECALL_TAG,
  };
}

function buildMcpServerConfig(host) {
  return {
    command: "node",
    args: [fwd(path.join(MCP_DIR, "index.js"))],
    env: {
      RECALL_HOST: host,
    },
  };
}

// ── Detect Recall hooks (tagged or legacy untagged) ──────────────────────
// Matches by _tag OR by command path containing known Recall hook filenames
// from this repo's hooks directory. Handles migration from untagged → tagged.
function isRecallHook(hook) {
  if (hook._tag === RECALL_TAG) return true;
  if (hook.command) {
    const cmd = hook.command;
    const hooksPath = fwd(HOOKS_DIR);
    return (
      cmd.includes(hooksPath) && RECALL_HOOK_FILES.some((f) => cmd.includes(f))
    );
  }
  return false;
}

// ── Smart merge: hooks ───────────────────────────────────────────────────
// Removes all Recall hooks (tagged or legacy) from existing config, then
// appends fresh tagged Recall hooks into matching groups or as new groups.
function mergeHooks(existingHooks, recallHooks) {
  const result = {};

  // Deep-clone existing hooks
  for (const event of Object.keys(existingHooks || {})) {
    if (!Array.isArray(existingHooks[event])) continue;
    result[event] = existingHooks[event].map((group) => ({
      ...group,
      hooks: Array.isArray(group.hooks) ? [...group.hooks] : [],
    }));
  }

  // Step 1: Strip all Recall hooks (tagged + legacy untagged) from every group
  for (const event of Object.keys(result)) {
    for (const group of result[event]) {
      group.hooks = group.hooks.filter((h) => !isRecallHook(h));
    }
    // Remove groups that became empty
    result[event] = result[event].filter((g) => g.hooks.length > 0);
    if (result[event].length === 0) {
      delete result[event];
    }
  }

  // Step 2: Add Recall hooks into matching or new groups
  for (const event of Object.keys(recallHooks)) {
    if (!result[event]) {
      result[event] = [];
    }

    for (const recallGroup of recallHooks[event]) {
      const matcher = recallGroup.matcher || null;
      const existing = result[event].find(
        (g) => (g.matcher || null) === matcher,
      );

      if (existing) {
        existing.hooks.push(...recallGroup.hooks);
      } else {
        // Clone the group so we don't mutate the template
        const newGroup = { hooks: [...recallGroup.hooks] };
        if (matcher) newGroup.matcher = matcher;
        result[event].push(newGroup);
      }
    }
  }

  return result;
}

// ── Smart merge: env vars ────────────────────────────────────────────────
function mergeEnvVars(existingEnv, recallEnv) {
  return { ...(existingEnv || {}), ...recallEnv };
}

function removeRecallEnvVars(env) {
  if (!env) return {};
  const result = { ...env };
  for (const key of RECALL_ENV_KEYS) {
    delete result[key];
  }
  return result;
}

// ── Strip Recall hooks only (for uninstall) ──────────────────────────────
function stripRecallHooks(existingHooks) {
  if (!existingHooks) return {};

  const result = {};
  for (const event of Object.keys(existingHooks)) {
    if (!Array.isArray(existingHooks[event])) continue;

    const groups = existingHooks[event]
      .map((group) => ({
        ...group,
        hooks: Array.isArray(group.hooks)
          ? group.hooks.filter((h) => !isRecallHook(h))
          : [],
      }))
      .filter((g) => g.hooks.length > 0);

    if (groups.length > 0) {
      result[event] = groups;
    }
  }
  return result;
}

// ── Verify required hook files exist ─────────────────────────────────────
function verifyHooks() {
  const required = [
    "recall-retrieve.js",
    "observe-edit.js",
    "session-save.js",
    "recall-session-summary.js",
    "recall-statusline.js",
  ];
  const missing = required.filter(
    (f) => !fs.existsSync(path.join(HOOKS_DIR, f)),
  );
  if (missing.length > 0) {
    console.error(`\nMissing hook files in ${HOOKS_DIR}:`);
    missing.forEach((f) => console.error(`  - ${f}`));
    console.error("\nRun this script from the Recall repo root.");
    process.exit(1);
  }
}

// ── Install ──────────────────────────────────────────────────────────────
async function install() {
  console.log("\n╔══════════════════════════════════════╗");
  console.log("║     Recall — Claude Code Installer    ║");
  console.log("╚══════════════════════════════════════╝\n");

  // Parse CLI flags
  let host = getFlag("--host");
  let apiKey = getFlag("--key");
  let ollamaHost = getFlag("--ollama");

  // Interactive prompts for missing values
  if (!host) {
    host = await ask(
      "Recall API host",
      process.env.RECALL_HOST || "http://localhost:8200",
    );
  }
  if (!apiKey) {
    apiKey = await ask(
      "Recall API key (leave blank to skip)",
      process.env.RECALL_API_KEY || "",
    );
  }
  if (!ollamaHost) {
    ollamaHost = await ask(
      "Ollama host (for session summaries)",
      process.env.OLLAMA_HOST || "http://localhost:11434",
    );
  }

  // Verify hooks exist
  verifyHooks();

  // Check MCP server deps
  if (!fs.existsSync(path.join(MCP_DIR, "node_modules"))) {
    console.log("\n⚠ MCP server dependencies not installed.");
    console.log(`  Run: cd ${fwd(MCP_DIR)} && npm install\n`);
  }

  // ── 1. MCP Server → ~/.claude.json ──
  console.log("1. Configuring MCP server...");
  const claudeJson = readJson(CLAUDE_JSON) || {};
  if (!claudeJson.mcpServers) {
    claudeJson.mcpServers = {};
  }
  claudeJson.mcpServers.recall = buildMcpServerConfig(host);
  writeJson(CLAUDE_JSON, claudeJson);
  console.log(`   ✓ Added "recall" MCP server to ${CLAUDE_JSON}`);

  // ── 2. Hooks + StatusLine → ~/.claude/settings.json ──
  console.log("\n2. Configuring hooks & statusline...");
  const settings = readJson(SETTINGS_JSON) || {};

  // Smart merge: only touch __recall__-tagged hooks
  settings.hooks = mergeHooks(settings.hooks, buildRecallHooks());
  settings.statusLine = buildStatusLineConfig();

  // ── 3. Env vars → settings.env ──
  console.log("\n3. Configuring environment variables...");
  const recallEnv = { RECALL_HOST: host };
  if (apiKey) recallEnv.RECALL_API_KEY = apiKey;
  if (ollamaHost) recallEnv.OLLAMA_HOST = ollamaHost;
  settings.env = mergeEnvVars(settings.env, recallEnv);

  writeJson(SETTINGS_JSON, settings);
  console.log(`   ✓ Merged hooks (tagged __recall__) into ${SETTINGS_JSON}`);
  console.log(`   ✓ Added statusline to ${SETTINGS_JSON}`);
  console.log(`   ✓ Merged env vars into ${SETTINGS_JSON}`);

  // Count preserved hooks
  const nonRecallCount = countNonRecallHooks(settings.hooks);
  if (nonRecallCount > 0) {
    console.log(`   ✓ Preserved ${nonRecallCount} non-Recall hook(s)`);
  }

  // ── Done ──
  console.log("\n✅ Installation complete!");
  console.log("   Restart Claude Code to activate.\n");
  console.log("Installed components:");
  console.log(
    "   • MCP Server — recall_store, recall_search, recall_context, ...",
  );
  console.log("   • UserPromptSubmit — auto-retrieves relevant memories");
  console.log("   • PostToolUse (Write|Edit) — observer (auto-stores facts)");
  console.log("   • Stop — session save + session summary to Recall");
  console.log("   • Statusline — context bar with auto-handoff at 90%");
  console.log("\nEnvironment:");
  console.log(`   RECALL_HOST=${host}`);
  if (apiKey) console.log(`   RECALL_API_KEY=${apiKey}`);
  if (ollamaHost) console.log(`   OLLAMA_HOST=${ollamaHost}`);
  console.log();
}

function countNonRecallHooks(hooks) {
  let count = 0;
  for (const event of Object.keys(hooks || {})) {
    if (!Array.isArray(hooks[event])) continue;
    for (const group of hooks[event]) {
      if (Array.isArray(group.hooks)) {
        count += group.hooks.filter((h) => !isRecallHook(h)).length;
      }
    }
  }
  return count;
}

// ── Uninstall ────────────────────────────────────────────────────────────
async function uninstall() {
  console.log("\nUninstalling Recall from Claude Code...\n");

  // Remove MCP server
  const claudeJson = readJson(CLAUDE_JSON);
  if (claudeJson && claudeJson.mcpServers && claudeJson.mcpServers.recall) {
    delete claudeJson.mcpServers.recall;
    writeJson(CLAUDE_JSON, claudeJson);
    console.log(`✓ Removed "recall" MCP server from ${CLAUDE_JSON}`);
  } else {
    console.log("  (no MCP server to remove)");
  }

  // Remove only Recall hooks, env vars, and statusline
  const settings = readJson(SETTINGS_JSON);
  if (settings) {
    let changed = false;

    // Strip only __recall__-tagged hooks
    if (settings.hooks) {
      const cleaned = stripRecallHooks(settings.hooks);
      if (Object.keys(cleaned).length > 0) {
        settings.hooks = cleaned;
      } else {
        delete settings.hooks;
      }
      changed = true;
    }

    // Remove statusline only if it's Recall's
    if (settings.statusLine && settings.statusLine._tag === RECALL_TAG) {
      delete settings.statusLine;
      changed = true;
    }

    // Remove only Recall env vars
    if (settings.env) {
      settings.env = removeRecallEnvVars(settings.env);
      if (Object.keys(settings.env).length === 0) {
        delete settings.env;
      }
      changed = true;
    }

    if (changed) {
      writeJson(SETTINGS_JSON, settings);
      console.log(
        `✓ Removed Recall hooks, env vars, and statusline from ${SETTINGS_JSON}`,
      );
      const remaining = countNonRecallHooks(settings.hooks);
      if (remaining > 0) {
        console.log(`  (preserved ${remaining} non-Recall hook(s))`);
      }
    } else {
      console.log("  (no hooks or statusline to remove)");
    }
  }

  console.log("\n✅ Uninstall complete. Restart Claude Code.\n");
}

// ── Main ─────────────────────────────────────────────────────────────────
async function main() {
  if (process.argv.includes("--uninstall")) {
    await uninstall();
  } else if (process.argv.includes("--help") || process.argv.includes("-h")) {
    console.log(`
Usage:
  node install.js                                      Install (interactive)
  node install.js --host <url>                         Install with host
  node install.js --host <url> --key <key>             Install with host + API key
  node install.js --host <url> --key <key> --ollama <url>  Full non-interactive
  node install.js --uninstall                          Remove only Recall config
  node install.js --help                               Show this help

Options:
  --host <url>     Recall API URL (default: http://localhost:8200)
  --key <key>      Recall API key (optional, for authenticated access)
  --ollama <url>   Ollama host URL (default: http://localhost:11434)
  --uninstall      Remove Recall hooks, env vars, MCP server (preserves other hooks)
`);
  } else {
    await install();
  }
}

main().catch((err) => {
  console.error("Install failed:", err.message);
  process.exit(1);
});
