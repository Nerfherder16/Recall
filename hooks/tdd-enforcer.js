#!/usr/bin/env node
/**
 * PostToolUse hook: Warn when editing implementation files without corresponding tests.
 *
 * Behavior:
 * - In /build mode (`.autopilot/mode` === "build"): exit 2 (blocks) if test file missing
 * - Otherwise: stderr warning only
 *
 * Skips files that are exempt from TDD (configs, types, migrations, etc.)
 */

const { existsSync, readFileSync } = require("fs");
const path = require("path");

const EXEMPT_PATTERNS = [
  /\.config\.(ts|js|mjs|cjs)$/,
  /tsconfig.*\.json$/,
  /\.d\.ts$/,
  /__init__\.py$/,
  /migrations?\//,
  /\.env/,
  /\.md$/,
  /\.json$/,
  /\.yaml$/,
  /\.yml$/,
  /\.toml$/,
  /\.css$/,
  /\.svg$/,
  /\.png$/,
  /\.ico$/,
  /conftest\.py$/,
  /setup\.(py|cfg)$/,
  /pyproject\.toml$/,
  /vite\.config/,
  /tailwind\.config/,
  /postcss\.config/,
];

// Patterns that indicate a file IS a test file (checked against basename only)
const TEST_FILE_PATTERNS = [
  /^test_.*\.py$/,
  /^.*_test\.py$/,
  /^.*\.test\.(ts|tsx|js|jsx)$/,
  /^.*\.spec\.(ts|tsx|js|jsx)$/,
];

function readStdin() {
  return new Promise((resolve) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
    setTimeout(() => resolve(data), 2000);
  });
}

