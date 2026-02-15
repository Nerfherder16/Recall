# Recall Roadmap

## Completed Phases

### Phase 1: API Hardening & Foundation
- Admin endpoints, input validation, 16 integration tests
- **Audit**: scroll_all(), content_hash dedup, Cypher fix, cron staggering

### Phase 2: Signal Detection Brain (commit 33b1efb)
- Auto-memory from conversation via LLM signal detection
- **Audit**: 3-agent audit identified 27 issues across security/architecture/edge cases

### Phase 3: Hardening & Correctness (commit ec91efd)
- Fixed 10 issues: C1-C4, I1-I2, I4-I8
- _track_access persistence, scroll_all() for decay/consolidation, Cypher f-string fixes

### Phase 4: Event System & Session Lifecycle
- Fixed 4 issues: I3, I9, I11, N8
- Session end consolidation, pending signal cleanup, turn ordering

### Phase 5: Security & Access Control
- Auth (C5), error sanitization (I12), input validation (N6 partial), CORS (N10)
- Bearer token auth on all endpoints except /health and /metrics

### Phase 6: Smarter Memory Formation
- LLM consolidation merge, LLM pattern extraction
- Contradiction resolution, MCP session tools

### Phase 7: Observability & Operations
- JSONL export/import, reconcile (found 6 real Qdrant/Neo4j mismatches)
- Prometheus metrics endpoint, in-memory MetricsCollector
- Dashboard (HTML/JS single-page app)
- Instrumentation across LLM, embeddings, signals, workers

### PostgreSQL Integration
- Audit log: all 6 mutation paths (create, delete, supersede, consolidate, decay, signal)
- Session archive: persisted on session end (survives Redis TTL)
- Metrics snapshots: hourly cron at :30
- Endpoints: GET /admin/audit, GET /admin/sessions
- 7 integration tests (98 fast total, 127 including slow/LLM)

### Phase 8: Quality of Life + Operational Hardening + Dashboard
- **N2**: Batch store/delete endpoints (POST /memory/batch/store, POST /memory/batch/delete)
- **N3**: Date-range search (since/until filters via Qdrant DatetimeRange)
- **N5**: Rate limiting (slowapi — 60/min default, 30/min search, 20/min ingest, 10/min admin)
- **N7**: Per-domain statistics (GET /stats/domains)
- **N9**: Graceful Ollama degradation (OllamaUnavailableError → 503 on API, log+skip in workers)
- Dashboard: audit log viewer, session history, memory search, signal review
- 11 new integration tests (109 fast total, 138 including slow/LLM)

---

## Open Issues

### Infrastructure
| ID | Priority | Description | Notes |
|----|----------|-------------|-------|
| I10 | Medium | No backup/restore strategy | Export/import exists but no scheduled backups |

### Nice-to-Have
| ID | Priority | Description | Notes |
|----|----------|-------------|-------|
| N1 | Low | Memory versioning (track content changes) | Audit log partially covers this now |
| N4 | Low | Configurable LLM prompts (externalize) | Currently hardcoded in detector/consolidator |

---

## Phase 9 Options (Not Yet Started)

### Option A: Backup & Resilience
- Scheduled Qdrant snapshots + Neo4j dump
- Offsite backup to external storage
- Restore verification testing
- Closes I10

### Option B: MCP Client Enhancement
- Richer context assembly for Claude Code
- Better working memory management
- Cross-session memory continuity

---

## Architecture Reference

```
Client (Claude Code / MCP)
    │
    ▼
FastAPI API (:8200)
    ├── /memory/*     — CRUD + relationships
    ├── /search/*     — semantic + graph search
    ├── /session/*    — session lifecycle
    ├── /ingest/*     — turn ingestion + signal detection
    ├── /admin/*      — export, import, reconcile, audit, sessions
    ├── /health       — public health check
    ├── /metrics      — Prometheus format
    ├── /stats        — system statistics
    └── /dashboard    — ops dashboard (HTML)
    │
    ▼
Storage Layer
    ├── Qdrant        — vector store (source of truth for memories)
    ├── Neo4j         — graph store (relationships, traversal)
    ├── Redis         — volatile (sessions, working memory, turns, cache)
    └── PostgreSQL    — durable metadata (audit log, session archive, metrics)
    │
    ▼
ARQ Worker (background jobs)
    ├── Consolidation — hourly at :00
    ├── Decay         — every 30min at :15/:45
    ├── Metrics       — hourly at :30
    └── Patterns      — daily at 3:30am
    │
    ▼
Ollama (192.168.50.62:11434)
    ├── qwen3:14b     — LLM (signals, consolidation, patterns)
    └── bge-large     — embeddings (1024 dims)
```
