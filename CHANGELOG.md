# Changelog

All notable changes to Recall are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/). Most recent first.

---

## v2.9.6 — Bug Hunt: 23 Bugs Fixed (2026-02-20)

### Summary
Full systems audit found 23 bugs (3 CRITICAL, 5 HIGH, 8 MEDIUM, 7 LOW). All actionable bugs fixed. Dead code audit also removed 408 lines across 13 files.

### CRITICAL Fixes
- **patterns.py**: Division by zero in `_cosine_similarity` when vector norm is 0
- **memory.py**: Batch delete didn't clean up facts sub-embeddings (single delete did)
- **documents.py**: Document pin/unpin propagated to Qdrant but skipped Neo4j Memory nodes

### HIGH Fixes
- **All 4 storage singletons** (qdrant, neo4j, redis, postgres): Added `asyncio.Lock` double-checked locking to prevent race conditions during concurrent init
- **retrieval.py**: `_payload_to_memory` never set `metadata` field — broke document-sibling boost entirely (document_id always None)
- **events.py**: SSE error events leaked internal exception details to clients
- **health.py**: `compute_forces` return type annotation was wrong (`dict` vs `dict | None`)
- **neo4j_documents.py**: `update_document` used f-string interpolation for field names — added `_ALLOWED_FIELDS` whitelist

### MEDIUM Fixes
- **mcp-server/index.js**: Default RECALL_HOST was `localhost:8200` (unreachable) — matched to hooks' default `192.168.50.19:8200`
- **redis_store.py**: `get_active_sessions` counted ended sessions — now checks `ended_at` via pipeline
- **observe-edit.js**: Write content >10KB was silently dropped — now truncated with flag

### LOW Fixes
- **decay.py**: Single bad memory (e.g., invalid datetime) aborted entire decay run — wrapped loop body in try/except
- **retrieval.py**: `_track_access` mutated returned Memory objects via background task (race condition) — now uses local copies
- **context-monitor.js**: Output format missing `hookSpecificOutput` wrapper — context was silently ignored

### By Design (Not Fixed)
- #10 (default credentials): Dev defaults, overridden by env vars in production
- #12 (readStdin timeout): Returns partial data by design for non-blocking hooks
- #13 (session-summary timeout): Key decisions are fire-and-forget; summary completes before 10s
- #14 (consolidation lock): Single-process deployment doesn't need distributed locks
- #17 (checkpoint feedback dupes): Each checkpoint is an independent signal
- #22 (CORS wildcard): Configurable via env var; `*` is appropriate for self-hosted homelab

### Dead Code Removed (408 lines across 13 files)
- Unused imports, unreachable branches, commented-out code, dead helper functions
- See commit for full diff

### Files Changed
- `src/workers/patterns.py`, `src/api/routes/memory.py`, `src/api/routes/documents.py`
- `src/storage/qdrant.py`, `src/storage/neo4j_store.py`, `src/storage/redis_store.py`, `src/storage/postgres_store.py`
- `src/core/retrieval.py`, `src/core/health.py`, `src/api/routes/events.py`
- `src/storage/neo4j_documents.py`, `src/workers/decay.py`
- `hooks/observe-edit.js`, `hooks/context-monitor.js`, `mcp-server/index.js`

---

## v2.9.5 — Fix Stale Package Shadowing Worker (2026-02-20)

### Problem
ARQ worker `run_decay` and `run_consolidation` crashed every cycle with `3 validation errors for MatchValue` (value=None). Manual Python runs succeeded but cron-triggered runs consistently failed. Logs also showed `pulling_embedding_model model=bge-large` despite settings using `qwen3-embedding:0.6b`.

### Root Cause
The Dockerfile's `pip install --no-cache-dir .` installed the `recall` package into `/usr/local/lib/python3.11/site-packages/src/`. This stale copy — baked into the Docker image at build time — shadowed the volume-mounted `/app/src/` for the ARQ worker process. The old code had MatchValue(value=None) bugs and `bge-large` as the default embedding model. All source edits deployed via SCP + restart were invisible to the worker because it imported from site-packages.

