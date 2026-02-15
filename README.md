# Recall

**Living Memory System for AI Assistants**

Recall is a semantic, evolving, context-aware memory system designed to give AI assistants true persistent memory - not just storage, but understanding.

## Philosophy

Traditional memory systems are filing cabinets: store text, retrieve by keyword.

Recall is designed like biological memory:
- **Memories form** through attention and importance, or automatically via LLM signal detection
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
│  │   - Ingest      │     │  - Patterns     │               │
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
│  ┌──────────────┐  ┌──────────────────────┐               │
│  │ MEMORY TYPES │  │    SIGNAL BRAIN      │               │
│  │  Episodic    │  │  LLM-powered auto    │               │
│  │  Semantic    │  │  memory from convos  │               │
│  │  Procedural  │  │  (qwen3:14b/Ollama)  │               │
│  └──────────────┘  └──────────────────────┘               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Features

### Semantic Understanding
- **BGE-large embeddings** (1024 dimensions) via Ollama
- True similarity search, not keyword matching
- Understanding of meaning, not just words

### Automatic Memory Formation (Signal Detection Brain)
- Ingest conversation turns via `POST /ingest/turns`
- LLM (qwen3:14b) analyzes conversations for important signals
- Auto-stores high-confidence signals as memories (error fixes, facts, decisions, workflows)
- Medium-confidence signals queued for human review
- Content-hash deduplication prevents duplicate memories

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
- **Consolidation** - merges similar memories (hourly)
- **Pattern extraction** - learns from episodes (daily)
- **Decay** - applies forgetting curve (every 30 min)

### Security
- **Bearer token auth** - optional API key via `RECALL_API_KEY`
- **Error sanitization** - internal details never leaked to clients
- **Input validation** - content length, turn count, and field size limits
- **Configurable CORS** - restrict origins via `RECALL_ALLOWED_ORIGINS`

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Ollama running somewhere on your network with `bge-large` and `qwen3:14b` models

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
# Pull required models
ollama pull bge-large
ollama pull qwen3:14b

# Edit docker-compose.yml to set your RECALL_OLLAMA_HOST
# Then start the stack
docker compose up -d

# Check health
curl http://localhost:8200/health
```

### Enable Authentication (Recommended)

By default, auth is disabled for easy development. To secure your instance:

```bash
# On your server, create a .env file with your API key
echo "RECALL_API_KEY=your-secret-key-here" >> /path/to/Recall/.env

# Restart the API to pick up the key
docker compose up -d api
```

Once enabled:
- All endpoints except `/health` require `Authorization: Bearer <key>`
- `/health` remains public for monitoring
- The startup log will show `auth_enabled=True`

Generate a strong key:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### First Memory

```bash
# Without auth:
curl -X POST http://localhost:8200/memory/store \
  -H "Content-Type: application/json" \
  -d '{
    "content": "JWT tokens should use 24h expiry for this project",
    "memory_type": "semantic",
    "domain": "auth",
    "tags": ["jwt", "security"]
  }'

