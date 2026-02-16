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

### Phase 9: Claude-Pilot Patterns
- **3-Layer Search**: browse (120-char summaries) → get (full detail) → timeline (chronological)
- **Sub-embeddings**: `recall_memories_facts` Qdrant collection, parent_id linked, 1.15x score boost
- **Observer**: PostToolUse hook → POST /observe/file-change → LLM fact extraction → auto-store
- **Hooks** (all CommonJS, in `hooks/`): lint-check, observe-edit, context-monitor, session-save, stop-guard
- **Dashboard**: React+Vite+Tailwind+DaisyUI SPA at `dashboard/`, builds to `src/api/static/dashboard/`
- **SSE**: GET /events/stream for real-time dashboard updates
- **MCP tools**: recall_search → browse, recall_search_full → full content, recall_timeline → chronological
- 10 new integration tests (119 fast total, 148 including slow/LLM)

### Phase 10: Dashboard Redesign
- **Collapsible sidebar**: 224px ↔ 64px, persisted to localStorage, mobile overlay at <768px
- **Dark/light theme**: DaisyUI `data-theme` swap, init script prevents flash, persisted
- **Toast notifications**: success/error/info, auto-dismiss 3s, bottom-right fixed stack
- **Memories**: auto-browse on mount, grid/list toggle, bulk select+delete, detail modal
- **Sessions**: expandable cards with vertical turn timeline (lazy-loads turns)
- **Audit**: auto-load on mount, null-safe `details` field, relative timestamps, badge formatting
- **Signals**: session dropdown, auto-load on select
- **Settings**: maintenance ops (consolidation/decay/reconcile/export), theme toggle
- **LLM panel**: GET /admin/ollama proxies Ollama API, shows model table + running model cards
- **SSE reconnect fix**: mountedRef + recursive connect()
- **Simulation**: `tests/simulation/build_hub_sim.py` — 1-hour, 5-agent stress test (commit dc1051a)

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

## Phase 11: Organic Memory Hooks — COMPLETE (commit 80718bd + 5e3c448)
- **recall-retrieve.js** (UserPromptSubmit): queries /search/browse, injects top 5 memories, project affinity via [projectName] prefix
- **recall-session-summary.js** (Stop): reads transcript JSONL, stores episodic summary with project domain/tags
- **observe-edit.js** (PostToolUse): already existed — extracts facts from file edits
- Closed the retrieval loop — no CLAUDE.md instructions needed

---

## Phase 12: Neural Memory — COMPLETE (commit ce48382)
- **12A: Spreading Activation** (Collins & Loftus, 1975): Graph expansion now propagates weighted activation through edges using relationship `strength` field. `child_activation = parent_activation * edge_strength * decay`. Replaces flat `importance / (1 + distance * 0.3)` penalty. Neo4j `find_related()` returns `rel_strengths`. Activation threshold at 0.05.
- **12B: Interference / Inhibition**: New Stage 5.5 in retrieval pipeline. CONTRADICTS edges between results cause 0.7x penalty on lower-scored memory. Near-duplicates (same content_hash) fully suppressed. New `find_contradictions()` method in Neo4j store.
- **12C: Core Memory Auto-Elevation**: Signal detector prompt updated with 1-10 poignancy scale (Stanford Generative Agents inspired). LLM-scored importance maps to 0.0-1.0, preferred over flat `SIGNAL_IMPORTANCE` dict. `DetectedSignal.suggested_importance` field added. Workers and ingest route use LLM importance with type-based fallback.

---

## Phase 13: Multi-User Support — COMPLETE (commit 8aa7f73)
- **Per-user API keys**: PostgreSQL `users` table (username, api_key, display_name, is_admin, last_active_at). Keys auto-generated with `rc_` prefix.
- **Auth middleware**: Extracted to `src/api/auth.py`. Resolves Bearer token → User object. Check order: (1) auth disabled → None, (2) RECALL_API_KEY → system admin User(id=0), (3) users table lookup → User(id=N), (4) reject 401. Backward compatible — existing master key still works.
- **User attribution**: Memory model gains `user_id`/`username` (nullable for legacy data). Stored in Qdrant payload (with indexes), Neo4j node properties, and audit log.
- **Admin endpoints**: `POST /admin/users` (create, returns one-time API key), `GET /admin/users` (list without keys), `DELETE /admin/users/{id}` (remove user, memories stay).
- **Search filtering**: `user` param on SearchRequest filters by username via Qdrant FieldCondition. `stored_by` field added to BrowseResult, SearchResult, TimelineEntry, MemoryResponse.
- **Dashboard**: Users page (create/list/delete with API key reveal modal), `stored_by` badges on memory cards (grid + list views), user filter dropdown on Memories page, "Users" link in sidebar.
- **Migration**: Idempotent — `CREATE TABLE IF NOT EXISTS` for users table, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for audit_log.user_id. No data migration needed.
- **Shared visibility by default**: All users see all memories; `user` filter is optional.

---

## Deferred (Post Phase 12 Evaluation)

### Prospective Memory Triggers
- "When condition X is met, surface memory Y"
- May be solved by spreading activation — evaluate after Phase 12

