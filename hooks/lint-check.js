#!/usr/bin/env node
/**
 * PostToolUse hook: Auto-lint after Write/Edit.
 *
 * Reads stdin for tool_input JSON, detects language by file extension,
 * runs the appropriate linter (ruff for Python, prettier for JS/TS).
 *
 * Optimizations:
 * - Ruff path cached after first probe
 * - No `npx tsc --noEmit` (full project typecheck per edit caused VS Code crashes)
 * - Skip build output, static assets, node_modules
 */

const { execSync } = require("child_process");
const { existsSync } = require("fs");
const path = require("path");

// Cached tool paths (persist across... well, they don't since each hook is a fresh process,
// but this avoids re-probing within a single invocation)
let _ruffPath = undefined;

const RUFF_PATHS = [
  "ruff",
  path.join(process.env.LOCALAPPDATA || "", "Programs", "Python", "Python311", "Scripts", "ruff.exe"),
  path.join(process.env.LOCALAPPDATA || "", "Programs", "Python", "Python312", "Scripts", "ruff.exe"),
  path.join(process.env.APPDATA || "", "Python", "Scripts", "ruff.exe"),
  path.join(process.env.LOCALAPPDATA || "", "Python", "pythoncore-3.14-64", "Scripts", "ruff.exe"),
];

// Dirs/patterns to skip entirely — no linting needed
const SKIP_PATTERNS = [
  "/node_modules/",
  "/dist/",
  "/build/",
  "/.next/",
  "/__pycache__/",
  "/static/dashboard/",
  "/.autopilot/",
  "/.ui/",
];

function findRuff() {
  if (_ruffPath !== undefined) return _ruffPath;
  for (const p of RUFF_PATHS) {
    try {
      execSync(`"${p}" --version`, { stdio: "pipe", timeout: 3000 });
      _ruffPath = p;
      return p;
    } catch {}
  }
  _ruffPath = null;
  return null;
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

function run(cmd, timeout = 10000) {
  try {
    execSync(cmd, { stdio: ["pipe", "pipe", "pipe"], timeout });
    return { ok: true, output: "" };
  } catch (e) {
    return {
      ok: false,
      output: (e.stderr?.toString() || "") + (e.stdout?.toString() || ""),
    };
  }
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
  const filePath = toolInput.file_path || toolInput.path || "";
  if (!filePath) process.exit(0);

  const normalized = filePath.replace(/\\/g, "/");

  // Skip hooks, build output, node_modules, static assets
  if (normalized.includes("/hooks/")) process.exit(0);
  if (SKIP_PATTERNS.some((p) => normalized.includes(p))) process.exit(0);

  if (filePath.endsWith(".py")) {
    const ruff = findRuff();
    if (!ruff) process.exit(0);

    // Fix + format in one pass, then verify
    run(`"${ruff}" check --fix "${filePath}"`);
    run(`"${ruff}" format "${filePath}"`);
    const check = run(`"${ruff}" check "${filePath}"`);
    if (!check.ok) {
      process.stderr.write(`Lint errors in ${filePath}:\n${check.output}\n`);
      process.exit(2);
    }
  } else if (/\.(ts|tsx|js|jsx)$/.test(filePath)) {
    // Prettier only — lightweight, fast
    run(`npx prettier --write "${filePath}"`);

    // ESLint only if config exists nearby (skip npx probe overhead otherwise)
    let hasEslintConfig = false;
    let dir = path.dirname(filePath);
    for (let i = 0; i < 5; i++) {
      if (
        existsSync(path.join(dir, "eslint.config.js")) ||
        existsSync(path.join(dir, "eslint.config.mjs")) ||
        existsSync(path.join(dir, ".eslintrc.json")) ||
        existsSync(path.join(dir, ".eslintrc.js"))
      ) {
        hasEslintConfig = true;
        break;
      }
      const parent = path.dirname(dir);
      if (parent === dir) break;
      dir = parent;
    }

    if (hasEslintConfig) {
      const eslint = run(`npx eslint --fix "${filePath}"`);
      if (!eslint.ok && !eslint.output.includes("eslint.config")) {
        const recheck = run(`npx eslint "${filePath}"`);
        if (!recheck.ok && !recheck.output.includes("eslint.config")) {
          process.stderr.write(`Lint errors in ${filePath}:\n${recheck.output}\n`);
          process.exit(2);
        }
      }
    }

    // NOTE: tsc --noEmit removed. Full project typecheck on every edit
    // caused VS Code crashes. Use /verify or manual tsc for type checking.
  }

  process.exit(0);
}

main().catch((e) => {
  process.stderr.write(`lint-check error: ${e.message}\n`);
  process.exit(0);
});
