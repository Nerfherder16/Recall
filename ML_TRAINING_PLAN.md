# ML Training Data Plan — Signal Classifier Diversification

**Goal**: Go from 68 homogeneous training samples to 500+ diverse samples spanning real-world developer usage patterns. Make the classifier production-ready, not just "Tim-tuned."

**Current baseline**: Binary CV F1 = 0.871, Type CV F1 = 0.353 (68 samples, 27 signal / 41 non-signal)

---

## Stage 1: LLM Corpus Generator (~500 synthetic samples)

**Script**: `tests/ml/generate_corpus.py`
**Output**: `tests/ml/datasets/generated_corpus.json`

### Matrix Design
Generate conversations by crossing:

| Dimension | Values | Count |
|-----------|--------|-------|
| Languages | Python, JavaScript/TypeScript, Rust, Go, Java, C#, Ruby, Shell/Bash | 8 |
| Domains | web-api, frontend, infrastructure, database, security, ml-data, mobile, devops-ci, testing, systems | 10 |
| Signal Types | error_fix, decision, pattern, preference, fact, workflow, contradiction, warning | 8 |
| Non-signals | greetings, status checks, simple commands, file reads, chitchat, confirmations | 6 categories |

### Generation Strategy
- **Signal conversations** (positives): 8 types x 10 domains x ~3 variations = ~240 samples
  - Each prompt specifies: language, domain, signal type, conversation length (3-8 turns)
  - LLM generates realistic developer<->assistant exchange
- **Non-signal conversations** (negatives): ~260 samples
  - Short greetings, file operations, "run tests", confirmations, off-topic
  - Mix of 1-turn and 2-turn exchanges
  - Deliberately include technical-sounding non-signals (avoid easy negatives)
- **Hard negatives**: ~50 of the non-signals should look technical but contain no memorable signal
  - "Show me the file", "Run the linter", "What's in this directory?"

### Quality Controls
- Reject responses < 50 chars total or > 5000 chars
- Reject if LLM returns malformed JSON
- Validate turn structure: alternating user/assistant roles
- Deduplicate by content similarity (simple jaccard on tokens)
- Target ratio: ~45% signal, ~55% non-signal

### Execution
- Use Ollama qwen3:14b at 192.168.50.62:11434
- Batch with asyncio.Semaphore(2) to avoid saturation
- ~500 conversations, ~2-5s per generation = ~20-40 min total
- Save with metadata: `{turns, is_signal, signal_type, language, domain, source: "llm_generated"}`

---

## Stage 2: Public Dataset Integration (~200-300 real samples)

**Script**: `tests/ml/import_public_data.py`
**Output**: `tests/ml/datasets/public_corpus.json`

### Source: LMSYS-Chat-1M or WildChat (Hugging Face)
- Both are freely available conversation datasets with real user<->AI exchanges
- Filter for coding/technical conversations using keyword heuristics
- Already in the right turn format (role + content)

### Pipeline
1. **Download**: Fetch a subset (parquet file, ~1GB) via `huggingface_hub` or direct URL
2. **Filter**: Keep conversations where content contains code indicators:
   - Backticks, `def `, `function `, `class `, `import `, `error`, `bug`, `deploy`
   - Minimum 2 turns, maximum 20 turns
   - English language (simple heuristic: ASCII ratio > 0.9)
3. **Label**: Two-pass labeling:
   - **Pass 1 — Heuristic**: keyword density scoring (same logic as eval harness baseline)
   - **Pass 2 — LLM verification**: Send borderline cases (score 0.3-0.7) to qwen3 for label confirmation
4. **Type classification**: LLM classifies signal type for positives
5. **Dedup**: Remove near-duplicates (jaccard > 0.8)
6. **Sample**: Take 200-300 balanced samples (mix of signals and non-signals)

### Quality Controls
- Strip PII (emails, names) with regex
- Truncate conversations > 10 turns to last 10
- Remove conversations with non-English content
- Validate JSON structure

---

## Stage 3: Merge, Train & Evaluate

**Script**: Updates to `signal_classifier_trainer.py` + eval run
**Output**: Retrained model on live server, eval report comparison

### Merge Strategy
1. Load all sources:
   - `generated_corpus.json` (Stage 1, ~500 samples)
   - `public_corpus.json` (Stage 2, ~200-300 samples)
   - Existing corpus (conversation_turns.py + marathon, 68 samples)
2. Combined: ~770-870 samples
3. Deduplicate across sources
4. Stratified split: 80% train, 20% test (held-out, never seen during training)

### Trainer Updates
- `signal_classifier_trainer.py`: Add `load_dataset_files()` that reads from `tests/ml/datasets/*.json`
- Support `source` field for tracking provenance
- Increase `max_vocab` from 500 to 1000 (more diverse text needs bigger vocabulary)
- Add per-source metrics in training report