### Encoding Context Snapshots
- Store full encoding context (project, files, task, working memory IDs)
- Match retrieval context to encoding context for boost
- Marginal improvement over existing context boosting

### Schema Formation
- Hierarchical abstraction: facts → concepts → principles → mental models
- High value but needs spreading activation foundation first

---

## Future: Research-Backed Enhancements

### From Stanford Generative Agents
- **Reflections**: Periodically synthesize higher-order insights from recent memories ("I notice that every time I work on Recall, I encounter Qdrant API issues"). Store as first-class memories. Triggered when cumulative importance exceeds threshold.
- **Three-factor retrieval**: `score = α*recency + β*importance + γ*similarity` (partially implemented)

### From mem0
- **Four-operation consolidation**: LLM chooses ADD/UPDATE/DELETE/NOOP per fact against existing memories (more precise than current merge-all)
- **Custom extraction prompts with few-shot examples**: Domain-specific prompts dramatically improve extraction precision

### From Zep/Graphiti
- **Bi-temporal invalidation**: Never delete, mark invalid with timestamps. Enables "what did we know at time T?" queries
- **Extraction reflection**: LLM reviews its own entity extractions before committing (reduces hallucinated facts)
- **BM25 + vector search with RRF fusion**: Catches keyword matches that vectors miss

### From HyDE
- **Hypothetical Document Embeddings**: For vague queries, generate a hypothetical answer first, embed that. Bridges the query-document embedding gap. Use selectively when initial search returns low-confidence results.

### From A-MEM (Zettelkasten-inspired)
- **Memory evolution**: When new memories link to old ones, LLM enriches the old memory's context. Not replacing — evolving.
- **Validated with Ollama**: 1.1s per operation with 1B model locally. Feasible for real-time use.

### From GraphRAG
- **Community/cluster summaries**: Run Leiden clustering on Neo4j, pre-generate summaries per cluster. Enables "what do I know about X?" without scanning all memories.

### Problem
Recall's storage side works (observer hooks extract facts from file edits), but the **retrieval side is broken** — nothing queries Recall before the agent starts working. Phase 10's simulation generated 85 memories about Build Hub architecture, but when actually building Build Hub Desktop, none were retrieved. Memory is useless if it's never consulted.

### Solution: Close the Retrieval Loop

```
User types message
       ↓
[UserPromptSubmit hook]  ← NEW (recall-retrieve.js)
  → queries Recall: POST /search/browse with user's message
  → outputs top 3-5 relevant memories as context
  → agent sees them naturally in conversation
       ↓
Agent works (edits files)
       ↓
[PostToolUse hook]  ← EXISTS (observe-edit.js)
  → extracts facts from file changes
  → stores to Recall
       ↓
[Stop hook]  ← NEW (recall-session-summary.js)
  → summarizes what was built/fixed in the session
  → stores to Recall for next-session continuity
```

### Files to Create/Modify
1. **`hooks/recall-retrieve.js`** — UserPromptSubmit hook
   - Reads user's message from stdin
   - POST /search/browse with message as query, limit=5
   - Outputs formatted memories to stdout (Claude sees as context)
   - Filters by relevance score threshold (>0.3)
   - Fast path: skip if message is very short (<10 chars) or a greeting

2. **`hooks/recall-session-summary.js`** — Stop hook
   - Reads conversation transcript or last N messages
   - Generates a 2-3 sentence summary of what was accomplished
   - POST /memory/store with domain="work", source="system"
   - Includes project path and key decisions made

3. **`~/.claude/settings.json`** — Add UserPromptSubmit hook config
   - Point to recall-retrieve.js for all user messages
   - Point to recall-session-summary.js for Stop events

### Success Criteria
- Opening a new Claude Code session about a previously-discussed project should automatically surface relevant memories
- No CLAUDE.md instructions needed — hooks handle everything
- Latency budget: <500ms for retrieval (browse endpoint is fast)
- No false positives on greetings or trivial messages

---

## Architecture Reference

```
Claude Code Hooks (client-side)
    ├── UserPromptSubmit → recall-retrieve.js (query memories)     ← Phase 11
    ├── PostToolUse      → observe-edit.js (extract & store facts)  ← Phase 9
    └── Stop             → recall-session-summary.js (store summary) ← Phase 11
    │
    ▼
Client (Claude Code / MCP)
    │
    ▼
FastAPI API (:8200)
    ├── /memory/*     — CRUD + relationships + batch ops
    ├── /search/*     — browse (summaries) / full / timeline
    ├── /session/*    — session lifecycle
    ├── /ingest/*     — turn ingestion + signal detection
    ├── /observe/*    — file-change observer (fact extraction)
    ├── /admin/*      — export, import, reconcile, audit, sessions, ollama, users
    ├── /events/*     — SSE stream for dashboard
    ├── /health       — public health check
    ├── /metrics      — Prometheus format
    ├── /stats        — system + domain statistics
    └── /dashboard    — React SPA (DaisyUI)
    │
    ▼
Storage Layer
    ├── Qdrant        — vector store (memories + sub-embeddings/facts)
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
    ├── qwen3:14b     — LLM (signals, consolidation, patterns, fact extraction)
    └── bge-large     — embeddings (1024 dims)
```
