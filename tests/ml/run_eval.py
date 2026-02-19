"""
ML Eval Harness — measures P/R/F1 for Recall's ML systems on held-out data.

Usage:
    python -m tests.ml.run_eval
    python -m tests.ml.run_eval --include-llm    # also eval LLM detector (slow)
    python -m tests.ml.run_eval --output r.json   # custom output path
    python -m tests.ml.run_eval --split 0.3       # 70/30 split (default 80/20)

Evaluates:
    1. Signal Classifier (ML) — trained on split, tested on held-out
    2. Signal Classifier (baseline) — keyword heuristic comparison
    3. Reranker — synthetic/trained weights on curated eval dataset
    4. LLM Signal Detector (optional) — Ollama qwen3 comparison

Output: structured console report + JSON file.
"""

import argparse
import json
import math
import random
import time
from collections import defaultdict
from pathlib import Path

DATASETS_DIR = Path(__file__).parent / "datasets"
OLLAMA_URL = "http://192.168.50.62:11434"
MODEL = "qwen3:14b"


# ─── Core math ─────────────────────────────────────────────────────


def sigmoid(x: float) -> float:
    """Numerically stable sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    exp_x = math.exp(x)
    return exp_x / (1.0 + exp_x)


def compute_metrics(y_true: list[bool], y_pred: list[bool]) -> dict:
    """Compute precision, recall, F1, accuracy from boolean lists."""
    tp = sum(1 for t, p in zip(y_true, y_pred) if t and p)
    fp = sum(1 for t, p in zip(y_true, y_pred) if not t and p)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t and not p)
    tn = sum(1 for t, p in zip(y_true, y_pred) if not t and not p)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    accuracy = (tp + tn) / len(y_true) if y_true else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round(accuracy, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "total": len(y_true),
    }


# ─── Data loading ──────────────────────────────────────────────────


def load_all_corpus() -> list[dict]:
    """Load all *_corpus.json files from datasets directory."""
    samples = []
    for path in sorted(DATASETS_DIR.glob("*_corpus.json")):
        with open(path) as f:
            data = json.load(f)
        count = 0
        for s in data:
            if "turns" in s and len(s.get("turns", [])) >= 2:
                samples.append(s)
                count += 1
        print(f"  Loaded {count} samples from {path.name}")
    return samples


def load_curated_eval(filename: str) -> list[dict]:
    """Load a curated eval dataset."""
    with open(DATASETS_DIR / filename) as f:
        return json.load(f)


def stratified_split(
    samples: list[dict], test_ratio: float = 0.2, seed: int = 42
) -> tuple[list[dict], list[dict]]:
    """Split samples into train/test with stratification by is_signal."""
    rng = random.Random(seed)

    positives = [s for s in samples if s.get("is_signal", False)]
    negatives = [s for s in samples if not s.get("is_signal", False)]

    rng.shuffle(positives)
    rng.shuffle(negatives)

    n_pos_test = max(1, int(len(positives) * test_ratio))
    n_neg_test = max(1, int(len(negatives) * test_ratio))

    test = positives[:n_pos_test] + negatives[:n_neg_test]
    train = positives[n_pos_test:] + negatives[n_neg_test:]

    rng.shuffle(test)
    rng.shuffle(train)
    return train, test


# ─── Signal classifier training (self-contained) ──────────────────


def _tokenize(text: str) -> list[str]:
    """Simple whitespace/punctuation tokenizer."""
    import re

    return [t for t in re.split(r"\\W+", text.lower()) if len(t) > 1]


def train_classifier_local(
    train_data: list[dict],
) -> dict:
    """
    Train signal classifier on train split, return model dict.

    Uses the same architecture as signal_classifier_trainer.py but
    runs entirely in-process without Redis.
    """
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    from src.core.signal_classifier import (
        extract_conversation_features,
        tfidf_transform,
    )
    from src.core.signal_classifier_trainer import _build_vocabulary

    conversations = [s["turns"] for s in train_data]
    labels = [1 if s.get("is_signal", False) else 0 for s in train_data]
    signal_types = [
        s.get("signal_type", "none") if s.get("is_signal") else "none" for s in train_data
    ]

    all_texts = [" ".join(t.get("content", "") for t in conv) for conv in conversations]
    max_vocab = 1000 if len(conversations) > 200 else 500
    vocab, idf_weights = _build_vocabulary(all_texts, max_vocab=max_vocab)

    feat_rows = []
    for i, conv in enumerate(conversations):
        tfidf_vec = tfidf_transform(all_texts[i], vocab, idf_weights)
        conv_features = extract_conversation_features(conv)
        feat_rows.append(tfidf_vec + conv_features)

    features = np.array(feat_rows, dtype=np.float64)
    y_binary = np.array(labels, dtype=np.int32)

    scaler = StandardScaler()
    feat_scaled = scaler.fit_transform(features)

    binary_model = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)
    binary_model.fit(feat_scaled, y_binary)

    # Bake scaler into weights
    scale = scaler.scale_
    mean = scaler.mean_
    binary_w = (binary_model.coef_[0] / scale).tolist()
    binary_b = float(binary_model.intercept_[0] - np.sum(binary_model.coef_[0] * mean / scale))

    # Type classifier on positives
    positive_mask = y_binary == 1
    feat_pos = feat_scaled[positive_mask]
    types_pos = [signal_types[i] for i in range(len(labels)) if labels[i] == 1]

    type_classes = []
    type_weights = []
    type_biases = []

    if len(set(types_pos)) >= 2 and len(types_pos) >= 10:
        unique_types = sorted(set(types_pos))
        type_to_idx = {t: i for i, t in enumerate(unique_types)}
        y_type = np.array([type_to_idx[t] for t in types_pos], dtype=np.int32)

        type_model = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)
        type_model.fit(feat_pos, y_type)

        type_classes = unique_types
        for i in range(len(unique_types)):
            w_eff = (type_model.coef_[i] / scale).tolist()
            b_eff = float(type_model.intercept_[i] - np.sum(type_model.coef_[i] * mean / scale))
            type_weights.append(w_eff)
            type_biases.append(b_eff)

    return {
        "vocab": vocab,
        "idf_weights": idf_weights,
        "binary_weights": binary_w,
        "binary_bias": binary_b,
        "type_classes": type_classes,
        "type_weights": type_weights,
        "type_biases": type_biases,
        "n_train": len(train_data),
    }


# ─── Evaluators ────────────────────────────────────────────────────


def eval_ml_classifier(
    model: dict, test_data: list[dict], label: str = "ml_classifier"
) -> tuple[dict, dict]:
    """
    Evaluate ML classifier on test data.

    Returns (binary_metrics, type_metrics).
    """
    from src.core.signal_classifier import SignalClassifier

    clf = SignalClassifier(
        vocab=model["vocab"],
        idf_weights=model["idf_weights"],
        binary_weights=model["binary_weights"],
        binary_bias=model["binary_bias"],
        type_classes=model["type_classes"],
        type_weights=model["type_weights"],
        type_biases=model["type_biases"],
    )

    y_true = []
    y_pred = []
    type_true = []
    type_pred = []
    latencies = []

    for sample in test_data:
        turns = sample["turns"]
        expected = sample.get("is_signal", sample.get("expected_signal", False))
        expected_type = sample.get("signal_type", sample.get("expected_type"))

        t0 = time.perf_counter()
        result = clf.predict(turns)
        latencies.append((time.perf_counter() - t0) * 1000)

        y_true.append(expected)
        y_pred.append(result["is_signal"])

        if expected and expected_type and expected_type != "none":
            type_true.append(expected_type)
            type_pred.append(result.get("predicted_type"))

    binary = compute_metrics(y_true, y_pred)
    binary["model"] = label
    binary["avg_latency_ms"] = round(sum(latencies) / len(latencies), 3)
    binary["p95_latency_ms"] = round(sorted(latencies)[int(len(latencies) * 0.95)], 3)

    # Per-type metrics
    type_metrics = _per_type_metrics(type_true, type_pred)

    return binary, type_metrics


def eval_baseline(test_data: list[dict], label: str = "baseline_heuristic") -> tuple[dict, dict]:
    """Evaluate keyword heuristic baseline on test data."""
    signal_keywords = {
        "error",
        "fix",
        "bug",
        "crash",
        "fail",
        "decide",
        "let's",
        "should we",
        "always",
        "never",
        "prefer",
        "pattern",
        "notice",
        "workflow",
        "deploy",
        "process",
        "warning",
        "don't",
        "avoid",
        "server",
        "port",
        "host",
        "version",
        "config",
    }
    type_keywords = {
        "error_fix": ["error", "fix", "bug", "crash", "timeout", "failed"],
        "decision": ["decide", "should we", "let's use", "chose", "agreed"],
        "workflow": ["deploy", "process", "pipeline", "step", "command"],
        "fact": ["server", "port", "address", "ip", "host", "runs on"],
        "preference": ["prefer", "always", "never", "like", "default"],
        "pattern": ["pattern", "noticed", "every time", "recurring"],
        "warning": ["don't", "avoid", "dangerous", "vulnerability"],
        "contradiction": ["actually", "turns out", "was wrong", "outdated"],
    }

    y_true = []
    y_pred = []
    type_true = []
    type_pred = []

    for sample in test_data:
        turns = sample["turns"]
        expected = sample.get("is_signal", sample.get("expected_signal", False))
        expected_type = sample.get("signal_type", sample.get("expected_type"))

        text = " ".join(t["content"].lower() for t in turns)
        word_count = len(text.split())
        hits = sum(1 for kw in signal_keywords if kw in text)
        predicted = hits >= 2 and word_count >= 20

        y_true.append(expected)
        y_pred.append(predicted)

        if expected and expected_type and expected_type != "none":
            type_true.append(expected_type)
            # Guess type via keywords
            scores: dict[str, int] = defaultdict(int)
            for stype, kws in type_keywords.items():
                for kw in kws:
                    if kw in text:
                        scores[stype] += 1
            pred_type = max(scores, key=scores.get) if scores else None
            type_pred.append(pred_type if predicted else None)

    binary = compute_metrics(y_true, y_pred)
    binary["model"] = label
    type_metrics = _per_type_metrics(type_true, type_pred)
    return binary, type_metrics


def eval_reranker(
    dataset: list[dict],
    weights: list[float] | None = None,
    bias: float | None = None,
) -> dict:
    """Evaluate reranker on feature vectors."""
    if weights is None:
        weights = [
            1.5,
            0.8,
            0.8,
            0.5,
            -0.01,
            -0.005,
            0.6,
            0.5,
            1.5,
            0.4,
            -0.1,
        ]
    if bias is None:
        bias = -2.0

    y_true = []
    y_pred = []
    for sample in dataset:
        features = sample["features"]
        expected = sample["expected_useful"]
        dot = sum(w * f for w, f in zip(weights, features)) + bias
        y_true.append(expected)
        y_pred.append(sigmoid(dot) > 0.5)

    metrics = compute_metrics(y_true, y_pred)
    metrics["model"] = "reranker"
    metrics["n_features"] = len(weights)
    return metrics


async def eval_llm_detector(test_data: list[dict]) -> dict:
    """Evaluate LLM signal detector on test data (slow)."""
    import httpx

    y_true = []
    y_pred = []
    latencies = []

    prompt_template = (
        "Analyze this developer conversation. Does it contain a memorable "
        "signal worth storing? (bug fix, decision, pattern, fact, workflow, "
        "warning, etc.)\n\nConversation:\n{conversation}\n\n"
        'Return JSON: {{"is_signal": true/false, "signal_type": "..."}}'
    )

    async with httpx.AsyncClient() as client:
        for sample in test_data:
            turns = sample["turns"]
            expected = sample.get("is_signal", sample.get("expected_signal", False))
            conv_text = "\n".join(f"[{t['role']}] {t['content'][:200]}" for t in turns)
            prompt = prompt_template.format(conversation=conv_text)

            t0 = time.perf_counter()
            try:
                resp = await client.post(
                    f"{OLLAMA_URL}/api/generate",
                    json={
                        "model": MODEL,
                        "prompt": prompt,
                        "stream": False,
                        "think": False,
                        "format": "json",
                        "options": {"temperature": 0.1, "num_predict": 100},
                    },
                    timeout=60.0,
                )
                resp.raise_for_status()
                raw = resp.json().get("response", "")
                parsed = json.loads(raw)
                predicted = parsed.get("is_signal", False)
            except Exception:
                predicted = False
            latencies.append((time.perf_counter() - t0) * 1000)

            y_true.append(expected)
            y_pred.append(predicted)

            done = len(y_true)
            if done % 10 == 0:
                print(f"  LLM: {done}/{len(test_data)} evaluated")

    metrics = compute_metrics(y_true, y_pred)
    metrics["model"] = "llm_detector"
    if latencies:
        metrics["avg_latency_ms"] = round(sum(latencies) / len(latencies), 1)
        metrics["p95_latency_ms"] = round(sorted(latencies)[int(len(latencies) * 0.95)], 1)
    return metrics


# ─── Per-type metrics ──────────────────────────────────────────────


def _per_type_metrics(type_true: list[str], type_pred: list[str | None]) -> dict:
    """Compute per-type P/R/F1."""
    all_types = sorted(set(type_true))
    result = {}

    for t in all_types:
        tp = sum(1 for tr, pr in zip(type_true, type_pred) if tr == t and pr == t)
        fp = sum(1 for tr, pr in zip(type_true, type_pred) if tr != t and pr == t)
        fn = sum(1 for tr, pr in zip(type_true, type_pred) if tr == t and pr != t)
        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0
        support = sum(1 for tr in type_true if tr == t)
        result[t] = {
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(f1, 4),
            "support": support,
        }

    # Macro averages
    if result:
        avg_p = sum(v["precision"] for v in result.values()) / len(result)
        avg_r = sum(v["recall"] for v in result.values()) / len(result)
        avg_f1 = sum(v["f1"] for v in result.values()) / len(result)
        result["_macro_avg"] = {
            "precision": round(avg_p, 4),
            "recall": round(avg_r, 4),
            "f1": round(avg_f1, 4),
            "support": len(type_true),
        }

    return result


# ─── Output formatting ─────────────────────────────────────────────


def format_binary_table(results: list[dict]) -> str:
    """Format binary classification results as console table."""
    lines = []
    header = (
        f"{'Model':<28} {'P':>6} {'R':>6} {'F1':>6} "
        f"{'Acc':>6} {'TP':>4} {'FP':>4} {'FN':>4} {'TN':>4} {'N':>4}"
    )
    lines.append(header)
    lines.append("-" * len(header))

    for r in results:
        line = (
            f"{r['model']:<28} "
            f"{r['precision']:>6.3f} {r['recall']:>6.3f} "
            f"{r['f1']:>6.3f} {r['accuracy']:>6.3f} "
            f"{r['tp']:>4d} {r['fp']:>4d} "
            f"{r['fn']:>4d} {r['tn']:>4d} {r['total']:>4d}"
        )
        lines.append(line)

    return "\n".join(lines)


def format_type_table(type_metrics: dict) -> str:
    """Format per-type metrics as console table."""
    lines = []
    header = f"{'Type':<20} {'P':>6} {'R':>6} {'F1':>6} {'N':>4}"
    lines.append(header)
    lines.append("-" * len(header))

    for t, m in sorted(type_metrics.items()):
        if t.startswith("_"):
            continue
        lines.append(
            f"{t:<20} {m['precision']:>6.3f} {m['recall']:>6.3f} {m['f1']:>6.3f} {m['support']:>4d}"
        )

    if "_macro_avg" in type_metrics:
        avg = type_metrics["_macro_avg"]
        lines.append("-" * len(header))
        lines.append(
            f"{'MACRO AVG':<20} {avg['precision']:>6.3f} "
            f"{avg['recall']:>6.3f} {avg['f1']:>6.3f} {avg['support']:>4d}"
        )

    return "\n".join(lines)


# ─── Main ──────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Recall ML Eval Harness")
    parser.add_argument(
        "--include-llm",
        action="store_true",
        help="Include LLM signal detector eval (slow, needs Ollama)",
    )
    parser.add_argument(
        "--split",
        type=float,
        default=0.2,
        help="Test split ratio (default: 0.2 = 80/20)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSON report path",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("RECALL ML EVAL HARNESS")
    print("=" * 70)

    # ── Step 1: Load corpus ──
    print("\n[1/5] Loading corpus data...")
    corpus = load_all_corpus()
    if not corpus:
        print("ERROR: No corpus data found in datasets/")
        return

    n_sig = sum(1 for s in corpus if s.get("is_signal"))
    n_nonsig = len(corpus) - n_sig
    print(f"  Total: {len(corpus)} (signals: {n_sig}, non-signals: {n_nonsig})")

    # ── Step 2: Train/test split ──
    print(f"\n[2/5] Stratified split ({1 - args.split:.0%} / {args.split:.0%})...")
    train, test = stratified_split(corpus, test_ratio=args.split)
    train_sig = sum(1 for s in train if s.get("is_signal"))
    test_sig = sum(1 for s in test if s.get("is_signal"))
    print(f"  Train: {len(train)} (signals: {train_sig}, non-signals: {len(train) - train_sig})")
    print(f"  Test:  {len(test)} (signals: {test_sig}, non-signals: {len(test) - test_sig})")

    # ── Step 3: Train ML classifier ──
    print("\n[3/5] Training ML signal classifier on train split...")
    t0 = time.time()
    model = train_classifier_local(train)
    train_time = time.time() - t0
    print(f"  Trained in {train_time:.1f}s (vocab: {len(model['vocab'])})")

    # ── Step 4: Evaluate ──
    print("\n[4/5] Evaluating on held-out test split...")
    results = []

    # ML classifier
    ml_binary, ml_types = eval_ml_classifier(model, test, "ml_classifier")
    results.append(ml_binary)

    # Baseline heuristic
    bl_binary, bl_types = eval_baseline(test, "baseline_heuristic")
    results.append(bl_binary)

    # Reranker (curated eval dataset)
    reranker_path = DATASETS_DIR / "reranker_eval.json"
    if reranker_path.exists():
        with open(reranker_path) as f:
            reranker_data = json.load(f)
        reranker_metrics = eval_reranker(reranker_data)
        results.append(reranker_metrics)

    # Also eval ML + baseline on curated signal_eval.json
    curated_results = []
    for filename in ["signal_eval.json", "classifier_eval.json"]:
        curated_path = DATASETS_DIR / filename
        if not curated_path.exists():
            continue
        curated = load_curated_eval(filename)
        c_ml, _ = eval_ml_classifier(model, curated, f"ml_{filename}")
        c_bl, _ = eval_baseline(curated, f"bl_{filename}")
        curated_results.extend([c_ml, c_bl])

    # LLM detector (optional)
    llm_metrics = None
    if args.include_llm:
        import asyncio

        print("\n  Evaluating LLM detector (this will take a while)...")
        llm_metrics = asyncio.run(eval_llm_detector(test))
        results.append(llm_metrics)

    # ── Step 5: Report ──
    print("\n" + "=" * 70)
    print("HELD-OUT TEST RESULTS")
    print("=" * 70)
    print(format_binary_table(results))

    # Latency info
    for r in results:
        if "avg_latency_ms" in r:
            print(
                f"\n  {r['model']} latency: "
                f"avg={r['avg_latency_ms']:.1f}ms, "
                f"p95={r['p95_latency_ms']:.1f}ms"
            )

    # ML improvement over baseline
    ml_f1 = ml_binary["f1"]
    bl_f1 = bl_binary["f1"]
    delta = ml_f1 - bl_f1
    pct = (delta / bl_f1 * 100) if bl_f1 > 0 else 0
    print(f"\n  ML vs Baseline: F1 {bl_f1:.3f} -> {ml_f1:.3f} ({pct:+.1f}%)")

    # Per-type breakdown
    if ml_types:
        print(f"\n{'ML CLASSIFIER — PER-TYPE METRICS':}")
        print("-" * 42)
        print(format_type_table(ml_types))

    if bl_types:
        print(f"\n{'BASELINE — PER-TYPE METRICS':}")
        print("-" * 42)
        print(format_type_table(bl_types))

    # Curated eval results
    if curated_results:
        print(f"\n{'CURATED EVAL DATASETS':}")
        print("-" * 70)
        print(format_binary_table(curated_results))

    # Build JSON report
    report = {
        "corpus_size": len(corpus),
        "train_size": len(train),
        "test_size": len(test),
        "split_ratio": args.split,
        "train_time_s": round(train_time, 2),
        "held_out": {
            "ml_binary": ml_binary,
            "ml_per_type": ml_types,
            "baseline_binary": bl_binary,
            "baseline_per_type": bl_types,
        },
        "reranker": results[-1] if reranker_path.exists() else None,
        "curated": curated_results,
    }
    if llm_metrics:
        report["llm_detector"] = llm_metrics

    output_path = args.output or str(DATASETS_DIR.parent / "eval_report.json")
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to: {output_path}")


if __name__ == "__main__":
    main()
