# Recall Tuning Ledger

Living document tracking every parameter adjustment, what it changed, why, and the measured effect.
Read this before adjusting any threshold, rate, or weight.

---

## Active Parameters

### Decay System (`src/workers/decay.py`)

| Parameter | Value | File:Line | Last Changed |
|-----------|-------|-----------|--------------|
| Base decay rate | 0.01/hr | `src/core/config.py:51` | Original |
| Decay schedule | **Every 6hr** (0:15, 6:15, 12:15, 18:15) | `src/workers/main.py:232-236` | 2026-02-19 |
| Importance floor | **0.05** | `decay.py:136, 247` | 2026-02-19 |
| Durability modifiers | permanent=immune, durable=0.15x, ephemeral=1.0x | `decay.py:87-130` | v2.2 |
| Null durability default | Treated as "durable" (0.15x) | `decay.py:92-93` | v2.3 |
| Access frequency mod | `1.0 / (1.0 + 0.1 * access_count)` | `decay.py:113` | Original |
| Feedback ratio mod | `1.0 - (0.5 * useful_ratio)` | `decay.py:124-126` | Original |
| Pinned immunity | Skipped entirely | `decay.py:81-83` | v2.2 Phase 14A |

### Feedback Loop (`src/api/routes/memory.py`, hooks)

| Parameter | Value | File:Line | Last Changed |
|-----------|-------|-----------|--------------|
| Useful boost (importance) | **+0.10** | `memory.py:461` | 2026-02-19 |
| Useful boost (stability) | **+0.05** | `memory.py:462` | 2026-02-19 |
| Not-useful penalty (importance) | **-0.01** | `memory.py:468` | 2026-02-19 |
| Not-useful penalty (stability) | **-0.005** | `memory.py:469` | 2026-02-19 |
| Penalty importance floor | **0.05** | `memory.py:468` | 2026-02-19 |
| Cosine similarity threshold | 0.35 | `memory.py:459` | v2.2 Phase 14C |
| Rehydrate IDs in feedback | **No** (filtered by source tag) | `recall-session-summary.js:196` | 2026-02-19 |

### Retrieval Scoring (`src/core/retrieval.py`)

| Parameter | Value | File:Line | Last Changed |
|-----------|-------|-----------|--------------|
| Importance floor in scoring | 0.15 | `retrieval.py:174, 220` | v2.3 |
| Fact search bonus | 1.15x | `retrieval.py:220` | Phase 9 |
| ML reranker blend | 0.7 ML + 0.3 similarity | `retrieval.py` | v2.4 |
| Graph activation decay | per-hop with edge strength | `retrieval.py` | Phase 12A |
| Contradiction inhibition | 0.7x penalty | `retrieval.py` | Phase 12B |
| Anti-pattern boost | `1.0 + 0.1 * log2(1 + triggers)` | `retrieval.py` | v2.1 |
| Track access boost | +0.02 (1hr cooldown) | `retrieval.py:563-577` | Original |

### Retrieval Hook (`hooks/recall-retrieve.js`)

| Parameter | Value | Last Changed |
|-----------|-------|--------------|
| Min prompt length | 15 chars | Original |
| Max results | 5 | Original |
| Min similarity | 0.25 | Original |
| Rehydrate max entries | 10 | v2.8 |
| Browse timeout | 3.5s | v2.8 |
| Injected entry source tag | "search" or "rehydrate" | 2026-02-19 |

### Session Summary Hook (`hooks/recall-session-summary.js`)

| Parameter | Value | Last Changed |
|-----------|-------|--------------|
| Min user messages | 2 | v2.8 |
| LLM summary threshold | 3+ messages, 200+ chars | v2.8 |
| Feedback timeout | 8s | v2.8 |
| Summary importance (LLM) | 0.5 | v2.8 |
| Summary importance (fallback) | 0.4 | v2.8 |

### ML Signal Classifier (`src/core/signal_classifier.py`)

