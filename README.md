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
│  ┌─────────────────┐     ┌─────────────────┐                │
│  │   API (FastAPI) │     │  Workers (ARQ)  │                │
│  │   - Store       │     │  - Consolidate  │                │
│  │   - Retrieve    │     │  - Decay        │                │
│  │   - Search      │     │  - Extract      │                │
│  └────────┬────────┘     └────────┬────────┘                │
│           │                       │                         │
│           └───────────┬───────────┘                         │
│                       │                                     │
│  ┌────────────────────┴────────────────────┐                │
│  │              STORAGE LAYER              │                │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ │                │
│  │  │  Qdrant  │ │  Neo4j   │ │  Redis   │ │                │
│  │  │ (vectors)│ │ (graph)  │ │ (cache)  │ │                │
│  │  └──────────┘ └──────────┘ └──────────┘ │                │
│  └─────────────────────────────────────────┘                │
│                                                             │
│  ┌─────────────────────────────────────────┐                │
│  │            MEMORY TYPES                 │                │
│  │  Episodic  │  Semantic  │  Procedural   │                │
│  │  (events)  │  (facts)   │  (workflows)  │                │
│  └─────────────────────────────────────────┘                │
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

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Ollama with `bge-large-en-v1.5` model

### Pull the embedding model
```bash
ollama pull bge-large-en-v1.5
```

### Start the stack
```bash
docker-compose up -d
```

### Check health
```bash
curl http://localhost:8100/health
```

### Store a memory
```bash
curl -X POST http://localhost:8100/memory/store \
  -H "Content-Type: application/json" \
  -d '{
    "content": "JWT tokens should use 24h expiry for this project",
    "memory_type": "semantic",
    "domain": "auth",
    "tags": ["jwt", "security"]
  }'
```

### Search memories
```bash
curl -X POST http://localhost:8100/search/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the token configuration?",
    "limit": 5
  }'
```

## API Endpoints

### Memory Operations
- `POST /memory/store` - Store a new memory
- `GET /memory/{id}` - Get a memory
- `DELETE /memory/{id}` - Delete a memory
- `POST /memory/relationship` - Create relationship

### Search & Retrieval
- `POST /search/query` - Semantic search
- `POST /search/context` - Assemble context for injection
- `GET /search/similar/{id}` - Find similar memories

### Sessions
- `POST /session/start` - Start a session
- `POST /session/end` - End a session
- `GET /session/{id}` - Get session status
- `GET /session/{id}/working-memory` - Get working memory

### System
- `GET /health` - Health check
- `GET /stats` - System statistics

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| RECALL_ENV | development | Environment mode |
| QDRANT_HOST | localhost | Qdrant host |
| QDRANT_PORT | 6333 | Qdrant port |
| NEO4J_URI | bolt://localhost:7687 | Neo4j connection |
| REDIS_URL | redis://localhost:6380 | Redis connection |
| OLLAMA_HOST | http://localhost:11434 | Ollama API |
| EMBEDDING_MODEL | bge-large-en-v1.5 | Embedding model |

## Development

### Install dependencies
```bash
pip install -e ".[dev]"
```

### Run tests
```bash
pytest
```

### Run API locally
```bash
uvicorn src.api.main:app --reload --port 8100
```

### Run worker locally
```bash
arq src.workers.main.WorkerSettings
```

## Project Status

🚧 **Work in Progress**

This is an active development project. Current focus:
- [ ] Core API stabilization
- [ ] Integration tests
- [ ] Claude Code integration
- [ ] Production hardening

## License

MIT
