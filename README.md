# Recall

**Living Memory System for AI Assistants**

Recall is a semantic, evolving, context-aware memory system designed to give AI assistants true persistent memory - not just storage, but understanding.

## Philosophy

Traditional memory systems are filing cabinets: store text, retrieve by keyword.

Recall is designed like biological memory:
- **Memories form** through attention and importance
- **Memories consolidate** through background processing (like sleep)
- **Memories decay** without reinforcement
- **Memories connect** to form knowledge graphs
- **Memories reconstruct** based on current context

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         RECALL                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐     ┌─────────────────┐               │
│  │   API (FastAPI) │     │  Workers (ARQ)  │               │
│  │   - Store       │     │  - Consolidate  │               │
│  │   - Retrieve    │     │  - Decay        │               │
│  │   - Search      │     │  - Extract      │               │
│  └────────┬────────┘     └────────┬────────┘               │
│           │                       │                         │
│           └───────────┬───────────┘                         │
│                       │                                     │
│  ┌────────────────────┴────────────────────┐               │
│  │              STORAGE LAYER              │               │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐│               │
│  │  │  Qdrant  │ │  Neo4j   │ │  Redis   ││               │
│  │  │ (vectors)│ │ (graph)  │ │ (cache)  ││               │
│  │  └──────────┘ └──────────┘ └──────────┘│               │
│  └─────────────────────────────────────────┘               │
│                                                             │
│  ┌─────────────────────────────────────────┐               │
│  │            MEMORY TYPES                 │               │
│  │  Episodic  │  Semantic  │  Procedural   │               │
│  │  (events)  │  (facts)   │  (workflows)  │               │
│  └─────────────────────────────────────────┘               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Features

### Semantic Understanding
- **BGE-large embeddings** (1024 dimensions) via Ollama
- True similarity search, not keyword matching
- Understanding of meaning, not just words

### Memory Dynamics
- **Importance decay** - unused memories fade
- **Reinforcement** - accessed memories strengthen
- **Stability** - consolidated memories resist decay
- **Confidence** - tracks certainty of information

### Graph Relationships
- Memories connect through typed relationships
- Traversal for context expansion
- Contradiction detection

### Background Processing
- **Consolidation** - merges similar memories
- **Pattern extraction** - learns from episodes
- **Decay** - applies forgetting curve

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Ollama running somewhere on your network with `bge-large` model

### Option 1: Deploy Script (Recommended)

**Linux/Mac/WSL:**
```bash
git clone https://github.com/Nerfherder16/Recall.git
cd Recall
chmod +x scripts/deploy.sh
./scripts/deploy.sh http://YOUR_OLLAMA_HOST:11434
```

**Windows PowerShell:**
```powershell
git clone https://github.com/Nerfherder16/Recall.git
cd Recall
.\scripts\deploy.ps1 -OllamaHost "http://YOUR_OLLAMA_HOST:11434"
```

The deploy script will:
1. Check Docker and Ollama prerequisites
2. Pull the `bge-large` embedding model if missing
3. Create a `.env` configuration file
4. Build and start the full stack (6 containers)
5. Wait for health checks to pass
6. Warm up the embedding model

### Option 2: Manual

```bash
# Pull the embedding model
ollama pull bge-large

# Edit docker-compose.yml to set your RECALL_OLLAMA_HOST
# Then start the stack
docker compose up -d

# Check health
curl http://localhost:8200/health
```

### First Memory

```bash
curl -X POST http://localhost:8200/memory/store \
  -H "Content-Type: application/json" \
  -d '{
    "content": "JWT tokens should use 24h expiry for this project",
    "memory_type": "semantic",
    "domain": "auth",
    "tags": ["jwt", "security"]
  }'
```

### Search

```bash
curl -X POST http://localhost:8200/search/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the token configuration?",
    "limit": 5
  }'
```

---

## Claude Code Integration (MCP Server)

Recall ships with an MCP server that gives Claude Code direct access to the memory system.

### Setup

```bash
cd mcp-server
npm install
```

Add to your `~/.claude.json` under `mcpServers`:

```json
{
  "recall": {
    "command": "node",
    "args": ["/path/to/Recall/mcp-server/index.js"],
    "env": {
      "RECALL_HOST": "http://YOUR_SERVER:8200"
    }
  }
}
```

