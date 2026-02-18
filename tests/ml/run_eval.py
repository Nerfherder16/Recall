"""
ML Eval Harness — measures P/R/F1 for Recall's ML systems.

Usage:
    python -m tests.ml.run_eval
    python -m tests.ml.run_eval --include-llm   # also eval signal detector (slow, needs Ollama)

Evaluates:
    1. Reranker (logistic regression): feature vector → useful/not_useful
    2. Signal classifier (if trained): conversation → is_signal + type
    3. Signal detector (LLM, optional): conversation → extracted signals

Output: JSON report + console table.
"""

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

DATASETS_DIR = Path(__file__).parent / "datasets"


def sigmoid(x: float) -> float:
    """Numerically stable sigmoid — matches reranker.py."""
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


def eval_reranker(
    dataset: list[dict], weights: list[float] | None = None, bias: float | None = None
) -> dict:
    """Evaluate reranker on feature vectors.

    Uses synthetic weights if none provided (default: equal weight per feature).
    """
    if weights is None:
        # Synthetic weights: positive for quality signals, negative for staleness
        weights = [
            1.5,  # importance
            0.8,  # stability
            0.8,  # confidence
            0.5,  # log1p_access_count
            -0.01,  # hours_since_last_access
            -0.005,  # hours_since_creation
            0.6,  # is_pinned
            0.5,  # durability_score
            1.5,  # similarity (highest weight)
            0.4,  # has_graph_path
            -0.1,  # retrieval_path_len (shorter = better)
        ]
    if bias is None:
        bias = -2.0

    y_true = []
    y_pred = []

    for sample in dataset:
        features = sample["features"]
        expected = sample["expected_useful"]

        dot = sum(w * f for w, f in zip(weights, features)) + bias
        prob = sigmoid(dot)
        predicted = prob > 0.5

        y_true.append(expected)
        y_pred.append(predicted)

    metrics = compute_metrics(y_true, y_pred)
    metrics["model"] = "reranker"
    metrics["n_features"] = len(weights)
    return metrics


def eval_signal_classifier(dataset: list[dict]) -> dict:
    """Evaluate signal classification using simple heuristics as baseline.

    Since the ML signal classifier may not be trained, this uses a
    rule-based baseline: conversations with technical keywords and
    sufficient length are likely signals.
    """
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
        "keep hitting",
        "workflow",
        "deploy",
        "process",
        "warning",
        "don't",
        "avoid",
        "server",
        "port",
        "host",
        "address",
        "version",
        "config",
    }

    y_true = []
    y_pred = []
    type_true = []
    type_pred = []

    for sample in dataset:
        turns = sample["turns"]
        expected = sample["expected_signal"]
        expected_type = sample.get("expected_type")

        # Flatten turns to text
        text = " ".join(t["content"].lower() for t in turns)
        word_count = len(text.split())
        keyword_hits = sum(1 for kw in signal_keywords if kw in text)

        # Heuristic: signal if enough keywords and sufficient length
        predicted = keyword_hits >= 2 and word_count >= 20

        y_true.append(expected)
        y_pred.append(predicted)

        if expected_type:
            type_true.append(expected_type)
            type_pred.append(_guess_type(text) if predicted else None)

    binary_metrics = compute_metrics(y_true, y_pred)
    binary_metrics["model"] = "signal_classifier_baseline"

    # Per-type accuracy (only for true positives)
    type_correct = sum(1 for t, p in zip(type_true, type_pred) if t == p)
    type_total = len(type_true)
    binary_metrics["type_accuracy"] = round(type_correct / type_total, 4) if type_total > 0 else 0.0
    binary_metrics["type_total"] = type_total

    return binary_metrics


def _guess_type(text: str) -> str | None:
    """Simple keyword-based type classification."""
    type_keywords = {
        "error_fix": ["error", "fix", "bug", "crash", "timeout", "failed"],
        "decision": ["decide", "should we", "let's use", "let's go with", "chose", "agreed"],
        "workflow": ["deploy", "process", "pipeline", "step", "command", "run"],
        "fact": ["server", "port", "address", "ip", "host", "runs on", "located"],
        "preference": ["prefer", "always", "never", "like", "want", "default"],
        "pattern": ["pattern", "keep hitting", "noticed", "every time", "recurring", "common"],
        "warning": ["never", "don't", "avoid", "dangerous", "security", "vulnerability"],
    }

    scores = defaultdict(int)
    for signal_type, keywords in type_keywords.items():
        for kw in keywords:
            if kw in text:
                scores[signal_type] += 1

    if not scores:
        return None
    return max(scores, key=scores.get)


def format_table(results: list[dict]) -> str:
    """Format results as a console table."""
    lines = []
    cols = f"{'P':>6} {'R':>6} {'F1':>6} {'Acc':>6}"
    counts = f"{'TP':>4} {'FP':>4} {'FN':>4} {'TN':>4} {'N':>4}"
    header = f"{'Model':<30} {cols} {counts}"
    lines.append(header)
    lines.append("-" * len(header))

    for r in results:
        line = (
            f"{r['model']:<30} "
            f"{r['precision']:>6.3f} "
            f"{r['recall']:>6.3f} "
            f"{r['f1']:>6.3f} "
            f"{r['accuracy']:>6.3f} "
            f"{r['tp']:>4d} "
            f"{r['fp']:>4d} "
            f"{r['fn']:>4d} "
            f"{r['tn']:>4d} "
            f"{r['total']:>4d}"
        )
        lines.append(line)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Recall ML Eval Harness")
    parser.add_argument(
        "--include-llm", action="store_true", help="Include LLM signal detector eval (slow)"
    )
    parser.add_argument("--output", type=str, default=None, help="Output JSON report path")
    args = parser.parse_args()

    results = []

    # 1. Reranker eval
    print("Evaluating reranker...")
    with open(DATASETS_DIR / "reranker_eval.json") as f:
        reranker_data = json.load(f)
    reranker_metrics = eval_reranker(reranker_data)
    results.append(reranker_metrics)

    # 2. Signal classifier eval (both datasets)
    print("Evaluating signal classifier (baseline)...")
    for name, filename in [
        ("signal_eval", "signal_eval.json"),
        ("classifier_eval", "classifier_eval.json"),
    ]:
        with open(DATASETS_DIR / filename) as f:
            data = json.load(f)
        metrics = eval_signal_classifier(data)
        metrics["model"] = f"signal_baseline_{name}"
        results.append(metrics)

    # 3. LLM signal detector (optional)
    if args.include_llm:
        print("LLM eval not yet implemented — skipping.")

    # Print report
    print("\n" + "=" * 70)
    print("RECALL ML EVAL REPORT")
    print("=" * 70)
    print(format_table(results))
    print()

    # Type accuracy
    for r in results:
        if "type_accuracy" in r:
            acc = r["type_accuracy"]
            n = r["type_total"]
            print(f"  {r['model']} type accuracy: {acc:.1%} ({n} samples)")

    # Save JSON report
    output_path = args.output or str(DATASETS_DIR.parent / "eval_report.json")
    report = {"results": results}
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to: {output_path}")


if __name__ == "__main__":
    main()
