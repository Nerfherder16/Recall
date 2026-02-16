#!/usr/bin/env node
/**
 * Recall Installer — configures Claude Code with:
 *   1. MCP server (recall) in ~/.claude.json
 *   2. Hooks (retrieve, observe, session-summary, etc.) in ~/.claude/settings.json
 *   3. Statusline (context % + auto-handoff) in ~/.claude/settings.json
 *
 * Usage:
 *   node install.js                     # Interactive — prompts for host
 *   node install.js --host http://...   # Non-interactive
 *   node install.js --uninstall         # Remove all Recall config
 *
 * Safe to re-run — merges into existing config without clobbering.
 */

const fs = require("fs");
const path = require("path");
const os = require("os");
const readline = require("readline");

// ── Paths ──────────────────────────────────────────────────────────────
const HOME = os.homedir();
const CLAUDE_JSON = path.join(HOME, ".claude.json");
const CLAUDE_DIR = path.join(HOME, ".claude");
const SETTINGS_JSON = path.join(CLAUDE_DIR, "settings.json");
const REPO_DIR = __dirname; // Where this script lives = repo root
const HOOKS_DIR = path.join(REPO_DIR, "hooks");
const MCP_DIR = path.join(REPO_DIR, "mcp-server");

// Normalize to forward slashes for Claude Code (works on all platforms)
function fwd(p) {
  return p.replace(/\\/g, "/");
}

// ── Read/write JSON safely ─────────────────────────────────────────────
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
  // Backup existing file
  if (fs.existsSync(filepath)) {
    const backupPath = filepath + ".backup";
    fs.copyFileSync(filepath, backupPath);
    console.log(`  Backed up ${filepath} → ${backupPath}`);
  }
  fs.writeFileSync(filepath, JSON.stringify(data, null, 2) + "\n");
}

// ── Prompt helper ──────────────────────────────────────────────────────
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

// ── Build hook configs ─────────────────────────────────────────────────
function buildHooksConfig() {
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
            command: `${node} ${h("lint-check.js")}`,
            timeout: 30,
          },
          {
            type: "command",
            command: `${node} ${h("observe-edit.js")}`,
            async: true,
            timeout: 10,
          },
        ],
      },
      {
        matcher: "Write|Edit|Bash",
        hooks: [
          {
            type: "command",
            command: `${node} ${h("context-monitor.js")}`,
            async: true,
            timeout: 5,
          },
        ],
      },
    ],
    Stop: [
      {
        hooks: [
          {
            type: "command",
            command: `${node} ${h("stop-guard.js")}`,
            timeout: 15,
          },
          {
            type: "command",
            command: `${node} ${h("session-save.js")}`,
            timeout: 10,
          },
          {
            type: "command",
            command: `${node} ${h("recall-session-summary.js")}`,
            timeout: 10,
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

// ── Verify hooks exist ─────────────────────────────────────────────────
function verifyHooks() {
  const required = [
    "recall-retrieve.js",
    "recall-session-summary.js",
    "recall-statusline.js",
    "observe-edit.js",
    "lint-check.js",
    "context-monitor.js",
    "stop-guard.js",
    "session-save.js",
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

// ── Install ────────────────────────────────────────────────────────────
async function install() {
  console.log("\n╔══════════════════════════════════════╗");
  console.log("║     Recall — Claude Code Installer    ║");
  console.log("╚══════════════════════════════════════╝\n");

  // Parse --host flag
  const args = process.argv.slice(2);
  const hostIdx = args.indexOf("--host");
  let host = hostIdx !== -1 && args[hostIdx + 1] ? args[hostIdx + 1] : null;

  if (!host) {
    host = await ask(
      "Recall API host",
      process.env.RECALL_HOST || "http://192.168.50.19:8200",
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

  // Merge hooks — replace Recall-related hooks entirely
  settings.hooks = buildHooksConfig();
  settings.statusLine = buildStatusLineConfig();

  writeJson(SETTINGS_JSON, settings);
  console.log(`   ✓ Added hooks (5 events) to ${SETTINGS_JSON}`);
  console.log(
    `   ✓ Added statusline (context bar + handoff) to ${SETTINGS_JSON}`,
  );

  // ── 3. Set env hint ──
  console.log("\n3. Environment variables (optional):");
  console.log(`   RECALL_HOST=${host}`);
  console.log("   RECALL_API_KEY=<your-key-if-auth-enabled>");
  console.log(
    "   OLLAMA_HOST=http://192.168.50.62:11434 (for handoff summarization)",
  );
  console.log("   OLLAMA_MODEL=qwen3:14b (default)");

  // ── Done ──
  console.log("\n✅ Installation complete!");
  console.log("   Restart Claude Code to activate.\n");
  console.log("Installed components:");
  console.log(
    "   • MCP Server — recall_store, recall_search, recall_context, ...",
  );
  console.log("   • UserPromptSubmit hook — auto-retrieves relevant memories");
  console.log(
    "   • PostToolUse hooks — lint check + observer (auto-stores facts)",
  );
  console.log("   • Stop hooks — session save + session summary to Recall");
  console.log("   • Statusline — context bar with auto-handoff at 90%\n");
}

// ── Uninstall ──────────────────────────────────────────────────────────
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

  // Remove hooks and statusline
  const settings = readJson(SETTINGS_JSON);
  if (settings) {
    let changed = false;
    if (settings.hooks) {
      delete settings.hooks;
      changed = true;
    }
    if (settings.statusLine) {
      delete settings.statusLine;
      changed = true;
    }
    if (changed) {
      writeJson(SETTINGS_JSON, settings);
      console.log(`✓ Removed hooks and statusline from ${SETTINGS_JSON}`);
    } else {
      console.log("  (no hooks or statusline to remove)");
    }
  }

  console.log("\n✅ Uninstall complete. Restart Claude Code.\n");
}

// ── Main ───────────────────────────────────────────────────────────────
async function main() {
  if (process.argv.includes("--uninstall")) {
    await uninstall();
  } else if (process.argv.includes("--help") || process.argv.includes("-h")) {
    console.log(`
Usage:
  node install.js                     Install (interactive)
  node install.js --host <url>        Install (non-interactive)
  node install.js --uninstall         Remove Recall config
  node install.js --help              Show this help
`);
  } else {
    await install();
  }
}

main().catch((err) => {
  console.error("Install failed:", err.message);
  process.exit(1);
});
