# ML Plan for Recall — Benefit Scale & Real-Life Simulation

## Current System Baseline (as of 2026-02-18)

```
Memories:           602
Graph edges:        1,275 (avg 2.1 per memory)
Feedback:           150 events (77% positive rate)
Importance dist:    71% in 0.0-0.2 range (most memories are "low")
Domains:            15 canonical, balanced distribution after reclassification
Retrieval:          6-stage pipeline, hardcoded weights
Hardware:           RTX 3090 running qwen3:14b + qwen3-embedding:0.6b
```

### Current Retrieval Quality Problem

Query: "how to deploy docker containers"
```
Result 1: similarity=0.49  "Dashboard build and deploy workflow..."        ← relevant
Result 2: similarity=0.00  "Found 5 related memories about 'infra...'"    ← graph noise
Result 3: similarity=0.00  "Found 5 related memories about 'database...'" ← graph noise
Result 4: similarity=0.55  "How to deploy Build Hub: Docker Compose..."   ← relevant
Result 5: similarity=0.00  "Found 5 related memories about 'backend...'"  ← graph noise
```

**3 out of 5 results are irrelevant graph-expansion noise with 0.0 similarity.** This is the #1 quality problem.

---

## Benefit Scale (1-10)

| ML Feature | Benefit | Effort | Data Needed | Priority |
|------------|---------|--------|-------------|----------|
| Retrieval reranking | **9/10** | Medium | 150+ feedback events (have it) | **1st** |
| Domain classifier (replace LLM) | **3/10** | Low | 602 labeled memories (have it) | 4th |
| Importance prediction | **6/10** | Medium | Access patterns + feedback | 2nd |
| Decay rate learning | **4/10** | High | Months of usage data | 5th |
| Graph edge quality filter | **7/10** | Low | Current edge + feedback data | **3rd** |

---

## Feature 1: Retrieval Reranking (Benefit: 9/10)

### What it does
Learns which retrieved memories are actually useful based on feedback data. Replaces the hardcoded 6-stage scoring with a learned ranking function.

### How it works (no new infrastructure)

**Training phase** (one-time, runs on existing data):
1. From feedback events, extract `(query_embedding, memory_embedding, was_useful)` triples
2. Compute features for each pair:
   - Cosine similarity (already have)
   - Graph distance (1=direct, 2=2-hop, 0=no connection)
   - Edge strength (if connected)
   - Importance score
   - Access count
   - Domain match (1 if same domain, 0 if not)
   - Memory age (days since creation)
   - Memory type (semantic=0, episodic=1, procedural=2)
3. Train a logistic regression: `P(useful) = sigmoid(w · features)`
4. Store the weight vector (8 floats) in config

**Inference** (replaces current scoring):
```python
# Current: score = similarity * max(importance, 0.15) + graph_boost + fact_boost
# New:     score = learned_model.predict(features)
```

### Real-life simulation

**Before (current system):**
```
Tim's prompt:  "How do I configure Neo4j for Recall?"
recall-retrieve.js sends query to /search/browse

Stage 1 (vector):    Find top 20 by embedding similarity
Stage 2 (graph):     Expand via RELATED_TO edges (+15 neighbors)
Stage 3 (facts):     Check sub-embeddings (+5 fact matches)
Stage 4 (anti):      Check anti-patterns
Stage 5 (inhibit):   Remove contradictions
Final scoring:       similarity * max(importance, 0.15) + graph_activation

Top 5 injected into Claude's context:
  1. "Neo4j connection string is bolt://..." (sim=0.72, useful!)
  2. "Build Hub CRDT strategy: Yjs..." (sim=0.0, graph noise, useless)
  3. "Found 5 related memories about..." (sim=0.0, synthesis blob, useless)
  4. "Docker compose restart api worker" (sim=0.31, tangentially useful)
  5. "Auth middleware resolves Bearer..." (sim=0.0, graph noise, useless)

→ 2/5 useful. 3 wasted context window slots.
```

**After (with learned reranker):**
```
Same query, same candidate pool of 35 memories.

Reranker scores each candidate:
  "Neo4j connection string..."  → P(useful)=0.89 (high sim + database domain + high access)
  "Build Hub CRDT strategy..."  → P(useful)=0.12 (zero sim, graph-only, wrong domain)
  "Found 5 related memories..." → P(useful)=0.08 (zero sim, synthesis type, low access)
  "Neo4j driver.session()..."   → P(useful)=0.83 (high sim + database domain + procedural)
  "Qdrant indexes for Neo4j..." → P(useful)=0.71 (medium sim + database domain)
  "Docker compose restart..."   → P(useful)=0.45 (low sim but high access, infrastructure)
  "Auth middleware..."           → P(useful)=0.15 (zero sim, security domain, graph-only)

Top 5 injected:
  1. "Neo4j connection string..." (0.89)    ← directly answers the question
  2. "Neo4j driver.session()..." (0.83)     ← relevant code pattern
  3. "Qdrant indexes for Neo4j..." (0.71)   ← related infrastructure
  4. "Docker compose restart..." (0.45)     ← operational context
  5. "Auth middleware..." (0.15)             ← still noise, but pushed to last slot

→ 4/5 useful. The reranker learned that zero-similarity graph-only results
  are almost never useful, and that domain match is a strong signal.
```