| Parameter | Value | Last Changed |
|-----------|-------|--------------|
| Binary CV F1 | 0.943 | v2.7 |
| Type CV F1 | 0.649 | v2.7 |
| Training samples | 1,209 | v2.7 |
| TF-IDF vocab size | 1,000 | v2.7 |

### ML Reranker (`src/core/reranker.py`)

| Parameter | Value | Last Changed |
|-----------|-------|--------------|
| CV score | 0.984 | v2.6 |
| Training samples | 2,179 | v2.6 |
| Features | 11 | v2.4 |

### Rehabilitation (`src/api/routes/admin.py`)

| Parameter | Value | File:Line | Last Changed |
|-----------|-------|-----------|--------------|
| Trigger threshold | importance < 0.05 | `admin.py:729-788` | v2.3 |
| Accessed 3+ or pinned → floor | 0.30 (or initial_importance * 0.5) | `admin.py` | v2.3 |
| Durable/permanent → floor | 0.20 | `admin.py` | v2.3 |

---

## Change History

### 2026-02-19: Reduce decay frequency from 48x/day to 4x/day

**Problem:** Decay ran every 30 min (48x/day), applying relentless downward pressure. Combined with the now-rebalanced feedback loop, this was overkill — memories that get one useful retrieval per day only gain +0.11, but decay at 48x/day could remove ~0.05-0.10/day for low-stability durable memories.

**Change:** `src/workers/main.py:232-236` — `minute={15, 45}` → `hour={0, 6, 12, 18}, minute=15`

**Expected effect:** 12x less decay pressure. Durable memories at importance 0.30 should now lose ~0.002/day instead of ~0.024/day. One useful retrieval per day (+0.10) easily overwhelms decay.

**What to watch:** If memories start accumulating above 0.8 without being genuinely useful, consider bumping back to every 4 hours (6x/day).

---

### 2026-02-19: Fix importance collapse (commit bcd1648)

**Problem:** 667/722 memories (92%) had decayed to importance 0.01-0.02. The feedback loop was net-negative per session.

**Root cause:** Rehydrate domain briefing IDs (up to 10/session) were tracked alongside search results and submitted for feedback. Most failed the 0.35 cosine threshold → -0.02 penalty each. With 5 search + 10 rehydrate = 15 IDs and ~2 useful, net was -0.16/session.

**Changes:**
1. `recall-retrieve.js`: Tag entries with `source: "search"` vs `"rehydrate"`
2. `recall-session-summary.js`: Filter to only `source: "search"` for feedback
3. `memory.py`: Boost +0.05→+0.10, penalty -0.02→-0.01, penalty floor 0.01→0.05
4. `decay.py`: Importance floor 0.01→0.05 (both code paths)

**Measured effect:**
- Old net feedback (200 entries): +2.16 aggregate (barely positive)
- New net feedback (estimated): +8.35 aggregate (4x improvement)
- Rehabilitation: 240/559 memories recovered to 0.20-0.30 range
- Expected equilibrium: useful=+0.11/day, not-useful=0.00/day, unused=-0.01/day

**What to watch:** Monitor importance distribution over next 7 days. If memories still drift below 0.10, consider: (a) reducing decay frequency from 48x/day to 4-6x/day, (b) raising the 0.35 cosine threshold to 0.30 to count more memories as "useful".

---

### Pre-2026-02-19: Original values (for reference)

| Parameter | Original Value | Current Value |
|-----------|---------------|---------------|
| Useful boost | +0.05 | +0.10 |
| Not-useful penalty | -0.02 | -0.01 |
| Penalty importance floor | 0.01 | 0.05 |
| Decay importance floor | 0.01 | 0.05 |
| Rehydrate in feedback | Yes (all IDs) | No (search only) |

---

## How to Use This File

1. **Before changing any parameter:** Read its current value and history here
2. **After changing:** Add a dated entry to Change History with problem/cause/change/effect
3. **Include the math:** Show the expected net effect, not just the new value
4. **Monitor and follow up:** Note what to watch and when to revisit