# With auth:
curl -X POST http://localhost:8200/memory/store \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-secret-key-here" \
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
      "RECALL_HOST": "http://YOUR_SERVER:8200",
      "RECALL_API_KEY": "your-secret-key-here"
    }
  }
}
```

> **Note:** If auth is disabled (no `RECALL_API_KEY` set on the server), you can omit the `RECALL_API_KEY` env var from the MCP config.

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
| `recall_ingest` | Ingest conversation turns for auto signal detection |

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

**Authentication:** If `RECALL_API_KEY` is set, all endpoints except `/health` require:
```
Authorization: Bearer <your-api-key>
```

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

| Field | Type | Default | Limits | Description |
|-------|------|---------|--------|-------------|
| `content` | string | *required* | 1-50,000 chars | The memory content |
| `memory_type` | enum | `semantic` | | `semantic`, `episodic`, or `procedural` |
| `source` | enum | `user` | | `user`, `system`, `observation`, `inference` |
| `domain` | string | `general` | max 200 chars | Project/topic domain for filtering |
| `tags` | string[] | `[]` | max 50 tags | Tags for categorization |
| `importance` | float | `0.5` | 0.0-1.0 | Higher = slower decay |
| `confidence` | float | `0.8` | 0.0-1.0 | Certainty of information |
| `session_id` | string? | `null` | | Links memory to a session's working memory |
| `metadata` | object | `{}` | | Arbitrary metadata |

**Response:**
```json
{
  "id": "uuid",
  "content_hash": "hex-hash",
  "created": true,
  "message": "Memory stored successfully"
}
```

Duplicate content (same content hash) returns `created: false` with the existing ID.

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

Relationship types: `related_to`, `caused_by`, `solved_by`, `supersedes`, `derived_from`, `contradicts`, `requires`, `part_of`

#### `GET /memory/{id}/related`
Get memories connected via graph traversal.

Query params: `max_depth` (1-10, default 2), `limit` (1-100, default 10)

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

### Conversation Ingestion (Signal Detection)

#### `POST /ingest/turns`
Ingest conversation turns for automatic signal detection. The LLM analyzes turns in the background and auto-stores important signals as memories.

**Request:**
```json
{
  "session_id": "uuid",
  "turns": [
    {"role": "user", "content": "How do I fix Docker permissions?"},
    {"role": "assistant", "content": "Run: sudo chmod 666 /var/run/docker.sock"}
  ]
}
```

| Field | Limits |
|-------|--------|
| `turns` | 1-50 per request |
| `turn.content` | 1-50,000 chars |
| `turn.role` | max 20 chars |

**Response:**
```json
{
  "session_id": "uuid",
  "turns_ingested": 2,
  "total_turns": 2,
  "detection_queued": true
}
```

Signal confidence thresholds:
- **>= 0.75**: Auto-stored as memory
- **0.4 - 0.75**: Added to pending queue for review
- **< 0.4**: Discarded

#### `GET /ingest/{session_id}/signals`
Get pending signals (medium confidence) awaiting review.

#### `POST /ingest/{session_id}/signals/approve`
Approve a pending signal, storing it as a memory.

#### `GET /ingest/{session_id}/turns`
Get stored turns for a session (debug/inspection).

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

Ending a session cleans up pending signals and optionally triggers consolidation of session memories.

#### `GET /session/{id}` - Session status
#### `GET /session/{id}/working-memory` - Working memory contents
#### `POST /session/{id}/context` - Update session context

### Admin

#### `POST /admin/consolidate`
Trigger memory consolidation on-demand. Finds clusters of similar memories and merges them.

```json
{
  "domain": null,
  "memory_type": null,
  "min_cluster_size": 2,
  "dry_run": false
}
```

#### `POST /admin/decay`
Trigger importance decay on-demand.

```json
{
  "simulate_hours": 0.0
}
```

### System

#### `GET /health`
Returns health status of all services (API, Qdrant, Neo4j, Redis, Ollama) with memory/node/model counts. **Always public** (no auth required).

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

All storage ports are bound to `127.0.0.1` only (not exposed to network).

---

## Configuration

All configuration is via environment variables (prefix `RECALL_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `RECALL_ENV` | `development` | Environment mode |
| `RECALL_API_KEY` | *(empty)* | API key for bearer auth (empty = auth disabled) |
| `RECALL_ALLOWED_ORIGINS` | `*` | Comma-separated CORS origins |
| `RECALL_OLLAMA_HOST` | `http://192.168.50.62:11434` | Ollama API endpoint |
| `RECALL_EMBEDDING_MODEL` | `bge-large` | Ollama embedding model |
| `RECALL_EMBEDDING_DIMS` | `1024` | Embedding dimensions |
| `RECALL_SIGNAL_DETECTION_MODEL` | `qwen3:14b` | LLM for signal detection |
| `RECALL_SIGNAL_CONFIDENCE_AUTO_STORE` | `0.75` | Auto-store threshold |
| `RECALL_SIGNAL_CONFIDENCE_PENDING` | `0.4` | Pending queue threshold |
| `RECALL_MAX_CONTENT_LENGTH` | `50000` | Max chars for content fields |
| `RECALL_MAX_TURNS_PER_REQUEST` | `50` | Max turns per ingest request |
| `RECALL_QDRANT_HOST` | `qdrant` | Qdrant hostname |
| `RECALL_QDRANT_PORT` | `6333` | Qdrant port |
| `RECALL_NEO4J_URI` | `bolt://neo4j:7687` | Neo4j connection |
| `RECALL_NEO4J_USER` | `neo4j` | Neo4j username |
| `RECALL_NEO4J_PASSWORD` | `recallmemory` | Neo4j password |
| `RECALL_REDIS_URL` | `redis://redis:6379` | Redis connection |
| `RECALL_POSTGRES_DSN` | *(see docker-compose)* | PostgreSQL DSN |