### Evaluation
1. Run eval harness before and after:
   - Binary: P / R / F1 / Accuracy
   - Per-type: P / R / F1
   - Per-source: does model generalize across sources?
2. Targets:
   - Binary F1 > 0.85 (on held-out test set, not CV)
   - Type F1 > 0.60 (up from 0.35)
   - Latency stays < 1ms per prediction
3. Deploy to live server, retrain, verify status endpoint

### Before/After Comparison Table — FINAL RESULTS (2026-02-19)
```
Metric              | Before (68)  | Stage 3 (831) | Stage 4 (1209) | Delta (total)
--------------------|--------------|----------------|----------------|-------------
Binary CV F1        | 0.871        | 0.940          | 0.943          | +8.3%
Type CV F1          | 0.353        | 0.604          | 0.649          | +84%
Curated eval F1     | —            | 0.240          | 0.884          | +268% (!)
Per-type macro F1   | —            | 0.520          | 0.793          | +52.5%
Vocab size          | 500          | 1,000          | 1,000          | 2x
Samples             | 68           | 831            | 1,209          | 18x
```

### Data Sources Breakdown
| Source | Samples | Type |
|--------|---------|------|
| Hand-labeled (TEST_CONVERSATIONS + marathon) | 28 | High quality |
| Synthetic negatives | 40 | Medium |
| LLM-generated corpus (Stage 1) | 463 | Diverse, verbose |
| ShareGPT52K public (Stage 2) | 300 | Real-world, verbose |
| Realistic Claude Code corpus (Stage 4) | 378 | Short, terse, production-like |
| **Total** | **1,209** | |

### Stage Progression
| Stage | Samples | Binary F1 | Type F1 | Curated F1 | Notes |
|-------|---------|-----------|---------|------------|-------|
| Baseline | 68 | 0.871 | 0.353 | — | Tim-only data |
| +Stage 1 | 531 | 0.929 | 0.619 | — | +LLM-generated corpus |
| +Stage 2 | 831 | 0.940 | 0.604 | 0.240 | +ShareGPT52K public data |
| +Stage 4 | 1,209 | 0.943 | 0.649 | 0.884 | +Realistic corpus (generalization fix) |

### Per-Type Improvement (Stage 2 → Stage 4)
| Type | Before | After | Delta |
|------|--------|-------|-------|
| pattern | 0.250 | 0.824 | +230% |
| preference | 0.182 | 0.615 | +238% |
| error_fix | 0.316 | 0.762 | +141% |
| workflow | 0.545 | 0.762 | +40% |
| decision | 0.615 | 0.800 | +30% |
| warning | 0.667 | 0.818 | +23% |
| fact | 0.760 | 0.766 | +1% |
| contradiction | 0.824 | 1.000 | +21% |
| **Macro avg** | **0.520** | **0.793** | **+52.5%** |

---

## Stage 4: Realistic Corpus (Generalization Fix) — COMPLETE

**Script**: `tests/ml/generate_realistic_corpus.py`
**Output**: `tests/ml/datasets/realistic_corpus.json` (378 samples)

### Problem
Eval harness revealed a generalization gap: F1 0.986 on held-out corpus data vs F1 0.240 on curated eval data. Root cause: training data was verbose (avg 177-703 chars/turn) while real Claude Code sessions are terse (avg 67 chars/turn).

### Solution
Hybrid template + LLM generator producing short, terse conversations matching Claude Code session style:
- Template signals: `SIGNAL_SCENARIOS` with placeholder filling (instant, no LLM)
- LLM signals: strict prompt enforcing 2-4 turns, 10-80 char user messages, <500 chars total
- Hard negatives: technical-looking but non-signal conversations
- 3x weight on weak types: error_fix, pattern, preference
- Length enforcement: user turns ≤150 chars, assistant ≤300 chars, total ≤1500 chars

### Results
- 378 samples, avg 93 chars/conv, avg 2.7 turns (matches production profile)
- Curated eval F1: 0.240 → 0.884 (+268%)
- Per-type macro F1: 0.520 → 0.793 (+52.5%)
- Held-out F1 maintained: 0.960 (down from 0.986, acceptable)

---

## Execution Order — ALL COMPLETE
1. **Stage 1** — LLM corpus generator: 463 samples across 8 languages x 10 domains x 8 signal types
2. **Stage 2** — ShareGPT52K import: 300 real-world coding conversations (CC0-1.0)
3. **Stage 3** — Merged, retrained, deployed to live server (192.168.50.19:8200)
4. **Stage 4** — Realistic corpus: 378 short/terse samples, closed generalization gap, deployed
