"""Tests for the ML eval harness."""

import json
from pathlib import Path

from tests.ml.run_eval import (
    compute_metrics,
    eval_baseline,
    eval_reranker,
    sigmoid,
    stratified_split,
)

DATASETS_DIR = Path(__file__).parent / "datasets"


def test_sigmoid_bounds():
    """Sigmoid output is always between 0 and 1."""
    assert 0.0 < sigmoid(0.0) < 1.0
    assert sigmoid(0.0) == 0.5
    assert sigmoid(10.0) > 0.99
    assert sigmoid(-10.0) < 0.01


def test_compute_metrics_perfect():
    """Perfect predictions yield P=R=F1=Acc=1.0."""
    y_true = [True, True, False, False]
    y_pred = [True, True, False, False]
    m = compute_metrics(y_true, y_pred)
    assert m["precision"] == 1.0
    assert m["recall"] == 1.0
    assert m["f1"] == 1.0
    assert m["accuracy"] == 1.0


def test_compute_metrics_all_wrong():
    """All wrong predictions yield F1=0."""
    y_true = [True, True, False, False]
    y_pred = [False, False, True, True]
    m = compute_metrics(y_true, y_pred)
    assert m["precision"] == 0.0
    assert m["recall"] == 0.0
    assert m["f1"] == 0.0
    assert m["accuracy"] == 0.0


def test_compute_metrics_known_values():
    """Verify P/R/F1 math with known values."""
    # TP=2, FP=1, FN=1, TN=1
    y_true = [True, True, True, False, False]
    y_pred = [True, True, False, True, False]
    m = compute_metrics(y_true, y_pred)
    assert m["tp"] == 2
    assert m["fp"] == 1
    assert m["fn"] == 1
    assert m["tn"] == 1
    assert abs(m["precision"] - 0.6667) < 0.001
    assert abs(m["recall"] - 0.6667) < 0.001
    assert abs(m["f1"] - 0.6667) < 0.001


def test_signal_eval_dataset_valid():
    """signal_eval.json loads and has minimum 30 samples."""
    with open(DATASETS_DIR / "signal_eval.json") as f:
        data = json.load(f)
    assert len(data) >= 30
    for sample in data:
        assert "turns" in sample
        assert "expected_signal" in sample
        assert isinstance(sample["expected_signal"], bool)
        assert len(sample["turns"]) >= 1


def test_reranker_eval_dataset_valid():
    """reranker_eval.json loads and has minimum 30 samples."""
    with open(DATASETS_DIR / "reranker_eval.json") as f:
        data = json.load(f)
    assert len(data) >= 30
    for sample in data:
        assert "features" in sample
        assert len(sample["features"]) == 11
        assert "expected_useful" in sample
        assert isinstance(sample["expected_useful"], bool)


def test_classifier_eval_dataset_valid():
    """classifier_eval.json loads and has minimum 30 samples."""
    with open(DATASETS_DIR / "classifier_eval.json") as f:
        data = json.load(f)
    assert len(data) >= 30
    for sample in data:
        assert "turns" in sample
        assert "expected_signal" in sample


def test_eval_reranker_produces_metrics():
    """eval_reranker returns valid metrics dict."""
    with open(DATASETS_DIR / "reranker_eval.json") as f:
        data = json.load(f)
    metrics = eval_reranker(data)
    assert metrics["model"] == "reranker"
    assert 0.0 <= metrics["precision"] <= 1.0
    assert 0.0 <= metrics["recall"] <= 1.0
    assert 0.0 <= metrics["f1"] <= 1.0
    assert metrics["total"] == len(data)


def test_eval_reranker_f1_above_threshold():
    """Reranker with synthetic weights should achieve F1 > 0.7."""
    with open(DATASETS_DIR / "reranker_eval.json") as f:
        data = json.load(f)
    metrics = eval_reranker(data)
    assert metrics["f1"] > 0.7, f"F1={metrics['f1']} below 0.7 threshold"


def test_eval_baseline_produces_metrics():
    """eval_baseline returns valid binary + type metrics."""
    with open(DATASETS_DIR / "signal_eval.json") as f:
        data = json.load(f)
    binary, type_metrics = eval_baseline(data)
    assert 0.0 <= binary["precision"] <= 1.0
    assert 0.0 <= binary["recall"] <= 1.0
    assert 0.0 <= binary["f1"] <= 1.0
    assert isinstance(type_metrics, dict)


def test_eval_baseline_f1_above_threshold():
    """Baseline heuristic should achieve F1 > 0.5 on signal_eval."""
    with open(DATASETS_DIR / "signal_eval.json") as f:
        data = json.load(f)
    binary, _ = eval_baseline(data)
    assert binary["f1"] > 0.5, f"F1={binary['f1']} below 0.5 threshold"


def test_stratified_split_preserves_ratio():
    """Stratified split maintains approximate class balance."""
    samples = [
        {"turns": [{"role": "user", "content": "x"}] * 2, "is_signal": True} for _ in range(40)
    ] + [{"turns": [{"role": "user", "content": "y"}] * 2, "is_signal": False} for _ in range(60)]
    train, test = stratified_split(samples, test_ratio=0.2)
    assert len(train) + len(test) == 100
    test_pos = sum(1 for s in test if s["is_signal"])
    test_neg = len(test) - test_pos
    # Should have ~8 positives and ~12 negatives in test
    assert 4 <= test_pos <= 12
    assert 8 <= test_neg <= 16


def test_corpus_datasets_have_required_fields():
    """All *_corpus.json files have the required schema."""
    for path in DATASETS_DIR.glob("*_corpus.json"):
        with open(path) as f:
            data = json.load(f)
        assert len(data) > 0, f"{path.name} is empty"
        for sample in data[:5]:  # spot check first 5
            assert "turns" in sample, f"{path.name} missing turns"
            assert "is_signal" in sample, f"{path.name} missing is_signal"
            assert isinstance(sample["is_signal"], bool)
            if sample["is_signal"]:
                assert "signal_type" in sample
