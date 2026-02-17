# Recall MCP Server

MCP (Model Context Protocol) server for integrating Recall memory system with Claude Code.

## Quick Install (Recommended)

The installer configures the MCP server, hooks, and statusline all at once:

```bash
cd /path/to/Recall
cd mcp-server && npm install && cd ..
node install.js
```

This sets up:
- **MCP Server** — Recall tools available in Claude Code
- **UserPromptSubmit hook** — auto-retrieves relevant memories before Claude responds
- **PostToolUse hooks** — auto-stores facts from file edits
- **Stop hooks** — stores session summaries on exit
- **Statusline** — context usage bar with auto-handoff at 90%

To uninstall: `node install.js --uninstall`

## Manual Installation

### 1. Install dependencies

```bash
cd mcp-server
npm install
```

### 2. Add to Claude Code

Add this to your `~/.claude.json` (or `C:\Users\<you>\.claude.json` on Windows):

```json
{
  "mcpServers": {
    "recall": {
      "command": "node",
      "args": ["/path/to/Recall/mcp-server/index.js"],
      "env": {
        "RECALL_HOST": "http://your-recall-host:8200"
      }
    }
  }
}
```

Then restart Claude Code.

## Available Tools

| Tool | Description |
|------|-------------|
| `recall_store` | Store a new memory |
| `recall_search` | Browse memories (120-char summaries) |
| `recall_search_full` | Full content semantic search |
| `recall_context` | Assemble context for prompt injection |
| `recall_timeline` | Chronological memory timeline |
| `recall_stats` | Get system statistics |
| `recall_health` | Check service health |
| `recall_get` | Get memory by ID |
| `recall_similar` | Find similar memories |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RECALL_HOST` | `http://localhost:8200` | Recall API endpoint |
| `RECALL_API_KEY` | _(empty)_ | API key (if auth enabled) |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama host (for handoff summaries) |
| `OLLAMA_MODEL` | `qwen3:14b` | Model for handoff summarization |

## Hooks & Statusline

When installed via `install.js`, Claude Code gets these automatic behaviors:

### Memory Retrieval (UserPromptSubmit)
Every user message is searched against Recall. Top 5 relevant memories (similarity > 0.25) are injected as context. Skips trivial messages, greetings, and slash commands.

### Fact Extraction (PostToolUse)
When Claude edits files, the observer hook sends the changes to Recall's `/observe/file-change` endpoint. An LLM extracts facts and stores them automatically.

### Session Summary (Stop)
When a session ends, the transcript is summarized and stored to Recall as an episodic memory with the project name as domain tag.

### Context Handoff (Statusline)
The statusline shows a color-coded context usage bar. At 65%, it spawns a background process that:
1. Reads the conversation transcript
2. Sends it to Ollama for a detailed structured summary
3. Stores the summary to Recall with `context-handoff` tag and importance 0.7

This ensures session knowledge survives context compaction.

## Troubleshooting

### "Cannot connect to Recall"
- Check that Recall API is running: `curl http://your-host:8200/health`
- Verify network connectivity

### Tools not appearing
- Restart Claude Code after adding config
- Check `~/.claude.json` syntax is valid JSON
- Run `node mcp-server/index.js` manually to check for errors

### Statusline not showing
- Check `~/.claude/settings.json` has a `statusLine` block
- Re-run `node install.js` to regenerate config
