#!/usr/bin/env node
/**
 * PostToolUse hook: Auto-lint after Write/Edit.
 *
 * Reads stdin for tool_input JSON, detects language by file extension,
 * runs the appropriate linter (ruff for Python, eslint/prettier for JS/TS).
 * Exit code 2 blocks Claude until errors are fixed.
 */

const { execSync } = require("child_process");
const { existsSync, readFileSync } = require("fs");
const path = require("path");

// Find ruff - check common locations
const RUFF_PATHS = [
  "ruff",
  path.join(
    process.env.LOCALAPPDATA || "",
    "Programs",
    "Python",
    "Python311",
    "Scripts",
    "ruff.exe",
  ),
  path.join(
    process.env.LOCALAPPDATA || "",
    "Programs",
    "Python",
    "Python312",
    "Scripts",
    "ruff.exe",
  ),
  path.join(process.env.APPDATA || "", "Python", "Scripts", "ruff.exe"),
  // pip install --user location
  path.join(
    process.env.LOCALAPPDATA || "",
    "Python",
    "pythoncore-3.14-64",
    "Scripts",
    "ruff.exe",
  ),
];

function findRuff() {
  for (const p of RUFF_PATHS) {
    try {
      execSync(`"${p}" --version`, { stdio: "pipe", timeout: 5000 });
      return p;
    } catch {}
  }
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

function run(cmd) {
  try {
    execSync(cmd, { stdio: ["pipe", "pipe", "pipe"], timeout: 20000 });
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

  // Skip linting hook files themselves
  if (filePath.replace(/\\/g, "/").includes("/hooks/")) process.exit(0);

  if (filePath.endsWith(".py")) {
    const ruff = findRuff();
    if (!ruff) {
      // ruff not installed — skip silently
      process.exit(0);
    }

    run(`"${ruff}" check --fix "${filePath}"`);
    run(`"${ruff}" format "${filePath}"`);
    const check = run(`"${ruff}" check "${filePath}"`);
    if (!check.ok) {
      process.stderr.write(`Lint errors in ${filePath}:\n${check.output}\n`);
      process.exit(2);
    }
  } else if (/\.(ts|tsx|js|jsx)$/.test(filePath)) {
    // JS/TS: prettier (skip eslint if no config found)
    run(`npx prettier --write "${filePath}"`);
    const eslint = run(`npx eslint --fix "${filePath}"`);
    if (!eslint.ok && !eslint.output.includes("eslint.config")) {
      // Only block on real lint errors, not missing config
      const recheck = run(`npx eslint "${filePath}"`);
      if (!recheck.ok && !recheck.output.includes("eslint.config")) {
        process.stderr.write(
          `Lint errors in ${filePath}:\n${recheck.output}\n`,
        );
        process.exit(2);
      }
    }

    // TypeScript type checking for .ts/.tsx files
    if (/\.(ts|tsx)$/.test(filePath)) {
      // Find tsconfig by walking up from the file
      let tsconfigDir = path.dirname(filePath);
      let tsconfigFound = false;
      for (let i = 0; i < 10; i++) {
        if (existsSync(path.join(tsconfigDir, "tsconfig.json"))) {
          tsconfigFound = true;
          break;
        }
        const parent = path.dirname(tsconfigDir);
        if (parent === tsconfigDir) break;
        tsconfigDir = parent;
      }

      if (tsconfigFound) {
        const tsc = run(
          `npx tsc --noEmit --project "${path.join(tsconfigDir, "tsconfig.json")}"`,
        );
        if (!tsc.ok) {
          // Check autopilot mode to decide block vs warn
          const mode = getAutopilotMode(filePath);
          if (mode === "build") {
            process.stderr.write(
              `Type errors (blocking in build mode):\n${tsc.output}\n`,
            );
            process.exit(2);
          } else {
            process.stderr.write(
              `Type check warnings:\n${tsc.output}\n`,
            );
            // Don't block in normal mode — just warn
          }
        }
      }
    }
  }

  process.exit(0);
}

main().catch((e) => {
  process.stderr.write(`lint-check error: ${e.message}\n`);
  process.exit(0);
});