Restart Claude Code. The `recall_*` tools will be available.

### MCP Tools

| Tool | Description |
|------|-------------|
| `recall_store` | Store a memory (semantic, episodic, or procedural) |
| `recall_search` | Semantic similarity search |
| `recall_context` | Assemble formatted context for prompt injection |
| `recall_stats` | Get memory counts and system statistics |
| `recall_health` | Check health of all services |
| `recall_get` | Retrieve a specific memory by UUID |
| `recall_similar` | Find memories similar to a given one |

### Slash Commands

Copy the skill file to your Claude Code skills directory:

```bash
cp mcp-server/recall-skill.md ~/.claude/skills/recall.md
```

Then use in Claude Code:
- `/recall store <content>` - Store a fact, fix, or decision
- `/recall search <query>` - Find relevant memories
- `/recall context <topic>` - Get full context on a topic
- `/recall health` - Check system status

---

## API Reference

**Base URL:** `http://localhost:8200`

### Memory Operations

#### `POST /memory/store`
Store a new memory. The content is embedded with BGE-large and stored in both vector (Qdrant) and graph (Neo4j) storage.

**Request:**
```json
{
  "content": "The auth service uses bcrypt for password hashing",
  "memory_type": "semantic",
  "source": "user",
  "domain": "auth",
  "tags": ["security", "passwords"],
  "importance": 0.7,
  "confidence": 0.9,
  "session_id": null,
  "metadata": {}
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `content` | string | *required* | The memory content |
| `memory_type` | enum | `semantic` | `semantic`, `episodic`, or `procedural` |
| `source` | enum | `user` | `user`, `system`, `observation`, `inference` |
| `domain` | string | `general` | Project/topic domain for filtering |
| `tags` | string[] | `[]` | Tags for categorization |
| `importance` | float | `0.5` | 0-1, higher = slower decay |
| `confidence` | float | `0.8` | 0-1, certainty of information |
| `session_id` | string? | `null` | Links memory to a session's working memory |
| `metadata` | object | `{}` | Arbitrary metadata |

**Response:**
```json
{
  "id": "uuid",
  "content_hash": "hex-hash",
  "created": true,
  "message": "Memory stored successfully"
}
```

#### `GET /memory/{id}`
Get a memory by UUID.

#### `DELETE /memory/{id}`
Delete a memory from all stores.

#### `POST /memory/relationship`
Create a typed relationship between two memories.

**Request:**
```json
{
  "source_id": "uuid-1",
  "target_id": "uuid-2",
  "relationship_type": "related_to",
  "strength": 0.7,
  "bidirectional": false
}
```

Relationship types: `related_to`, `causes`, `contradicts`, `refines`, `temporal_next`, `part_of`, `derived_from`

#### `GET /memory/{id}/related`
Get memories connected via graph traversal.

Query params: `max_depth` (default 2), `limit` (default 10)

### Search & Retrieval

#### `POST /search/query`
Semantic search using the full retrieval pipeline: vector similarity, graph expansion, context filtering, and ranking.

**Request:**
```json
{
  "query": "How does the auth system work?",
  "memory_types": ["semantic", "procedural"],
  "domains": ["auth"],
  "tags": ["security"],
  "min_importance": 0.3,
  "expand_relationships": true,
  "max_depth": 2,
  "limit": 10,
  "session_id": null,
  "current_file": null,
  "current_task": null
}
```

**Response:**
```json
{
  "results": [
    {
      "id": "uuid",
      "content": "The auth service uses bcrypt...",
      "memory_type": "semantic",
      "domain": "auth",
      "score": 0.89,
      "similarity": 0.92,
      "graph_distance": 0,
      "importance": 0.7,
      "tags": ["security"]
    }
  ],
  "total": 1,
  "query": "How does the auth system work?"
}
```

#### `POST /search/context`
Assemble formatted context for injection into prompts. Groups memories by type under markdown headers.

**Request:**
```json
{
  "query": "deployment process",
  "session_id": null,
  "current_file": null,
  "current_task": null,
  "max_tokens": 2000,
  "include_working_memory": true
}
```

**Response:**
```json
{
  "context": "## Known Facts\n- ...\n\n## Workflows\n- ...",
  "memories_used": 5,
  "estimated_tokens": 420,
  "breakdown": {
    "working_memory": 0,
    "semantic": 3,
    "episodic": 0,
    "procedural": 2
  }
}
```

#### `GET /search/similar/{id}?limit=5`
Find memories semantically similar to a given memory.

### Sessions

Sessions scope working memory and provide context for memory operations.

#### `POST /session/start`
```json
{
  "session_id": null,
  "working_directory": "/path/to/project",
  "current_task": "Fix auth bug"
}
```

#### `POST /session/end`
```json
{
  "session_id": "uuid",
  "trigger_consolidation": true
}
```

#### `GET /session/{id}` - Session status
#### `GET /session/{id}/working-memory` - Working memory contents
#### `POST /session/{id}/context` - Update session context

### System

#### `GET /health`
Returns health status of all services (API, Qdrant, Neo4j, Redis) with memory/node counts.

#### `GET /stats`
Returns total memory count, graph node/relationship counts, and active session count.

---

## Docker Services

| Container | Image | Port | Purpose |
|-----------|-------|------|---------|
| `recall-api` | Built from Dockerfile | 8200 | FastAPI application |
| `recall-worker` | Built from Dockerfile | - | ARQ background tasks |
| `recall-qdrant` | qdrant/qdrant | 6333, 6334 | Vector storage |
| `recall-neo4j` | neo4j:5-community | 7575, 7688 | Graph storage |
| `recall-postgres` | postgres:16-alpine | 5433 | Metadata (future) |
| `recall-redis` | redis:7-alpine | 6380 | Cache, sessions, working memory |

---

## Configuration

All configuration is via environment variables (prefix `RECALL_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `RECALL_ENV` | `development` | Environment mode |
| `RECALL_OLLAMA_HOST` | `http://192.168.50.62:11434` | Ollama API endpoint |
| `RECALL_QDRANT_HOST` | `qdrant` | Qdrant hostname |
| `RECALL_QDRANT_PORT` | `6333` | Qdrant port |
| `RECALL_NEO4J_URI` | `bolt://neo4j:7687` | Neo4j connection |
| `RECALL_NEO4J_USER` | `neo4j` | Neo4j username |
| `RECALL_NEO4J_PASSWORD` | `recallmemory` | Neo4j password |
| `RECALL_REDIS_URL` | `redis://redis:6379` | Redis connection |
| `RECALL_POSTGRES_DSN` | (see docker-compose) | PostgreSQL DSN |
| `RECALL_EMBEDDING_MODEL` | `bge-large` | Ollama embedding model |
| `RECALL_EMBEDDING_DIMS` | `1024` | Embedding dimensions |

