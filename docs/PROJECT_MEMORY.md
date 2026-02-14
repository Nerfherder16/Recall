# Project Memory - Recall

This document serves as persistent memory for Claude sessions working on this project.

## Project Overview

**Recall** is a living memory system for AI assistants. It replaces simple keyword storage with semantic understanding, memory dynamics, and graph relationships.

## Architecture Decisions

### Storage Layer
- **Qdrant** for vectors (not pgvector) - faster, purpose-built
- **Neo4j** for relationships - mature graph database
- **Redis** for cache/events - working memory + pub/sub
- **PostgreSQL** for metadata (future) - audit trails

### Embedding Model
- **BGE-large-en-v1.5** via Ollama
- 1024 dimensions (not 768 like nomic)
- Better retrieval quality for our use case
- Query prefix: "Represent this sentence for searching relevant passages: "

### Memory Types
1. **Episodic** - Events, time-bound experiences
2. **Semantic** - Facts, timeless knowledge
3. **Procedural** - Workflows, action sequences
4. **Working** - Session context, volatile

### Key Concepts
- **Importance**: Dynamic score, decays over time
- **Stability**: Resistance to decay, increases with consolidation
- **Confidence**: How certain we are of the information
- **Reinforcement**: Access increases importance

## File Structure

```
src/
├── api/           # FastAPI application
│   ├── main.py    # App entry point
│   └── routes/    # API endpoints
├── core/          # Domain models and services
│   ├── models.py  # Memory, Relationship, etc.
│   ├── embeddings.py  # BGE-large via Ollama
│   ├── retrieval.py   # Multi-stage retrieval pipeline
│   └── consolidation.py  # Memory merging
├── storage/       # Storage adapters
│   ├── qdrant.py  # Vector store
│   ├── neo4j_store.py  # Graph store
│   └── redis_store.py  # Cache + events
└── workers/       # Background jobs
    ├── main.py    # ARQ worker config
    ├── decay.py   # Importance decay
    └── patterns.py  # Pattern extraction
```

## API Ports
- **8100**: Recall API (mapped from container 8000)
- **6333**: Qdrant
- **7474/7687**: Neo4j (HTTP/Bolt)
- **5433**: PostgreSQL
- **6380**: Redis

## Current Status

### Completed
- [x] Core models (Memory, Relationship, Session, etc.)
- [x] Storage layer (Qdrant, Neo4j, Redis adapters)
- [x] Embedding service (BGE-large via Ollama)
- [x] Retrieval pipeline (vector + graph + context)
- [x] Consolidation service
- [x] API routes (memory, search, session)
- [x] Background workers (decay, patterns)
- [x] Docker Compose setup

### TODO
- [ ] Integration tests
- [ ] Signal detection (auto-save from conversation)
- [ ] Negative space (anti-patterns)
- [ ] Claude Code MCP integration
- [ ] Production config (secrets, scaling)
- [ ] Monitoring (Prometheus/Grafana)

## Key Formulas

### Decay
```python
effective_decay = base_decay * (1 - stability)
new_importance = importance * (1 - effective_decay) ** hours_since_access
```

### Retrieval Score
```python
score = similarity * importance * recency_factor * stability_factor * confidence_factor
```

### Consolidation Threshold
- Similarity >= 0.85 triggers potential merge
- Min cluster size: 2 memories

## Common Commands

```bash
# Start stack
docker-compose up -d

# Check logs
docker-compose logs -f api

# Run API locally
uvicorn src.api.main:app --reload --port 8100

# Run worker locally
arq src.workers.main.WorkerSettings

# Pull embedding model
ollama pull bge-large-en-v1.5
```

## Integration Points

### Claude Code
- MCP server wrapping the Recall API
- Auto-inject context on each message
- Auto-save signals from conversation
- Session management per Claude Code session

### FamilyHub
- Could share memory infrastructure
- Different domains: "work" vs "family"
- Same embedding model

## Notes for Future Sessions

1. **Ollama Host**: When running in Docker, use `host.docker.internal:11434` to reach host Ollama
2. **Neo4j Auth**: Default `neo4j/recallmemory`
3. **BGE Prefixes**: Use "query" prefix for searches, no prefix for stored content
4. **Working Memory Limit**: Default 20 items per session
