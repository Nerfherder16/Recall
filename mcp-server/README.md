# Recall MCP Server

MCP (Model Context Protocol) server for integrating Recall memory system with Claude Code.

## Installation

```bash
cd mcp-server
npm install
```

## Add to Claude Code

Add this to your `~/.claude.json` (or `C:\Users\<you>\.claude.json` on Windows):

```json
{
  "mcpServers": {
    "recall": {
      "command": "node",
      "args": ["C:/Users/trg16/Dev/Recall/mcp-server/index.js"],
      "env": {
        "RECALL_HOST": "http://192.168.50.19:8200"
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
| `recall_search` | Semantic search for memories |
| `recall_context` | Assemble context for prompt injection |
| `recall_stats` | Get system statistics |
| `recall_health` | Check service health |
| `recall_get` | Get memory by ID |
| `recall_similar` | Find similar memories |

## Usage in Claude Code

Once configured, Claude will have access to the Recall tools:

```
User: Store this fact: The payment service uses Stripe API v2023-10
Claude: [Uses recall_store tool]
       Memory stored! ID: abc123...

User: What do we know about payments?
Claude: [Uses recall_search tool]
       Found 3 memories about payments...
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RECALL_HOST` | `http://192.168.50.19:8200` | Recall API endpoint |

## Troubleshooting

### "Cannot connect to Recall"
- Check that Recall API is running: `curl http://192.168.50.19:8200/health`
- Verify network connectivity to the CasaOS VM

### Tools not appearing
- Restart Claude Code after adding config
- Check `~/.claude.json` syntax is valid JSON
- Run `node index.js` manually to check for errors
