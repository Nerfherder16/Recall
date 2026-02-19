/**
 * Tests for Recall MCP Server tool definitions.
 *
 * Validates that all expected tools are registered and have correct schemas.
 * Uses Node's built-in test runner (node --test).
 */

import { readFileSync } from "fs";
import { strict as assert } from "assert";
import { describe, it } from "node:test";

// Parse the source to extract tool names from ListTools handler
const source = readFileSync(new URL("./index.js", import.meta.url), "utf-8");

// Extract all tool names from the source
const toolNameRegex = /name:\s*"(recall_\w+)"/g;
const toolNames = [];
let match;
while ((match = toolNameRegex.exec(source)) !== null) {
  toolNames.push(match[1]);
}

describe("MCP Server tool definitions", () => {
  it("should define all expected tools", () => {
    const expected = [
      "recall_store",
      "recall_search",
      "recall_search_full",
      "recall_timeline",
      "recall_context",
      "recall_stats",
      "recall_health",
      "recall_get",
      "recall_similar",
      "recall_rehydrate",
      "recall_session_start",
      "recall_session_end",
      "recall_ingest",
    ];

    for (const name of expected) {
      assert.ok(toolNames.includes(name), `Missing tool: ${name}`);
    }
  });

  it("should have recall_rehydrate tool with correct parameters", () => {
    // Verify the rehydrate tool definition exists in source
    assert.ok(
      source.includes('"recall_rehydrate"'),
      "recall_rehydrate tool not found",
    );
    assert.ok(
      source.includes("include_narrative"),
      "include_narrative param missing",
    );
    assert.ok(
      source.includes("include_anti_patterns"),
      "include_anti_patterns param missing",
    );
    assert.ok(source.includes("max_entries"), "max_entries param missing");
  });

  it("should have recall_rehydrate case in CallTool handler", () => {
    assert.ok(
      source.includes('case "recall_rehydrate"'),
      "recall_rehydrate handler not found in switch",
    );
    assert.ok(
      source.includes("/search/rehydrate"),
      "POST /search/rehydrate endpoint not called",
    );
  });
});
