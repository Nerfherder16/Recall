#!/usr/bin/env node
/**
 * Stop hook: Auto-save session state to Recall.
 *
 * Fires on Stop event — captures what was worked on.
 * Always exits 0 (don't prevent stopping).
 */

const RECALL_HOST = process.env.RECALL_HOST || "http://192.168.50.19:8200";
const RECALL_API_KEY = process.env.RECALL_API_KEY || "";

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

  const sessionId = parsed.session_id || parsed.sessionId;
  if (!sessionId) process.exit(0);

  const headers = { "Content-Type": "application/json" };
  if (RECALL_API_KEY) {
    headers["Authorization"] = `Bearer ${RECALL_API_KEY}`;
  }

  try {
    await fetch(`${RECALL_HOST}/observe/session-snapshot`, {
      method: "POST",
      headers,
      body: JSON.stringify({ session_id: sessionId }),
      signal: AbortSignal.timeout(5000),
    });
  } catch {
    // Ignore — don't block stopping
  }

  process.exit(0);
}

main().catch(() => process.exit(0));
