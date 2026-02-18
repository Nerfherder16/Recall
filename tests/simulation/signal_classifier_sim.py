"""
Signal Classifier Validation Simulation.

Standalone script — no API dependency for training.

Usage:
    python -m tests.simulation.signal_classifier_sim

Workflow:
    1. Load labeled data (TEST_CONVERSATIONS + MARATHON CONVERSATIONS)
    2. Generate synthetic negatives from MEMORIES corpus
    3. Train/test split (70/30 stratified)
    4. Fit TF-IDF + train binary classifier + type classifier
    5. Evaluate on held-out test set
    6. Latency benchmark (ML predict time)
    7. Print structured report + save JSON
"""

import json
import math
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure project root is on path
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.signal_classifier import (
    CONV_FEATURE_NAMES,
    SignalClassifier,
    _tokenize,
    extract_conversation_features,
    tfidf_transform,
)
from src.core.signal_classifier_trainer import (
    _build_vocabulary,
    _infer_signal_type,
    collect_training_data_from_corpus,
    generate_synthetic_negatives,
)


def run_simulation() -> dict:
    """Run the full signal classifier validation simulation."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import (
        accuracy_score,
        classification_report,
        confusion_matrix,
        f1_score,
        precision_score,
        recall_score,
    )
    from sklearn.model_selection import cross_val_score, train_test_split
    from sklearn.preprocessing import StandardScaler
    import numpy as np

    print("=" * 60)
    print("Signal Classifier Validation Simulation")
    print("=" * 60)

    # 1. Load labeled data
    print("\n[1/7] Loading labeled data...")
    conversations, labels, signal_types = collect_training_data_from_corpus()
    print(f"  Corpus conversations: {len(conversations)}")
    print(f"  Signals: {sum(labels)}, Non-signals: {len(labels) - sum(labels)}")

    # 2. Generate synthetic negatives
    print("\n[2/7] Generating synthetic negatives...")
    negatives = generate_synthetic_negatives(40)
    for neg in negatives:
        conversations.append(neg)
        labels.append(0)
        signal_types.append("none")
    print(f"  Total samples: {len(conversations)}")
    print(f"  Signals: {sum(labels)}, Non-signals: {len(labels) - sum(labels)}")

    # Type distribution
    type_dist: dict[str, int] = {}
    for t in signal_types:
        type_dist[t] = type_dist.get(t, 0) + 1
    print(f"  Type distribution: {json.dumps(type_dist, indent=2)}")

    # 3. Build features
    print("\n[3/7] Building TF-IDF features...")
    all_texts = [
        " ".join(t.get("content", "") for t in conv)
        for conv in conversations
    ]
    vocab, idf_weights = _build_vocabulary(all_texts, max_vocab=500)
    print(f"  Vocabulary size: {len(vocab)}")

    X_list: list[list[float]] = []
    for i, conv in enumerate(conversations):
        text = all_texts[i]
        tfidf_vec = tfidf_transform(text, vocab, idf_weights)
        conv_features = extract_conversation_features(conv)
        X_list.append(tfidf_vec + conv_features)

    X = np.array(X_list, dtype=np.float64)
    y_binary = np.array(labels, dtype=np.int32)
    print(f"  Feature vector size: {X.shape[1]} ({len(vocab)} TF-IDF + {len(CONV_FEATURE_NAMES)} conv)")

    # 4. Train/test split
    print("\n[4/7] Train/test split (70/30)...")
    X_train, X_test, y_train, y_test, idx_train, idx_test = train_test_split(
        X, y_binary, np.arange(len(y_binary)),
        test_size=0.3, stratify=y_binary, random_state=42,
    )
    print(f"  Train: {len(X_train)} samples")
    print(f"  Test: {len(X_test)} samples")

    # Scale
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    # 5. Train binary classifier
    print("\n[5/7] Training binary classifier...")
    binary_model = LogisticRegression(
        class_weight="balanced", max_iter=1000, random_state=42,
    )
    binary_model.fit(X_train_s, y_train)

    # Cross-val
    n_folds = 5 if len(X_train) >= 50 else 3
    cv_scores = cross_val_score(binary_model, X_train_s, y_train, cv=n_folds, scoring="f1")
    print(f"  CV F1 scores: {[round(s, 3) for s in cv_scores]}")
    print(f"  Mean CV F1: {cv_scores.mean():.3f} (+/- {cv_scores.std():.3f})")

    # Evaluate on test set
    y_pred = binary_model.predict(X_test_s)
    y_proba = binary_model.predict_proba(X_test_s)[:, 1]

    binary_accuracy = accuracy_score(y_test, y_pred)
    binary_precision = precision_score(y_test, y_pred, zero_division=0)
    binary_recall = recall_score(y_test, y_pred, zero_division=0)
    binary_f1 = f1_score(y_test, y_pred, zero_division=0)

    print(f"\n  Binary Test Results:")
    print(f"    Accuracy:  {binary_accuracy:.3f}")
    print(f"    Precision: {binary_precision:.3f}")
    print(f"    Recall:    {binary_recall:.3f}")
    print(f"    F1:        {binary_f1:.3f}")

    cm = confusion_matrix(y_test, y_pred)
    print(f"\n  Confusion Matrix:")
    print(f"    TN={cm[0][0]:3d}  FP={cm[0][1]:3d}")
    print(f"    FN={cm[1][0]:3d}  TP={cm[1][1]:3d}")

    # 6. Train type classifier on positives
    print("\n[6/7] Training type classifier...")
    types_train = [signal_types[i] for i in idx_train if labels[i] == 1]
    types_test = [signal_types[i] for i in idx_test if labels[i] == 1]
    X_pos_train = X_train_s[y_train == 1]
    X_pos_test = X_test_s[y_test == 1]

    type_f1 = 0.0
    type_report_str = "N/A (insufficient data)"

    if len(set(types_train)) >= 2 and len(types_train) >= 5:
        unique_types = sorted(set(types_train))
        type_to_idx = {t: i for i, t in enumerate(unique_types)}
        y_type_train = np.array([type_to_idx[t] for t in types_train])

        type_model = LogisticRegression(
            class_weight="balanced",
            max_iter=1000, random_state=42,
        )
        type_model.fit(X_pos_train, y_type_train)

        if len(types_test) > 0:
            # Filter test types to only those seen in training
            valid_test = [
                (i, t) for i, t in enumerate(types_test) if t in type_to_idx
            ]
            if valid_test:
                valid_idx, valid_types = zip(*valid_test)
                y_type_test = np.array([type_to_idx[t] for t in valid_types])
                X_type_test = X_pos_test[list(valid_idx)]
                y_type_pred = type_model.predict(X_type_test)

                type_report_str = classification_report(
                    y_type_test, y_type_pred,
                    target_names=[unique_types[i] for i in sorted(set(y_type_test))],
                    zero_division=0,
                )
                type_f1 = f1_score(y_type_test, y_type_pred, average="weighted", zero_division=0)

        print(f"  Type classes: {unique_types}")
        print(f"  Type F1 (weighted): {type_f1:.3f}")
        print(f"\n  Type Classification Report:")
        print(f"  {type_report_str}")
    else:
        print(f"  Skipped — insufficient type variety in training set")
        print(f"  Types in training: {set(types_train)}")

    # 7. Bake weights and benchmark latency
    print("\n[7/7] Latency benchmark...")

    # Bake scaler into weights
    coef_b = binary_model.coef_[0]
    intercept_b = binary_model.intercept_[0]
    scale = scaler.scale_
    mean = scaler.mean_
    binary_w = (coef_b / scale).tolist()
    binary_b = float(intercept_b - np.sum(coef_b * mean / scale))

    classifier = SignalClassifier(
        vocab=vocab,
        idf_weights=idf_weights,
        binary_weights=binary_w,
        binary_bias=binary_b,
        type_classes=[],
        type_weights=[],
        type_biases=[],
    )

    # Benchmark on all conversations
    latencies = []
    for conv in conversations:
        start = time.perf_counter()
        classifier.predict(conv)
        elapsed = (time.perf_counter() - start) * 1000  # ms
        latencies.append(elapsed)

    avg_latency = sum(latencies) / len(latencies)
    p50_latency = sorted(latencies)[len(latencies) // 2]
    p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
    max_latency = max(latencies)

    print(f"  Predictions: {len(latencies)}")
    print(f"  Avg latency: {avg_latency:.2f}ms")
    print(f"  P50 latency: {p50_latency:.2f}ms")
    print(f"  P95 latency: {p95_latency:.2f}ms")
    print(f"  Max latency: {max_latency:.2f}ms")

    # Misclassification analysis
    print("\n" + "=" * 60)
    print("Misclassification Analysis")
    print("=" * 60)

    for i, idx in enumerate(idx_test):
        if y_pred[i] != y_test[i]:
            conv = conversations[idx]
            first_turn = conv[0].get("content", "")[:80]
            actual = "signal" if y_test[i] == 1 else "no_signal"
            predicted = "signal" if y_pred[i] == 1 else "no_signal"
            print(f"  [{actual} -> {predicted}] P={y_proba[i]:.3f} | {first_turn}...")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    passed = binary_f1 >= 0.80 and avg_latency < 50.0
    print(f"  Binary F1:    {binary_f1:.3f} {'PASS' if binary_f1 >= 0.80 else 'FAIL'} (target >= 0.80)")
    print(f"  Type F1:      {type_f1:.3f}")
    print(f"  Avg Latency:  {avg_latency:.2f}ms {'PASS' if avg_latency < 50 else 'FAIL'} (target < 50ms)")
    print(f"  Vocab Size:   {len(vocab)}")
    print(f"  Total Samples: {len(conversations)}")
    print(f"  Overall:      {'PASS' if passed else 'NEEDS IMPROVEMENT'}")

    # Save report
    report = {
        "timestamp": datetime.now().isoformat(),
        "samples": {
            "total": len(conversations),
            "train": len(X_train),
            "test": len(X_test),
            "signals": int(sum(labels)),
            "non_signals": int(len(labels) - sum(labels)),
        },
        "features": {
            "vocab_size": len(vocab),
            "conv_features": len(CONV_FEATURE_NAMES),
            "total": X.shape[1],
        },
        "binary": {
            "cv_f1_mean": round(float(cv_scores.mean()), 4),
            "cv_f1_std": round(float(cv_scores.std()), 4),
            "test_accuracy": round(binary_accuracy, 4),
            "test_precision": round(binary_precision, 4),
            "test_recall": round(binary_recall, 4),
            "test_f1": round(binary_f1, 4),
            "confusion_matrix": cm.tolist(),
        },
        "type": {
            "test_f1_weighted": round(type_f1, 4),
            "distribution": type_dist,
        },
        "latency": {
            "avg_ms": round(avg_latency, 2),
            "p50_ms": round(p50_latency, 2),
            "p95_ms": round(p95_latency, 2),
            "max_ms": round(max_latency, 2),
        },
        "passed": passed,
    }

    report_dir = Path(__file__).parent / "reports"
    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / "signal_classifier_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Report saved: {report_path}")

    return report


if __name__ == "__main__":
    report = run_simulation()
    sys.exit(0 if report["passed"] else 1)