### Why it's high-benefit
- Directly improves every single retrieval query
- The feedback loop provides continuous training data
- 150 feedback events is enough for logistic regression (8 features)
- Zero additional LLM calls — pure math on existing features
- Deploys as ~50 lines of Python, 8 float weights

### Implementation estimate
- Training script: ~100 lines (sklearn LogisticRegression)
- Inference: Replace `_score_candidate()` in retrieval.py (~30 lines)
- Admin endpoint to retrain: `POST /admin/ml/retrain-ranker`
- Total: ~200 lines of Python, no new dependencies beyond sklearn/numpy

---

## Feature 2: Importance Prediction (Benefit: 6/10)

### What it does
Predicts initial importance for new memories based on content features, replacing the LLM's noisy 1-10 rating.

### The problem
71% of memories (425/602) have importance 0.0-0.2. Either:
- a) They genuinely aren't important (possible but unlikely for ALL of them)
- b) Decay has crushed them all to floor level
- c) Initial importance assignment is broken

Looking at the data: 8239 decay events vs 3649 creates means each memory has been decayed ~2.3 times on average. The decay is aggressive — most things get pushed to floor regardless of initial importance.

### How it works

**Features** (computed at store time):
- Content length
- Domain (one-hot encoded)
- Memory type (semantic/episodic/procedural)
- Number of similar existing memories (novelty signal — fewer = more important)
- Embedding distance to nearest existing memory (farther = more novel)
- Has code snippets (regex check)
- Has specific entities (IPs, paths, names)

**Training**: Use access_count as a proxy for "importance was correct." High-access memories were important; never-accessed ones weren't. Train a simple regression.

### Real-life simulation

**Before:**
```
Observer detects: "The Qdrant collection for anti-patterns is recall_memories_anti_patterns"
LLM rates importance: 4/10 → 0.4
After 3 decay cycles: 0.4 × 0.985^3 = 0.38
After 10 decay cycles: 0.4 × 0.985^10 = 0.34
After 50 decay cycles: 0.4 × 0.985^50 = 0.19
→ Approaches floor. Gets retrieved less. Gets decayed more. Spiral.
```

**After (with importance prediction):**
```
Observer detects: "The Qdrant collection for anti-patterns is recall_memories_anti_patterns"
ML model sees: specific entity (collection name), domain=database, type=semantic,
               only 2 similar memories → high novelty
Predicted importance: 0.7 (high novelty + specific entity)
Durability auto-set to "durable" (importance > 0.5 heuristic)
After 50 decay cycles: 0.7 × (0.985 × 0.15)^50 = 0.7 × 0.9978^50 = 0.63
→ Stays useful. Gets retrieved. Gets positive feedback. Importance stabilizes.
```

### Why it's medium-benefit
- Fixes the importance death spiral for novel/specific memories
- But the underlying problem is really that decay is too aggressive
- Simpler fix: just tune decay rates. ML is the fancy version of "lower the decay rate for useful stuff"

---

## Feature 3: Graph Edge Quality Filter (Benefit: 7/10)

### What it does
Filters out low-quality graph edges that produce the 0.0-similarity noise in results.

### The problem
The graph bootstrap created 1,685 edges using cosine similarity > 0.5. But spreading activation propagates to 2-hop neighbors regardless of whether the path makes semantic sense. A memory about "Neo4j config" connects to "database deploy" which connects to "Build Hub CRDT" — and suddenly CRDT shows up in Neo4j queries.

### How it works (simple, no training)

**Approach A — Minimum activation threshold (no ML, just tuning):**
Currently spreading activation has threshold 0.05. Raising it to 0.15-0.20 would kill the long-tail noise.

**Approach B — Learned edge weights (light ML):**
Use feedback data to learn which edge types are useful:
1. When a memory gets positive feedback, credit the edges that led to it
2. When a memory gets negative feedback, penalize those edges
3. Over time, useful edges get stronger, noisy edges weaken
4. Already partially implemented via co-retrieval strengthening

### Real-life simulation

