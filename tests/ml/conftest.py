"""Shared fixtures for ML eval tests."""

import json
from pathlib import Path

import pytest

DATASETS_DIR = Path(__file__).parent / "datasets"


@pytest.fixture
def signal_eval_data():
    """Load signal eval dataset."""
    with open(DATASETS_DIR / "signal_eval.json") as f:
        return json.load(f)


@pytest.fixture
def reranker_eval_data():
    """Load reranker eval dataset."""
    with open(DATASETS_DIR / "reranker_eval.json") as f:
        return json.load(f)


@pytest.fixture
def classifier_eval_data():
    """Load classifier eval dataset."""
    with open(DATASETS_DIR / "classifier_eval.json") as f:
        return json.load(f)