function getAutopilotMode(filePath) {
  let dir = path.dirname(filePath);
  for (let i = 0; i < 10; i++) {
    const modeFile = path.join(dir, ".autopilot", "mode");
    if (existsSync(modeFile)) {
      try {
        return readFileSync(modeFile, "utf8").trim();
      } catch {
        return "";
      }
    }
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return "";
}

function isExempt(filePath) {
  const normalized = filePath.replace(/\\/g, "/");
  return EXEMPT_PATTERNS.some((p) => p.test(normalized));
}

function isTestFile(filePath) {
  const basename = path.basename(filePath);
  // Check filename patterns
  if (TEST_FILE_PATTERNS.some((p) => p.test(basename))) return true;
  // Check if inside a __tests__ directory
  const normalized = filePath.replace(/\\/g, "/");
  return /__tests__\//.test(normalized);
}

function isImplementationFile(filePath) {
  return /\.(py|ts|tsx|js|jsx)$/.test(filePath);
}

/**
 * Search for a corresponding test file given an implementation file path.
 * Checks multiple common patterns:
 *   - tests/test_<name>.py, tests/<layer>/test_<name>.py
 *   - __tests__/<Name>.test.tsx
 *   - <name>.test.ts alongside the file
 */
function findTestFile(filePath) {
  const ext = path.extname(filePath);
  const base = path.basename(filePath, ext);
  const dir = path.dirname(filePath);
  const normalized = filePath.replace(/\\/g, "/");

  // Python files
  if (ext === ".py") {
    const candidates = [
      path.join(dir, `test_${base}.py`),
      path.join(dir, `${base}_test.py`),
    ];

    // Walk up to find a tests/ directory
    let searchDir = dir;
    for (let i = 0; i < 10; i++) {
      const testsDir = path.join(searchDir, "tests");
      if (existsSync(testsDir)) {
        candidates.push(path.join(testsDir, `test_${base}.py`));
        // Check subdirectories of tests/
        try {
          const { readdirSync, statSync } = require("fs");
          const entries = readdirSync(testsDir);
          for (const entry of entries) {
            const full = path.join(testsDir, entry);
            if (statSync(full).isDirectory()) {
              candidates.push(path.join(full, `test_${base}.py`));
            }
          }
        } catch {}
        break;
      }
      const parent = path.dirname(searchDir);
      if (parent === searchDir) break;
      searchDir = parent;
    }

    return candidates.find((c) => existsSync(c)) || null;
  }

  // TypeScript/JavaScript files
  if (/\.(ts|tsx|js|jsx)$/.test(ext)) {
    const candidates = [
      path.join(dir, `${base}.test${ext}`),
      path.join(dir, `${base}.spec${ext}`),
      path.join(dir, "__tests__", `${base}.test${ext}`),
      path.join(dir, "__tests__", `${base}.spec${ext}`),
    ];

    // Walk up to find a tests/ directory
    let searchDir = dir;
    for (let i = 0; i < 10; i++) {
      const testsDir = path.join(searchDir, "tests");
      if (existsSync(testsDir)) {
        candidates.push(path.join(testsDir, `${base}.test${ext}`));
        candidates.push(path.join(testsDir, `${base}.spec${ext}`));
        break;
      }
      const parent = path.dirname(searchDir);
      if (parent === searchDir) break;
      searchDir = parent;
    }

    return candidates.find((c) => existsSync(c)) || null;
  }

  return null;
}

/**
 * Check if a test file actually imports the implementation module.
 * Returns { imports: boolean }.
 * Reads first 30 lines — enough to cover import sections.
 */
function checkTestImports(testFile, implFile) {
  try {
    const content = readFileSync(testFile, "utf8");
    const lines = content.split("\n").slice(0, 30).join("\n");
    const implBase = path.basename(implFile, path.extname(implFile));

    // Python: from <module> import ... or import <module>
    if (implFile.endsWith(".py")) {
      const pyPattern = new RegExp(
        `(?:from\\s+\\S*${implBase}\\s+import|import\\s+\\S*${implBase})`,
      );
      return { imports: pyPattern.test(lines) };
    }

    // TS/JS: import ... from '...<basename>' or require('...<basename>')
    const jsPattern = new RegExp(
      `(?:import\\s+.*from\\s+.*${implBase}|require\\s*\\(.*${implBase})`,
    );
    return { imports: jsPattern.test(lines) };
  } catch {
    return { imports: true }; // Can't read — assume OK
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

  // Skip non-implementation files
  if (!isImplementationFile(filePath)) process.exit(0);

  // Skip exempt files (configs, types, migrations, etc.)
  if (isExempt(filePath)) process.exit(0);

  // Skip if the file being edited IS a test file
  if (isTestFile(filePath)) process.exit(0);

  // Skip hook files
  if (filePath.replace(/\\/g, "/").includes("/hooks/")) process.exit(0);

  // Look for a corresponding test file
  const testFile = findTestFile(filePath);

  if (testFile) {
    const { imports } = checkTestImports(testFile, filePath);
    if (!imports) {
      const implBasename = path.basename(filePath);
      const testBasename = path.basename(testFile);
      const mode = getAutopilotMode(filePath);
      const msg = mode === "build"
        ? `TDD enforcer: ${testBasename} exists but doesn't appear to import ${implBasename}.\n`
        : `TDD hint: ${testBasename} may not import ${implBasename}.\n`;
      process.stderr.write(`\n${msg}`);
    }
    process.exit(0); // Always exit 0 — indirect imports are valid
  }

  // No test file found
  const mode = getAutopilotMode(filePath);
  const basename = path.basename(filePath);

  if (mode === "build") {
    process.stderr.write(
      `\nTDD enforcer: No test file found for ${basename}.\n` +
        `In /build mode, every implementation file must have a corresponding test.\n` +
        `Write the test first (RED phase), then implement.\n`,
    );
    process.exit(2);
  } else {
    process.stderr.write(
      `\nTDD hint: No test file found for ${basename}. Consider adding tests.\n`,
    );
    process.exit(0);
  }
}

main().catch((e) => {
  process.stderr.write(`tdd-enforcer error: ${e.message}\n`);
  process.exit(0);
});