### Fixed
- **Dockerfile**: Changed `RUN pip install --no-cache-dir .` to `RUN pip install --no-cache-dir . && pip uninstall -y recall` — installs dependencies but removes the package itself so site-packages never shadows the volume mount.
- **Running containers**: Ran `pip uninstall recall -y` as root on both worker and API containers.
- **Cleaned up debug instrumentation**: Removed MatchValue monkey-patch, marker file writes, and pathlib import from `src/workers/main.py`.

### Result
- Decay: processed 1287 memories, decayed 761 — first successful cron run in production.
- Consolidation: 51 clusters merged, 135 memories consolidated.
- Correct embedding model (`qwen3-embedding:0.6b`) now used.

### Files Changed
- `Dockerfile` — `pip uninstall -y recall` after install
- `src/workers/main.py` — removed debug instrumentation

---

## v2.9.4 — Fix Feedback Loop (2026-02-20)

### Problem
Session feedback never reached Recall. All hooks had `localhost:8200` as fallback default, but Recall runs on CasaOS (`192.168.50.19:8200`). The `settings.json` `env` block sets the correct host, but environment variable inheritance to hooks is unreliable on Windows. The session-summary hook also had a 10s timeout — too tight for feedback + LLM summary + decision extraction (~60s total).

### Fixed
- **All 6 hooks** now hardcode correct defaults: `RECALL_HOST=http://192.168.50.19:8200`, `RECALL_API_KEY=recall-admin-key-change-me`, `OLLAMA_HOST=http://192.168.50.62:11434`
- **Session-summary timeout** bumped from 10s to 30s in `settings.json`
- **Feedback + summary run in parallel** (was serial) — saves ~8s
- **Decision extraction** runs fire-and-forget (doesn't block hook exit)
- **Debug logging** added to session-summary hook: `~/.cache/recall/session-summary-debug.log`

### Hooks Fixed
- `hooks/recall-retrieve.js`
- `hooks/recall-session-summary.js`
- `hooks/observe-edit.js`
- `hooks/session-save.js`
- `hooks/recall-statusline.js`
- `hooks/git-watch.js`

---

## v2.9.3 — Smarter Memory Capture (2026-02-20)

### Problem
High-value changes (config edits, troubleshooting fixes, hook optimizations) weren't being captured by the observer because it treated all files equally and the session-summary hook compressed everything into one episodic blob.

### Added
- **High-value file detection** (`observe-edit.js`): Config files, hooks, docker-compose, Dockerfiles, settings, and CI/CD pipelines are flagged as `high_value: true`.
- **Enhanced observer prompt** (`observer.py`): High-value files get a richer LLM prompt asking for impact, root cause, and troubleshooting context. Default importance boosted from 0.4 to 0.6.
- **Session decision extraction** (`recall-session-summary.js`): For sessions with 10+ messages, a second LLM call extracts 2-5 key decisions/troubleshooting findings as separate **semantic** memories (not just one episodic summary). Includes both user AND assistant messages for full context.

### Files Changed
- `hooks/observe-edit.js` — HIGH_VALUE_PATTERNS list + `high_value` flag in request body
- `hooks/recall-session-summary.js` — `extractMessages()` (both roles), `extractKeyDecisions()`, stores semantic decision memories
- `src/api/routes/observe.py` — `high_value: bool` field on `FileChangeObservation`
- `src/workers/observer.py` — `HIGH_VALUE_PROMPT`, prompt selection by flag, importance boost

---

## v2.9.2 — Health Dashboard Tooltips & Scales (2026-02-20)

### Added
- **HealthScale component**: Segmented color bar showing where the current value falls within defined ranges. Added to FeedbackCard (positive rate), GraphCohesionCard, and PinRatioCard.
- **InfoTip component**: Hover/click tooltip on an info icon — replaces inline explanation text for cleaner UI.
- **Tooltips on health cards**: PopulationCard, ImportanceChart, FeedbackHistogram, StaleAuditSection, and ConflictsTable title all have InfoTip with contextual guidance.
- **Per-conflict-type tooltips**: Each conflict type (noisy, feedback_starved, orphan_hub, decay_vs_feedback, stale_anti_pattern) shows a remediation tip via InfoTip on the type label.

### Files Changed
- `dashboard/src/components/health/HealthScale.tsx` — NEW
- `dashboard/src/components/health/InfoTip.tsx` — NEW
- `dashboard/src/components/health/FeedbackCard.tsx` — HealthScale added
- `dashboard/src/components/health/PopulationCard.tsx` — InfoTip
- `dashboard/src/components/health/GraphCohesionCard.tsx` — HealthScale
- `dashboard/src/components/health/PinRatioCard.tsx` — HealthScale
- `dashboard/src/components/health/ImportanceChart.tsx` — InfoTip
- `dashboard/src/components/health/FeedbackHistogram.tsx` — InfoTip
- `dashboard/src/components/health/ConflictsTable.tsx` — InfoTip on title + per-type tips
- `dashboard/src/components/StaleAuditSection.tsx` — InfoTip

---

## v2.9.1 — DOCX Support (2026-02-20)

### Added
- **DOCX document ingestion**: `.docx` files now parsed via `python-docx`, chunked by paragraphs, and extracted through the LLM memory pipeline — same as PDF/markdown/text.
- `parse_docx()` in `document_ingest.py` using `python-docx` (lazy import).
- `python-docx>=1.1.0` added to dependencies.

### Files Changed
- `src/core/document_ingest.py` — `parse_docx()` + "docx" dispatch in `ingest_document()`
- `src/api/routes/documents.py` — "docx" in `ALLOWED_TYPES` + `.docx` extension detection
- `pyproject.toml` — `python-docx>=1.1.0`

---

## v2.9 — "Observer Intelligence" (2026-02-19)

Observer memories get LLM-assigned importance, test payloads are filtered out,
decay respects graph connectivity, and the feedback loop actually works.

### Fixed
- **Periodic feedback always marked "not useful"**: `submitPeriodicFeedback` sent fake UUID text as `assistant_text`, which always failed the 0.35 cosine similarity check. Added `force_useful` flag to `FeedbackRequest` — re-retrieval feedback now correctly boosts memories (+0.10 importance, +0.05 stability).
- **Feedback-starved query ignored access_count**: `get_feedback_starved_memories()` returned ANY memory without feedback regardless of access count. Now cross-references with Qdrant `access_count` — only flags memories accessed 5+ times.
- **Orphan hub conflicts from flat decay floor**: Well-connected hub memories (edge strength 6-12) decayed to 0.05 floor despite being central to the graph. Graph-aware floor now preserves hubs at 0.30 minimum.

### Changed
- **Observer importance tiers**: LLM prompt now requests importance 1-10. Observer memories range from 0.1 (trivial formatting change) to 1.0 (critical architecture decision) instead of flat 0.4 for everything.
- **Graph-aware decay floor**: Memories with total RELATED_TO edge strength >= 6.0 get 0.30 floor, >= 3.0 get 0.15, otherwise 0.05. One bulk Neo4j query per decay run (no N+1).
- **`get_feedback_starved_memories()` signature**: Removed misleading `**_kwargs` — caller filters by access_count instead.

### Added
- **Test payload filtering** (hook + worker): `observe-edit.js` skips `__tests__/`, `.autopilot/`, and `*.test.*` files. Observer worker skips content containing "test document", "smoke test", "test fixture", etc.
- **`force_useful` field on `POST /memory/feedback`**: Bypasses cosine similarity check for explicit re-retrieval signals.
- **`get_bulk_edge_strengths()`** on Neo4jStore: Batch query returning total RELATED_TO strength per memory ID.

### Files Changed
- `src/workers/observer.py` — importance tiers + test content filter
- `hooks/observe-edit.js` — test dir/file skip patterns
- `src/workers/decay.py` — graph-aware floor
- `src/storage/neo4j_store.py` — `get_bulk_edge_strengths()`
- `src/api/routes/memory.py` — `force_useful` on FeedbackRequest
- `hooks/recall-retrieve.js` — `force_useful: true` for re-retrieval
- `src/storage/postgres_store.py` — cleaned up signature
- `src/core/health.py` — access_count filter for feedback-starved

---

## v2.9 — Installer Fix (2026-02-19)

### Fixed
- **`install.js` hook clobber**: `settings.hooks = buildHooksConfig()` replaced the entire hooks object, wiping non-Recall hooks (autopilot, UI, etc.). Now uses tag-based smart merge — only touches `_tag: "__recall__"` entries.
- **`install.js` uninstall clobber**: `delete settings.hooks` nuked ALL hooks. Now only removes `__recall__`-tagged entries, preserving other hook systems.
- **Env vars never written**: `RECALL_HOST`, `RECALL_API_KEY`, `OLLAMA_HOST` were printed as instructions but never written to `settings.json`'s `env` block. Now merged into `settings.env` automatically.
- **Non-Recall hooks in installer**: Removed `lint-check.js`, `context-monitor.js`, `stop-guard.js` from the Recall installer — these are autopilot hooks, not Recall-specific.

### Added
- **`--key` and `--ollama` CLI flags**: `node install.js --host URL --key KEY --ollama URL` for fully non-interactive install.
- **Legacy hook migration**: `isRecallHook()` detects both tagged (`_tag: "__recall__"`) and untagged legacy hooks (by command path matching), ensuring clean upgrade from older installs.
- **`_tag: "__recall__"`** on all Recall hook entries and statusline for safe identification.

---

## v2.8 — "Tip Top Shape" (2026-02-19)

Hardening pass — no new features, just making everything that exists work correctly.

### Fixed
- **Importance collapse** (bcd1648): 92% of memories decayed to 0.01-0.02. Root cause: rehydrate IDs submitted as feedback, net-negative per session. Fix: tag entries by source, filter feedback to search-only, rebalance boost/penalty, raise floor to 0.05. 240/559 memories rehabilitated.
- **Duplicate memories** (0f3bd4d): 129 near-dupes (18% of corpus). Added semantic dedup at ingest (cosine > 0.95 = reject) across all 3 ingest paths (store, signal, observer). Batch cleanup endpoint. Corpus 701 → 572.
- **Null durability on pre-v2.2 memories** (c1cb466): 29 memories had null durability. Ran existing migration endpoint — 19 durable, 6 ephemeral, 4 permanent.
- **Ghost conflicts** (c1cb466): 150 conflicts included superseded/deleted memory references from Postgres audit_log and Neo4j. Fixed by filtering against active Qdrant memory set. 150 → 43.
- **Integration test suite** (6e699d3): 11 failures → 0. Root causes:
  - `normalize_domain()` destroyed `test-integration-*` isolation — added bypass
  - Semantic dedup skipped `add_to_working_memory()` — fixed both dedup paths
  - Generic test content hit 0.95 dedup threshold — replaced with distinct content
  - Graph expansion polluted filter tests — added `expand_relationships: false`
  - Timeline endpoint didn't normalize domain param
  - Rate limiting without retry wrapper on search tests
- **Retrieval-time dedup broken** (0f3bd4d): `content_hash` wasn't propagated to Memory objects in `_payload_to_memory()`.
- **Build-guard hook** (21e924d): didn't block `stop` during `/fix` mode.

### Changed
- Decay frequency: 48x/day → 4x/day (1dd5c36)
- Feedback boost: +0.05 → +0.10 importance, +0.03 → +0.05 stability
- Feedback penalty: -0.02 → -0.01 importance, -0.01 → -0.005 stability
- Importance floor: 0.01 → 0.05 (both decay and penalty paths)

### Added
- Periodic session checkpoints (1b21704): every 25 prompts or 2 hours, stores checkpoint summary and submits feedback for stale entries. Fixes dead feedback loop in long-running sessions.
- `POST /admin/dedup` endpoint for batch duplicate cleanup (2/hr rate limit)
- `docs/TUNING.md` — living ledger of all parameter adjustments with rationale

### Stats
- Integration tests: **210 passed**, 0 failed, 3 skipped
- Active memories: 724
- Conflicts: 43 (down from 150)

---

## v2.8.1–v2.8.6 — Hardening Passes (2026-02-18 → 2026-02-19)

Six sequential hardening commits after the initial v2.8 merge. Each addressed a batch of issues found during full-capacity operation testing.

### v2.8.6 (6f410d8)
- Tag post-filter in retrieval, testbed isolation, architecture graph dashboard page

### v2.8.5 (e3598b2)
- 15 fixes: audit resilience, invalidation accuracy, safety guards

### v2.8.4 (3900673)
- 10 fixes: document audit, consolidation scoping, data integrity

### v2.8.3 (3e87540)
- 9 fixes: health dashboard accuracy, data integrity

### v2.8.2 (c8b260e)
- 11 fixes: retrieval quality, data integrity

### v2.8.1 (19de3ed)
- 10 fixes for full-capacity operation

---

## v2.7 — "Trust & Context" (2026-02-18)

PR #2 merged. Temporal context, git-aware invalidation, ML evaluation.

### Added
- **Temporal rehydrate**: `POST /search/rehydrate` — time-windowed narrative summary with anti-pattern inclusion. MCP tool `recall_rehydrate`.
- **Git-aware invalidation**: `hooks/git-watch.js` detects file changes, `POST /admin/invalidate/git` marks stale memories, admin stale/resolve endpoints.
- **ML eval harness**: `tests/ml/run_eval.py` — held-out evaluation with curated datasets, per-type metrics.
- **Realistic training corpus**: 1,209 samples across 8 languages, 10 domains. Binary CV F1=0.943, type CV F1=0.649.
- **Dashboard redesign**: AI aesthetic (dark-first), stale audit panel.
- Integration tests for v2.7 features.

### Improved
- ML generalization gap closed: curated F1 0.240 → 0.884 via Stage 4 realistic corpus
- Per-type macro F1: 0.520 → 0.793

---

## v2.6 — "Tighten the Loop" (2026-02-18)

PR #1 merged. Performance optimization across the entire pipeline.

### Added
- ML in-process caching for reranker and signal classifier (Redis → memory with TTL)
- Embedding LRU cache: 200 entries, 300s TTL, skips Ollama on hit
- `asyncio.gather()` parallelization in graph expansion and health computation
- Background `track_access` (non-blocking via `create_task`)
- Contradiction embedding passthrough (avoids re-embedding)
- Retrieval pipeline singleton with cache invalidation
- Domain filter via API param (not query text pollution)
- File-type filter in observe-edit hook (SKIP_EXTENSIONS, SKIP_DIRS)
- Session-scoped feedback tracking
- Docker resource limits (api=512M, worker=512M, neo4j=1G, etc.)
- 22 new tests, integration smoke test

### Stats
- 23 files changed, +1917/-260 lines

---

## v2.5 — ML Signal Classifier (2026-02-17)

### Added
- **Signal classifier**: TF-IDF (500 vocab) + 8 conversation features, pure-math sigmoid inference. Binary (gates LLM) + Type (8 classes).
- Training from static corpus (68 samples). StandardScaler baked into weights.
- Integration in `signals.py` as ML pre-filter before LLM detection.
- Admin endpoints: `POST /admin/ml/retrain-signal-classifier`, `GET /admin/ml/signal-classifier-status`.
- 33 unit tests + standalone simulation.

### Performance
- Binary F1=0.93, precision=1.0 (zero false positives)
- Inference: 0.08ms avg (vs 2-5s LLM)

---

## v2.4 — ML Reranker (2026-02-17)

### Added
- **Reranker model**: 11 features, logistic regression, pure-math sigmoid inference.
- Training from Postgres audit_log feedback (min 30 samples, cross-validation).
- Blend: `0.7 * ML + 0.3 * similarity` when model available, legacy formula otherwise.
- Admin endpoints: retrain + status.
- Feedback enrichment with memory metadata.
- 22 unit tests.

### Performance
- 150 training samples, CV score=1.0

---

## v2.3 — "Make It Actually Work" (2026-02-17)

### Fixed
- Domain normalization: 542 domains normalized via `normalize_domain()` + admin migration
- Signal pipeline: importance+durability now carried through pending signal dict
- Double-division importance bug removed
- Graph bootstrap: `scroll_all(with_vectors=True)` returns 3-tuples

### Added
- `src/core/domains.py`: canonical domains, aliases, multi-level matching
- `src/core/auto_linker.py`: auto-link similar memories (>0.5 threshold)
- Admin endpoints: domain normalize, graph bootstrap, importance rehabilitation
- Importance floor (0.15) in retrieval scoring
- Null durability defaults to durable

### Stats
- 1,685 graph edges created, 166 memories rehabilitated

---

## v2.2 — Durability, Health, Documents (2026-02-16)

### Phase 15A: Memory Durability
- Durability enum: ephemeral, durable, permanent
- Decay behavior: permanent=immune, durable=0.15x, ephemeral=normal
- LLM classifies durability per signal

### Phase 15B: Health Dashboard
- HealthComputer with feedback metrics, population balance, graph cohesion
- Force profile: per-memory forces + importance timeline
- Conflict detection: noisy, decay-vs-feedback, orphan hub, stale, feedback-starved

### Phase 15C: Document Memory
- Upload → parse → chunk → LLM extract → embed → store pipeline
- PDF (pymupdf), markdown, plaintext support
- Neo4j Document nodes with EXTRACTED_FROM edges
- Cascade operations (pin/unpin/delete/domain-update)
- Sibling boost in retrieval (0.3 * importance)

---

## v2.1 — Hardening (2026-02-15)

### Added
- Escalating anti-pattern boost: `1.0 + 0.1 * log2(1 + triggers)`
- Co-retrieval strengthening via feedback
- `access_count` exposed in browse/timeline
- Auto-pin suggestions (importance >= 0.7 && access_count >= 10)

---

## v2.0 — Adaptive Memory (2026-02-15)

### Phase 14A: Memory Pinning
- `pinned` flag, decay immunity, pin/unpin endpoints

### Phase 14B: Anti-Pattern System
- Separate Qdrant collection, CRUD endpoints, WARNING signal type routing
- Retrieval Stage 4.5 anti-pattern check

### Phase 14C: Feedback Loop
- Track injected IDs, submit feedback at session end
- Useful: +importance/+stability. Not useful: -importance/-stability.

---

## v1.0 — Foundation (Phases 1–13)

### Phase 13: Multi-User Support
- Auth middleware, per-user API keys, user attribution on memories

### Phase 12: Neural Memory
- Spreading activation (replaces flat BFS), inhibition, auto-elevation

### Phase 11: Organic Memory Hooks
- `recall-retrieve.js` (prompt inject), `recall-session-summary.js` (stop), `observe-edit.js` (file edits)

### Phase 10: Dashboard Redesign
- Collapsible sidebar, dark/light theme, toast notifications, bulk ops

### Phase 9: Claude-Pilot Patterns
- 3-layer search (browse/timeline/full), observer hooks, sub-embeddings, React SPA, SSE events

### Phase 8: Quality of Life
- Batch ops, date-range search, rate limiting, domain stats, Ollama fallback

### Phase 7: Observability
- JSONL export/import, reconcile, Prometheus metrics, dashboard, instrumentation

### Postgres Integration
- Audit log, session archive, metrics snapshots

### Phase 6: Smarter Memory Formation
- LLM consolidation merge, pattern extraction, contradiction resolution, MCP session tools

### Phase 5: Security & Access Control
- Auth, error sanitization, input validation, CORS

### Phase 4: Event System & Session Lifecycle

### Phase 3: Hardening & Correctness (10 fixes)

### Phase 2: Signal Detection Brain

### Phase 1: API Hardening + Integration Tests
