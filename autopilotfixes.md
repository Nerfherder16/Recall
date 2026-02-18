# Autopilot v2.3 Post-Mortem — Issues to Fix

The autopilot `/build` completed all 12 tasks but left several real problems behind. These are bugs, gaps, and missed opportunities found during deployment and verification.

## Critical: Source-Level Tests Don't Catch Runtime Bugs

**Problem**: All 46 v2.3 tests use regex/string matching on source files instead of testing actual runtime behavior. This means the scroll_all 3-tuple unpacking bug shipped and was only caught during live deployment.

**Files affected**: Every test in `tests/core/`, `tests/api/`, `tests/workers/`

**Fix**: Write real integration tests that actually call the endpoints. At minimum:

1. `POST /admin/graph/bootstrap` — spin up test Qdrant+Neo4j fixtures, store 3 memories, call bootstrap, assert RELATED_TO edges exist in Neo4j
2. `POST /admin/domains/normalize` — store a memory with domain "Docker/Containerization", call normalize, assert domain is now "infrastructure"
3. `POST /admin/importance/rehabilitate` — store a memory with importance 0.01 and access_count 5, call rehabilitate, assert importance > 0.01
4. `POST /memory/store` with non-canonical domain — assert the stored domain is canonical
5. Signal approve flow — create a pending signal with importance/durability, approve it, assert the Memory has durability and initial_importance set

These require the existing `conftest.py` fixtures (running Qdrant, Neo4j, Redis) — not source-level hacks. Put them in `tests/integration/test_v23_runtime.py`.

## Critical: 432 Memories Stuck in "general" Domain

**Problem**: The first domain migration ran with the old exact-match normalization. It replaced all freeform domains with "general" before the compound matching fix was deployed. The original freeform domain names are gone — re-running the migration now finds nothing to update.

**Fix**: LLM re-classification. For each memory in the "general" domain:
1. Send the memory content to the LLM with the canonical domain list
2. Ask it to classify into one of the ~15 domains
3. Update Qdrant payload + Neo4j node