---

## Memory Types

| Type | Use For | Examples |
|------|---------|---------|
| **semantic** | Facts, concepts, relationships | "The API uses JWT auth with 24h expiry" |
| **episodic** | Events, experiences, sessions | "Fixed the UUID collision bug on 2026-02-14" |
| **procedural** | How-to, workflows, processes | "To deploy: run tests, build container, push to registry" |

---

## Background Workers

Workers run on a cron schedule via ARQ:

| Worker | Schedule | Description |
|--------|----------|-------------|
| Consolidation | Every hour at :00 | Merges similar memories, boosts stability |
| Decay | Every 30 min at :15/:45 | Reduces importance of unaccessed memories |
| Pattern extraction | Daily at 3:30 AM | Finds recurring patterns in episodic memories |

Consolidation uses a lock to prevent overlapping runs. All workers use `scroll_all()` for unbiased batch processing.

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
# All tests (requires live API at http://192.168.50.19:8200)
pytest tests/integration/ -v

# Fast tests only (no LLM calls)
pytest tests/integration/ -v -m "not slow"

# Slow tests (signal detection, consolidation — requires Ollama)
pytest tests/integration/ -v -m "slow"

# With auth enabled, set the key:
RECALL_API_KEY=your-key pytest tests/integration/ -v
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

# Restart API after code changes (volumes mount ./src)
docker compose restart api

# Shell into API container
docker compose exec api /bin/bash

# Full rebuild (needed for dependency changes)
docker compose down && docker compose build && docker compose up -d
```

### Deploy changes without rebuild
Source code is volume-mounted (`./src:/app/src`), so:
```bash
# Copy changed files and restart
scp src/path/to/file.py server:/path/to/Recall/src/path/to/file.py
ssh server "cd /path/to/Recall && docker compose restart api worker"
```

---

## Data Consistency

Recall uses dual-write to Qdrant (vectors) and Neo4j (graph). On Neo4j write failure, a compensating delete removes the Qdrant record to prevent orphaned data. This applies to all write paths: store, consolidation merge, signal auto-store, signal approval, and pattern extraction.

Superseded memories (merged during consolidation) are marked in both stores and filtered from graph traversal queries.

---

## Project Status

Active development. Current state:

- [x] Core API (store, search, context, sessions)
- [x] Vector storage (Qdrant) with content-hash deduplication
- [x] Graph storage (Neo4j) with parameterized Cypher queries
- [x] Cache & sessions (Redis) with SCAN-based counting
- [x] Background workers (decay, consolidation, patterns)
- [x] Signal detection brain (auto-memory from conversations)
- [x] Docker Compose deployment
- [x] Deploy scripts (bash + PowerShell)
- [x] MCP server for Claude Code
- [x] Integration tests (111 tests: 82 fast + 29 slow/LLM)
- [x] Bearer token authentication
- [x] Error sanitization
- [x] Input validation & CORS lockdown
- [x] Dual-write consistency (compensating deletes)
- [ ] LLM-powered consolidation (smarter merges)
- [ ] Prometheus metrics
- [ ] Backup/export/import
- [ ] Admin dashboard

## License

MIT
