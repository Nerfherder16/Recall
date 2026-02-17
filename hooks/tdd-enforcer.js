#!/usr/bin/env node
/**
 * PostToolUse hook: TDD enforcement for Autopilot.
 *
 * When editing implementation files, checks for a corresponding test file.
 * - Build mode (.autopilot/mode === "build"): exit 2 (block) if no test file
 * - Normal mode: warn via stderr but allow (exit 0)
 *
 * Reads stdin for tool_input JSON with file_path.
 */

const { existsSync, readFileSync } = require("fs");
const path = require("path");

// File extensions that need tests
const IMPL_EXTENSIONS = [".py", ".ts", ".tsx", ".js", ".jsx"];

// Files/patterns exempt from test requirements
const EXEMPT_PATTERNS = [
  /\.config\./,
  /\.d\.ts$/,
  /__init__\.py$/,
  /\.env/,
  /migrations?\//,
  /\.md$/,
  /\.json$/,
  /\.css$/,
  /\.svg$/,
  /tailwind\./,
  /vite\./,
  /tsconfig/,
  /pyproject/,
  /setup\.(py|cfg)$/,
  /conftest\.py$/,
];

// Patterns that indicate a file IS a test file
const TEST_PATTERNS = [
  /test_/,
  /\.test\./,
  /\.spec\./,
  /__tests__\//,
  /tests?\//,
];

function readStdin() {
  return new Promise((resolve) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
    setTimeout(() => resolve(data), 3000);
  });
}

function isTestFile(filePath) {
  const normalized = filePath.replace(/\\/g, "/");
  return TEST_PATTERNS.some((p) => p.test(normalized));
}

function isExempt(filePath) {
  const normalized = filePath.replace(/\\/g, "/");
  return EXEMPT_PATTERNS.some((p) => p.test(normalized));
}

function isImplFile(filePath) {
  const ext = path.extname(filePath);
  return IMPL_EXTENSIONS.includes(ext);
}

function findTestFile(implPath) {
  const normalized = implPath.replace(/\\/g, "/");
  const ext = path.extname(implPath);
  const basename = path.basename(implPath, ext);
  const dir = path.dirname(implPath);

  // Python: src/feature.py → tests/test_feature.py
  if (ext === ".py") {
    const candidates = [
      path.join(dir, `test_${basename}.py`),
      path.join(dir, "..", "tests", `test_${basename}.py`),
      path.join(dir, "..", "tests", path.basename(dir), `test_${basename}.py`),
      normalized.replace(/src\//, "tests/test_").replace(/\.py$/, ".py"),
    ];

    // Also try: tests/test_<module>.py at project root
    const parts = normalized.split("/");
    const srcIdx = parts.indexOf("src");
    if (srcIdx >= 0) {
      const testPath = [
        ...parts.slice(0, srcIdx),
        "tests",
        ...parts.slice(srcIdx + 1),
      ];
      testPath[testPath.length - 1] = `test_${basename}.py`;
      candidates.push(testPath.join("/"));
    }

    for (const c of candidates) {
      if (existsSync(c)) return c;
    }
    return null;
  }

  // TypeScript/JS: src/Component.tsx → src/__tests__/Component.test.tsx
  if (/\.(ts|tsx|js|jsx)$/.test(ext)) {
    const testExt = ext.replace(/^\./, ".test.");
    const candidates = [
      path.join(dir, "__tests__", `${basename}${testExt}`),
      path.join(dir, `${basename}.test${ext}`),
      path.join(dir, `${basename}.spec${ext}`),
      path.join(dir, "__tests__", `${basename}.test${ext}`),
    ];

    // Also check tests/ at project root
    const parts = normalized.split("/");
    const srcIdx = parts.indexOf("src");
    if (srcIdx >= 0) {
      const testPath = [
        ...parts.slice(0, srcIdx),
        "tests",
        ...parts.slice(srcIdx + 1),
      ];
      testPath[testPath.length - 1] = `${basename}.test${ext}`;
      candidates.push(testPath.join("/"));
    }

    for (const c of candidates) {
      if (existsSync(c)) return c;
    }
    return null;
  }

  return null;
}

function getAutopilotMode(filePath) {
  // Walk up from file to find .autopilot/mode
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

  // Skip if not an implementation file
  if (!isImplFile(filePath)) process.exit(0);

  // Skip if file is exempt
  if (isExempt(filePath)) process.exit(0);

  // Skip if this IS a test file
  if (isTestFile(filePath)) process.exit(0);

  // Skip hook files
  if (filePath.replace(/\\/g, "/").includes("/hooks/")) process.exit(0);

  // Check for corresponding test file
  const testFile = findTestFile(filePath);
  const mode = getAutopilotMode(filePath);

  if (!testFile) {
    const msg = `TDD: No test file found for ${path.basename(filePath)}. Write tests first!\n`;

    if (mode === "build") {
      process.stderr.write(`BLOCKED: ${msg}`);
      process.exit(2);
    } else {
      process.stderr.write(`WARNING: ${msg}`);
      process.exit(0);
    }
  }

  process.exit(0);
}

main().catch((e) => {
  process.stderr.write(`tdd-enforcer error: ${e.message}\n`);
  process.exit(0);
});