**Implementation approach**:
- New admin endpoint: `POST /admin/domains/reclassify`
- Use `scroll_all()` with a Qdrant filter for `domain == "general"`
- Batch through Ollama (qwen3:14b) with rate limiting (Semaphore(1), like fact extraction)
- JSON prompt: `"Given this memory content, which domain does it belong to? Choose from: [list]. Respond with JSON: {\"domain\": \"...\"}."`
- Only update if confidence is reasonable (don't let the LLM hallucinate)
- Log all changes for audit

**Estimated scope**: ~432 memories × ~2s each = ~15 minutes runtime. Should be an async background task with progress tracking.

## High: TDD Enforcer Hook is Counterproductive

**Problem**: `hooks/tdd-enforcer.js` fires as a PostToolUse hook, meaning it runs AFTER the write is already applied. The "BLOCKED" message is cosmetic noise that doesn't actually prevent anything. Worse, it uses mirror-path matching (`src/foo/bar.py` → `tests/foo/test_bar.py`) which doesn't match the actual test file organization (tests are in `tests/core/`, `tests/api/`, `tests/workers/` — not mirroring the full src path).

**Fix options**:
1. **Delete it.** The TDD discipline comes from the `/build` workflow, not a broken hook. The hook adds noise without value.
2. **Fix it.** Make it a PreToolUse hook (so it actually blocks), and use glob-based test discovery instead of mirror paths. But PreToolUse hooks can't block writes in Claude Code — they're informational only.
3. **Convert to advisory.** Keep it as PostToolUse but make the output a gentle reminder ("Consider writing tests for this file") instead of a fake "BLOCKED" message.

**Recommendation**: Option 1 — delete it. The `/build` skill already enforces TDD.

## High: Signal Pipeline — No Runtime Verification

**Problem**: We fixed the code that passes importance/durability through the signal pipeline, but we never verified it works end-to-end in production. The signal pipeline is:
1. Conversation ingested → signals detected by LLM → `add_pending_signal(session_id, {...})`
2. User approves signal → `approve_signal()` creates Memory with durability + initial_importance
3. Memory stored with auto-linking

There's no test or verification that the LLM actually produces `importance` and `durability` fields in its signal detection output. If qwen3 ignores those prompt fields, the whole fix is moot.

**Fix**:
1. Ingest a real test conversation
2. Check Redis for the pending signal dict — verify importance and durability are present
3. Approve the signal
4. Check the resulting Memory — verify durability and initial_importance are set
5. Check Neo4j — verify RELATED_TO edges were created

This can be a manual verification or an integration test.

## Medium: Auto-Linker Runs in Background Without Error Reporting

**Problem**: In `memory.py`, the auto_linker runs as a `BackgroundTask`. If it fails (Qdrant down, Neo4j down, etc.), the error is silently swallowed. The user gets a successful store response but no graph edges.

**Fix**: Add structured logging at minimum. Optionally, add a health check that verifies the ratio of memories with graph edges. If it drops below a threshold, surface it in the health dashboard.

**File**: `src/api/routes/memory.py` — the `background_tasks.add_task(auto_link_memory, ...)` call

## Medium: progress.json Wasn't Updated Per-Task

**Problem**: The autopilot spec says to update progress.json after each task. In practice, tasks 5-12 were marked PENDING until the final bulk update. This means if the build had been interrupted mid-way, the progress file would have been misleading.

**Fix for autopilot workflow**: The `/build` skill should explicitly write to progress.json BEFORE starting each task (mark IN_PROGRESS) and AFTER completing (mark DONE). This should be a hard requirement in the skill prompt, not optional.

## Low: Domain Stats Show Imbalanced Distribution

**Current state after migrations**:
```
general:         432 (75%)
frontend:         72 (12%)
infrastructure:   31 (5%)
configuration:    15 (3%)
security:         11 (2%)
devops:            6 (1%)
testing:           5 (1%)
api:               2 (<1%)
sessions:          1 (<1%)
development:       1 (<1%)
```

The "general" bucket is a dumping ground. Even after the compound matching fix, new memories from the LLM signal detector will still produce freeform domains that don't match. The LLM prompt constrains to canonical domains but qwen3:14b doesn't always follow instructions precisely.

**Fix**: Add a validation layer in the signal detector that rejects non-canonical domains and retries or falls back. Currently the prompt says "must be one of: [list]" but there's no enforcement after the LLM responds.

## ML Opportunity Assessment

### Where ML Would Help

1. **Domain classification (HIGH VALUE)**: Instead of regex/alias matching, train a small text classifier on the ~576 existing memories (once properly labeled) to predict domain from content. Could use the existing qwen3-embedding:0.6b embeddings + a simple nearest-centroid classifier. No new infrastructure needed — just compute centroids per domain from existing embeddings and classify by nearest centroid at store time. This replaces both the alias dict AND the LLM prompt constraint.

2. **Importance prediction (MEDIUM VALUE)**: The LLM's 1-10 importance rating is noisy and inconsistent. A model trained on historical importance + access patterns could predict better initial importance. Features: content length, domain, memory_type, time of day, embedding similarity to existing high-importance memories. Simple logistic regression would work.

3. **Retrieval quality scoring (HIGH VALUE but hard to measure)**: The retrieval pipeline has 6 stages with hardcoded weights (similarity, graph activation, fact boost, anti-pattern check, inhibition). These weights could be learned from the feedback loop data (useful_memory_ids from session summaries). This is essentially learning-to-rank, which is a well-studied ML problem. But you need more feedback data first — right now there's not enough signal.

### Where ML Would NOT Help

1. **Domain alias matching** — The compound matching fix solves this adequately. ML would be overengineering for string normalization when the real fix is making the LLM produce canonical domains.
2. **Graph edge creation** — The auto-linker uses embedding similarity (>0.5 threshold), which IS already an ML approach (cosine similarity on learned embeddings). A more sophisticated model isn't needed.
3. **Decay rates** — The durability system (ephemeral/durable/permanent) with fixed multipliers is simple and interpretable. ML would make it opaque without clear benefit.

### Recommended ML Approach (if pursuing)

**Nearest-centroid domain classifier** — minimal effort, high impact:
1. Query all properly-labeled memories per domain (post-reclassification)
2. Compute mean embedding vector per domain = centroid
3. Store centroids in a dict in `src/core/domains.py`
4. At classify time: embed the content, find nearest centroid, use that domain
5. Fallback to "general" if nearest distance > threshold

This replaces the entire alias dict + compound matching with a single cosine similarity lookup. Update centroids periodically via admin endpoint.

## File Reference

| File | Issues |
|------|--------|
| `tests/core/`, `tests/api/`, `tests/workers/` | Source-level tests — need real integration tests |
| `src/core/domains.py` | Compound matching works, but 432 existing memories stuck in "general" |
| `hooks/tdd-enforcer.js` | Broken — fires after writes, wrong path matching |
| `src/api/routes/memory.py` | Auto-linker background task has no error reporting |
| `src/workers/signals.py` | Signal pipeline importance/durability never verified end-to-end |
| `.autopilot/progress.json` | Should be updated per-task, not bulk |
| `src/core/signal_detector.py` | LLM doesn't always respect domain constraint — needs post-validation |