---

## Memory Types

| Type | Use For | Examples |
|------|---------|---------|
| **semantic** | Facts, concepts, relationships | "The API uses JWT auth with 24h expiry" |
| **episodic** | Events, experiences, sessions | "Fixed the UUID collision bug on 2026-02-14" |
| **procedural** | How-to, workflows, processes | "To deploy: run tests, build container, push to registry" |

---

## Development

### Install dependencies
```bash
pip install -e ".[dev]"
```

### Run API locally
```bash
uvicorn src.api.main:app --reload --port 8200
```

### Run worker locally
```bash
arq src.workers.main.WorkerSettings
```

### Run tests
```bash
pytest
```

### Lint
```bash
ruff check src/
mypy src/
```

### Common Docker commands
```bash
# View API logs
docker compose logs -f api

# Restart API after code changes
docker compose restart api

# Shell into API container
docker compose exec api /bin/bash

# Full rebuild
docker compose down && docker compose build && docker compose up -d
```

---

## Project Status

Active development. Current state:

- [x] Core API (store, search, context, sessions)
- [x] Vector storage (Qdrant)
- [x] Graph storage (Neo4j)
- [x] Cache & sessions (Redis)
- [x] Background workers (decay, consolidation, patterns)
- [x] Docker Compose deployment
- [x] Deploy scripts (bash + PowerShell)
- [x] MCP server for Claude Code
- [ ] Integration tests
- [ ] Production hardening (secrets management, CORS lockdown)
- [ ] Prometheus metrics
- [ ] Database migrations

## License

MIT