**Before:**
```
Query: "Redis cache configuration"
Vector match: "Redis keys: recall:session:{id}..." (sim=0.68)
Graph expand from that node:
  → "Session lifecycle management" (edge strength 0.9, but sim=0.0 to query)
  → "Worker retry with ARQ" (edge strength 0.85, but sim=0.0 to query)
  → "Build Hub task queue" (edge strength 0.7, 2-hop, sim=0.0 to query)
All three get injected with graph-boosted scores, diluting the good results.
```

**After (threshold raised to 0.20):**
```
Query: "Redis cache configuration"
Vector match: "Redis keys: recall:session:{id}..." (sim=0.68)
Graph expand: same neighbors found, but:
  → "Session lifecycle" activation=0.12 → below 0.20 threshold → FILTERED
  → "Worker retry" activation=0.09 → below threshold → FILTERED
  → "Build Hub task queue" activation=0.04 → below threshold → FILTERED
Only the direct vector matches survive. Result quality jumps.
```

### Why it's high-benefit but low-effort
- The fix is literally changing one number in retrieval.py (threshold 0.05 → 0.20)
- Could also add: if a candidate has similarity=0.0 to the query AND only arrived via graph, cap its score
- No training needed, no new dependencies
- Immediate impact on every retrieval

---

## Feature 4: Domain Classifier (Benefit: 3/10)

### What it does
Replaces the LLM call + alias dict with a nearest-centroid classifier using existing embeddings.

### How it works
1. Compute mean embedding per domain from the 602 labeled memories
2. Store 15 centroid vectors (15 × 1024 floats)
3. At classify time: embed content, find nearest centroid
4. If distance > threshold, fall back to "general"

### Why it's low-benefit
- The compound matching + LLM constraint already works well enough
- The LLM reclassification is a one-time migration, not ongoing
- For new memories, the signal detector prompt constrains to canonical domains
- A classifier saves ~2 seconds per memory (LLM call) but only fires on unknown domains
- Not worth the complexity unless you're storing hundreds of memories per hour

---

## Feature 5: Decay Rate Learning (Benefit: 4/10)

### What it does
Learns per-memory or per-domain optimal decay rates from usage patterns.

### Why it's low-priority
- Requires months of longitudinal data to train meaningfully
- The durability system (ephemeral/durable/permanent) already provides 3 tiers
- Simpler approach: just lower the base decay rate. Currently 0.985 per cycle — try 0.99
- The real fix is making the feedback loop work better (it already boosts importance on positive feedback)

---

## Recommended Implementation Order

### Phase 1: Quick wins (no ML, just tuning) — 1 hour
1. **Raise graph activation threshold** from 0.05 to 0.20 in `retrieval.py`
2. **Add similarity floor for graph results**: if `similarity == 0.0` and source is graph-only, cap score at 0.1
3. Deploy. Immediately fixes the 3/5 noise problem.

### Phase 2: Retrieval reranker — 1 session
1. Write training script that pulls feedback data
2. Train logistic regression on 150 feedback events
3. Replace `_score_candidate()` with learned function
4. Add `/admin/ml/retrain-ranker` endpoint
5. Deploy. Every future retrieval is better.

### Phase 3: Importance prediction — 1 session
1. Compute feature matrix from existing memories
2. Use access_count as label proxy
3. Train regression model
4. Integrate into store paths
5. Deploy. New memories start with better importance.

### Phases 4-5: Only if phases 1-3 show measurable improvement and more data accumulates.

---

## How to Measure Improvement

### Before/after metrics to track

| Metric | Current | Target | How to measure |
|--------|---------|--------|----------------|
| Feedback positive rate | 77% | 85%+ | `GET /admin/health/dashboard` → feedback.positive_rate |
| Zero-similarity results in top 5 | ~60% | <20% | Add logging in recall-retrieve.js |
| Mean similarity of injected memories | ~0.20 | >0.35 | Add logging in recall-retrieve.js |
| Memories at floor importance (<0.05) | Unknown | <10% | Importance distribution in health dashboard |

### Measurement approach
1. Add a field to the feedback hook: log the similarity scores of injected memories
2. Run 1 week with current system, collect baseline
3. Deploy Phase 1, run 1 week, compare
4. Deploy Phase 2, run 1 week, compare
5. Each phase should show improvement in positive rate and mean similarity

Without this measurement, we're guessing. The domain reclassification was measurable (75% general → 5%). Retrieval quality improvements need the same rigor.

---

## What ML Does NOT Help With

| Problem | Why ML won't help | Better fix |
|---------|-------------------|------------|
| Missing memories | ML can't create memories that don't exist | Better observer hooks, more signal types |
| Stale content | ML can't update facts that changed | TTL + re-observation on file changes |
| Duplicate memories | Already solved by content_hash dedup | N/A |
| Slow retrieval | Bottleneck is Ollama embedding, not scoring | Batch embeddings, cache popular queries |
| Wrong memory type | LLM classifies well enough | Prompt tuning |
