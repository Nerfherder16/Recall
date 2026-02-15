#!/usr/bin/env node
/**
 * PostToolUse hook: Send Write/Edit data to Recall for auto-observation.
 *
 * Async, non-blocking — fires and forgets. Recall being offline
 * should never block coding.
 */

const RECALL_HOST = process.env.RECALL_HOST || "http://192.168.50.19:8200";
const RECALL_API_KEY = process.env.RECALL_API_KEY || "";
const MAX_CONTENT_SIZE = 10000;

function readStdin() {
  return new Promise((resolve) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
    setTimeout(() => resolve(data), 3000);
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

  const toolInput = parsed.tool_input || {};
  const toolName = parsed.tool_name || "Write";
  const filePath = toolInput.file_path || toolInput.path || "";

  if (!filePath) process.exit(0);

  const body = {
    file_path: filePath,
    tool_name: toolName,
  };

  if (toolName === "Edit" || toolName === "edit") {
    body.old_string = (toolInput.old_string || "").slice(0, 5000);
    body.new_string = (toolInput.new_string || "").slice(0, 5000);
  } else {
    const content = toolInput.content || "";
    if (content.length > MAX_CONTENT_SIZE) {
      process.exit(0);
    }
    body.content = content;
  }

  const headers = { "Content-Type": "application/json" };
  if (RECALL_API_KEY) {
    headers["Authorization"] = `Bearer ${RECALL_API_KEY}`;
  }

  try {
    await fetch(`${RECALL_HOST}/observe/file-change`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(5000),
    });
  } catch {
    // Ignore — don't block coding
  }

  process.exit(0);
}

main().catch(() => process.exit(0));
