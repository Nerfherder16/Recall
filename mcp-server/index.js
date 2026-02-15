#!/usr/bin/env node
/**
 * Recall MCP Server
 *
 * Provides Claude Code with direct access to the Recall memory system.
 * Wraps the Recall REST API at http://192.168.50.19:8200
 *
 * Tools:
 *   - recall_store: Store a new memory
 *   - recall_search: Semantic search for memories
 *   - recall_context: Get assembled context for injection
 *   - recall_stats: Get system statistics
 *   - recall_health: Check system health
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

// Configuration - can override with env vars
const RECALL_HOST = process.env.RECALL_HOST || "http://192.168.50.19:8200";
const RECALL_API_KEY = process.env.RECALL_API_KEY || "";

// Helper for API calls
async function recallAPI(endpoint, method = "GET", body = null) {
  const url = `${RECALL_HOST}${endpoint}`;
  const headers = { "Content-Type": "application/json" };
  if (RECALL_API_KEY) {
    headers["Authorization"] = `Bearer ${RECALL_API_KEY}`;
  }
  const options = {
    method,
    headers,
  };
  if (body) {
    options.body = JSON.stringify(body);
  }

  try {
    const response = await fetch(url, options);
    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Recall API error (${response.status}): ${error}`);
    }
    return await response.json();
  } catch (error) {
    if (error.cause?.code === 'ECONNREFUSED') {
      throw new Error(`Cannot connect to Recall at ${RECALL_HOST}. Is the API running?`);
    }
    throw error;
  }
}

// Create the MCP server
const server = new Server(
  {
    name: "recall",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// Define available tools
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "recall_store",
        description: "Store a memory in Recall. Use this to persist important facts, decisions, fixes, and learnings. Memories are semantically indexed and can be retrieved later.",
        inputSchema: {
          type: "object",
          properties: {
            content: {
              type: "string",
              description: "The memory content to store (be descriptive and specific)",
            },
            memory_type: {
              type: "string",
              enum: ["semantic", "episodic", "procedural"],
              description: "Type: semantic (facts), episodic (events/experiences), procedural (how-to/workflows)",
            },
            domain: {
              type: "string",
              description: "Optional domain/project name for filtering (e.g., 'recall-project', 'family-hub')",
            },
            tags: {
              type: "array",
              items: { type: "string" },
              description: "Optional tags for categorization",
            },
            importance: {
              type: "number",
              minimum: 0,
              maximum: 1,
              description: "Importance score 0-1 (default 0.5). Higher = slower decay",
            },
          },
          required: ["content", "memory_type"],
        },
      },
      {
        name: "recall_search",
        description: "Search memories by semantic similarity. Returns relevant memories ranked by similarity score.",
        inputSchema: {
          type: "object",
          properties: {
            query: {
              type: "string",
              description: "Natural language search query",
            },
            limit: {
              type: "integer",
              minimum: 1,
              maximum: 20,
              description: "Maximum results to return (default 5)",
            },
            domain: {
              type: "string",
              description: "Optional domain filter",
            },
            memory_type: {
              type: "string",
              enum: ["semantic", "episodic", "procedural"],
              description: "Optional type filter",
            },
            min_similarity: {
              type: "number",
              minimum: 0,
              maximum: 1,
              description: "Minimum similarity threshold (default 0.5)",
            },
          },
          required: ["query"],
        },
      },
      {
        name: "recall_context",
        description: "Assemble context from memories for injection into prompts. Returns formatted markdown with sections for different memory types.",
        inputSchema: {
          type: "object",
          properties: {
            query: {
              type: "string",
              description: "Context query (what topic to retrieve context about)",
            },
            domain: {
              type: "string",
              description: "Optional domain filter",
            },
            max_tokens: {
              type: "integer",
              description: "Maximum tokens for context (default 2000)",
            },
          },
          required: ["query"],
        },
      },
      {
        name: "recall_stats",
        description: "Get Recall system statistics including memory counts by type and domain.",
        inputSchema: {
          type: "object",
          properties: {},
        },
      },
      {
        name: "recall_health",
        description: "Check Recall system health. Returns status of all services (Qdrant, Neo4j, Redis, etc.)",
        inputSchema: {
          type: "object",
          properties: {},
        },
      },
      {
        name: "recall_get",
        description: "Get a specific memory by its ID",
        inputSchema: {
          type: "object",
          properties: {
            id: {
              type: "string",
              description: "Memory UUID",
            },
          },
          required: ["id"],
        },
      },
      {
        name: "recall_similar",
        description: "Find memories similar to a given memory ID",
        inputSchema: {
          type: "object",
          properties: {
            id: {
              type: "string",
              description: "Memory UUID to find similar memories for",
            },
            limit: {
              type: "integer",
              minimum: 1,
              maximum: 20,
              description: "Maximum results (default 5)",
            },
          },
          required: ["id"],
        },
      },
      {
        name: "recall_session_start",
        description: "Start a new Recall session. Call this at the beginning of a conversation or work session. Returns a session ID for use with recall_ingest and recall_session_end.",
        inputSchema: {
          type: "object",
          properties: {
            working_directory: {
              type: "string",
              description: "Current working directory path",
            },
            current_task: {
              type: "string",
              description: "Description of the current task",
            },
          },
        },
      },
      {
        name: "recall_session_end",
        description: "End a Recall session. Cleans up pending signals and optionally triggers consolidation of session memories.",
        inputSchema: {
          type: "object",
          properties: {
            session_id: {
              type: "string",
              description: "Session ID to end",
            },
            trigger_consolidation: {
              type: "boolean",
              description: "Whether to trigger memory consolidation (default true)",
            },
          },
          required: ["session_id"],
        },
      },
      {
        name: "recall_ingest",
        description: "Ingest conversation turns for automatic signal detection. Call this after each meaningful exchange to let Recall auto-detect and store important signals (error fixes, decisions, facts, workflows, etc.) as memories. Requires an active session.",
        inputSchema: {
          type: "object",
          properties: {
            session_id: {
              type: "string",
              description: "Active Recall session ID",
            },
            turns: {
              type: "array",
              items: {
                type: "object",
                properties: {
                  role: {
                    type: "string",
                    enum: ["user", "assistant", "system"],
                    description: "Who sent this message",
                  },
                  content: {
                    type: "string",
                    description: "The message content",
                  },
                },
                required: ["role", "content"],
              },
              description: "Conversation turns to analyze",
            },
          },
          required: ["session_id", "turns"],
        },
      },
    ],
  };
});

// Handle tool calls
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case "recall_store": {
        const body = {
          content: args.content,
          memory_type: args.memory_type,
        };
        if (args.domain) body.domain = args.domain;
        if (args.tags) body.tags = args.tags;
        if (args.importance !== undefined) body.importance = args.importance;

        const result = await recallAPI("/memory/store", "POST", body);
        return {
          content: [
            {
              type: "text",
              text: `Memory stored successfully!\nID: ${result.id}\nContent hash: ${result.content_hash}`,
            },
          ],
        };
      }

      case "recall_search": {
        const body = {
          query: args.query,
          limit: args.limit || 5,
        };
        if (args.domain) body.domains = [args.domain];
        if (args.memory_type) body.memory_types = [args.memory_type];
        if (args.min_similarity !== undefined) body.min_similarity = args.min_similarity;

        const result = await recallAPI("/search/query", "POST", body);

        if (result.results.length === 0) {
          return {
            content: [{ type: "text", text: "No memories found matching your query." }],
          };
        }

        const formatted = result.results.map((m, i) =>
          `${i + 1}. [${(m.similarity * 100).toFixed(1)}%] (${m.memory_type}) ${m.content}`
        ).join("\n\n");

        return {
          content: [
            {
              type: "text",
              text: `Found ${result.total} memories:\n\n${formatted}`,
            },
          ],
        };
      }

      case "recall_context": {
        const body = {
          query: args.query,
        };
        if (args.domain) body.domain = args.domain;
        if (args.max_tokens) body.max_tokens = args.max_tokens;

        const result = await recallAPI("/search/context", "POST", body);

        return {
          content: [
            {
              type: "text",
              text: `Context assembled (${result.memories_used} memories, ~${result.estimated_tokens} tokens):\n\n${result.context}`,
            },
          ],
        };
      }

      case "recall_stats": {
        const result = await recallAPI("/stats");
        return {
          content: [
            {
              type: "text",
              text: `Recall Statistics:\n${JSON.stringify(result, null, 2)}`,
            },
          ],
        };
      }

      case "recall_health": {
        const result = await recallAPI("/health");
        const status = result.status === "healthy" ? "✅ Healthy" : "⚠️ " + result.status;
        const services = Object.entries(result.checks || {})
          .map(([name, val]) => `  ${String(val).startsWith("ok") ? "✅" : "❌"} ${name}: ${val}`)
          .join("\n");

        return {
          content: [
            {
              type: "text",
              text: `Recall System: ${status}\n\nServices:\n${services}`,
            },
          ],
        };
      }

      case "recall_get": {
        const result = await recallAPI(`/memory/${args.id}`);
        return {
          content: [
            {
              type: "text",
              text: `Memory ${args.id}:\n${JSON.stringify(result, null, 2)}`,
            },
          ],
        };
      }

      case "recall_similar": {
        const limit = args.limit || 5;
        const result = await recallAPI(`/search/similar/${args.id}?limit=${limit}`);

        const formatted = (result.similar || []).map((m, i) =>
          `${i + 1}. [${(m.similarity * 100).toFixed(1)}%] ${m.content}`
        ).join("\n\n");

        return {
          content: [
            {
              type: "text",
              text: `Similar memories:\n\n${formatted}`,
            },
          ],
        };
      }

      case "recall_session_start": {
        const body = {};
        if (args.working_directory) body.working_directory = args.working_directory;
        if (args.current_task) body.current_task = args.current_task;

        const result = await recallAPI("/session/start", "POST", body);
        return {
          content: [
            {
              type: "text",
              text: `Session started: ${result.session_id}\nStarted at: ${result.started_at}`,
            },
          ],
        };
      }

      case "recall_session_end": {
        const body = {
          session_id: args.session_id,
          trigger_consolidation: args.trigger_consolidation !== false,
        };

        const result = await recallAPI("/session/end", "POST", body);
        return {
          content: [
            {
              type: "text",
              text: `Session ${result.session_id} ended. Memories: ${result.memories_in_session}. Consolidation: ${result.consolidation_queued ? "queued" : "skipped"}.`,
            },
          ],
        };
      }

      case "recall_ingest": {
        const result = await recallAPI("/ingest/turns", "POST", {
          session_id: args.session_id,
          turns: args.turns,
        });

        return {
          content: [
            {
              type: "text",
              text: `Ingested ${result.turns_ingested} turns (${result.total_turns} total). Signal detection ${result.detection_queued ? "queued" : "skipped"}.`,
            },
          ],
        };
      }

      default:
        throw new Error(`Unknown tool: ${name}`);
    }
  } catch (error) {
    return {
      content: [
        {
          type: "text",
          text: `Error: ${error.message}`,
        },
      ],
      isError: true,
    };
  }
});

// Start the server
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("Recall MCP server running");
}

main().catch(console.error);
