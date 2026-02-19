"""
Signal classifier training module.

Collects labeled conversation data from corpus files and Postgres audit_log,
trains TF-IDF + logistic regression classifiers (binary + type), bakes
StandardScaler into weights, and stores to Redis.
"""

import json
import math
from datetime import datetime
from typing import Any

import structlog

from .signal_classifier import (
    CONV_FEATURE_NAMES,
    REDIS_KEY,
    _tokenize,
    extract_conversation_features,
)

logger = structlog.get_logger()

MIN_SAMPLES = 20

# Signal type mapping from conversation task names
_TASK_TO_SIGNAL_TYPE: dict[str, str] = {
    "debugging": "error_fix",
    "debug": "error_fix",
    "redis connection": "error_fix",
    "neo4j authentication": "error_fix",
    "qdrant indexes": "fact",
    "setting up": "workflow",
    "configuring": "workflow",
    "optimizing": "fact",
    "implementing": "workflow",
    "strategy": "decision",
    "tuning": "decision",
    "management": "workflow",
    "backup": "workflow",
    "isolation": "decision",
    "anti-pattern": "pattern",
    "profiling": "fact",
    "durability": "fact",
    "embedding": "fact",
    "rate limit": "fact",
    "testing": "workflow",
    "normalization": "workflow",
    "reranker": "fact",
    "feedback": "workflow",
    "decay": "workflow",
    "sse": "fact",
    "consolidation": "decision",
    "signal detection": "decision",
    "graph": "workflow",
}


def load_dataset_files() -> tuple[list[list[dict[str, str]]], list[int], list[str]]:
    """
    Load labeled conversations from JSON dataset files.

    Reads tests/ml/datasets/generated_corpus.json and any other
    *_corpus.json files. Each sample needs: turns, is_signal,
    signal_type.

    Returns (conversations, labels, signal_types).
    """
    from pathlib import Path

    conversations: list[list[dict[str, str]]] = []
    labels: list[int] = []
    signal_types: list[str] = []

    datasets_dir = Path(__file__).parent.parent.parent / "tests" / "ml" / "datasets"
    if not datasets_dir.exists():
        logger.info("dataset_dir_not_found", path=str(datasets_dir))
        return conversations, labels, signal_types

    for path in sorted(datasets_dir.glob("*_corpus.json")):
        try:
            with open(path) as f:
                data = json.load(f)
            count = 0
            for sample in data:
                turns = sample.get("turns", [])
                if len(turns) < 2:
                    continue
                is_signal = sample.get("is_signal", False)
                sig_type = sample.get("signal_type", "none")
                conversations.append(turns)
                labels.append(1 if is_signal else 0)
                signal_types.append(sig_type if is_signal else "none")
                count += 1
            logger.info(
                "dataset_loaded",
                path=path.name,
                samples=count,
            )
        except Exception as e:
            logger.warning("dataset_load_failed", path=str(path), error=str(e))

    return conversations, labels, signal_types


def _infer_signal_type(task_name: str) -> str:
    """Infer signal type from a conversation task name."""
    task_lower = task_name.lower()
    for keyword, signal_type in _TASK_TO_SIGNAL_TYPE.items():
        if keyword in task_lower:
            return signal_type
    return "fact"


def collect_training_data_from_corpus() -> tuple[list[list[dict[str, str]]], list[int], list[str]]:
    """
    Load labeled conversations from test corpus files.

    Returns (conversations, labels, signal_types) where:
    - conversations: list of turn-lists
    - labels: 1 for signal, 0 for no-signal
    - signal_types: type string for positives, "none" for negatives
    """
    conversations: list[list[dict[str, str]]] = []
    labels: list[int] = []
    signal_types: list[str] = []

    # Source 1: TEST_CONVERSATIONS (hand-labeled)
    try:
        from tests.simulation.data.conversation_turns import TEST_CONVERSATIONS

        for conv in TEST_CONVERSATIONS:
            turns = [{"role": role, "content": content} for role, content in conv["turns"]]
            expected = conv.get("expected_signals", [])
            is_signal = len(expected) > 0
            conversations.append(turns)
            labels.append(1 if is_signal else 0)
            signal_types.append(expected[0] if expected else "none")
    except ImportError:
        logger.warning("corpus_test_conversations_not_found")

    # Source 2: MARATHON CONVERSATIONS (task-name labeled)
    try:
        from tests.simulation.marathon.corpus import CONVERSATIONS

        for conv in CONVERSATIONS:
            turns = [{"role": role, "content": content} for role, content in conv["turns"]]
            signal_type = _infer_signal_type(conv.get("task", ""))
            conversations.append(turns)
            labels.append(1)
            signal_types.append(signal_type)
    except ImportError:
        logger.warning("corpus_marathon_not_found")

    return conversations, labels, signal_types


def generate_synthetic_negatives(
    n_samples: int = 40,
) -> list[list[dict[str, str]]]:
    """
    Generate synthetic negative examples (non-signal conversations).

    Creates short, greeting-like, or factual Q&A exchanges that shouldn't
    trigger signal detection.
    """
    negatives: list[list[dict[str, str]]] = []

    templates = [
        # Greetings
        [
            {"role": "user", "content": "Hey"},
            {"role": "assistant", "content": "Hi! How can I help?"},
        ],
        [
            {"role": "user", "content": "Good morning"},
            {"role": "assistant", "content": "Good morning! What are you working on today?"},
        ],
        [
            {"role": "user", "content": "Thanks for your help"},
            {
                "role": "assistant",
                "content": "You're welcome! Let me know if you need anything else.",
            },
        ],
        # Short status checks
        [
            {"role": "user", "content": "Is everything running?"},
            {"role": "assistant", "content": "All systems are operational."},
        ],
        [
            {"role": "user", "content": "What time is it?"},
            {"role": "assistant", "content": "I don't have access to the current time."},
        ],
        # Simple commands
        [
            {"role": "user", "content": "Show me the contents of main.py"},
            {"role": "assistant", "content": "Here's the file content..."},
        ],
        [
            {"role": "user", "content": "Run the tests"},
            {"role": "assistant", "content": "Running pytest... All tests pass."},
        ],
        [
            {"role": "user", "content": "List the files"},
            {"role": "assistant", "content": "Here are the files in the directory."},
        ],
        # Chitchat
        [
            {"role": "user", "content": "Just checking in"},
            {"role": "assistant", "content": "I'm here! Ready to help when you need me."},
        ],
        [
            {"role": "user", "content": "Never mind, I figured it out"},
            {"role": "assistant", "content": "No problem! Glad you got it sorted."},
        ],
    ]

    # Also generate negatives from MEMORIES corpus (non-conversational)
    try:
        from tests.simulation.marathon.corpus import MEMORIES

        memory_texts = []
        for domain_mems in MEMORIES.values():
            for mem in domain_mems:
                memory_texts.append(mem["content"])

        # Create fake "conversations" from individual memory texts
        for i in range(min(n_samples - len(templates), len(memory_texts))):
            text = memory_texts[i % len(memory_texts)]
            negatives.append(
                [
                    {"role": "user", "content": text},
                    {"role": "assistant", "content": "Noted."},
                ]
            )
    except ImportError:
        pass

    # Add templates
    negatives.extend(templates)

    return negatives[:n_samples]


def _build_vocabulary(texts: list[str], max_vocab: int = 500) -> tuple[dict[str, int], list[float]]:
    """
    Build TF-IDF vocabulary and IDF weights from a corpus of texts.

    Returns (vocab_map, idf_weights) where:
    - vocab_map: {token: index} for top-N terms by document frequency
    - idf_weights: IDF value per vocabulary term
    """
    # Document frequency
    doc_freq: dict[str, int] = {}
    total_docs = len(texts)

    for text in texts:
        unique_tokens = set(_tokenize(text))
        for token in unique_tokens:
            doc_freq[token] = doc_freq.get(token, 0) + 1

    # Keep top N by document frequency (appears in most docs)
    sorted_terms = sorted(doc_freq.items(), key=lambda x: -x[1])
    top_terms = sorted_terms[:max_vocab]

    vocab_map = {term: i for i, (term, _) in enumerate(top_terms)}
    idf_weights = [math.log(total_docs / (1 + df)) for _, df in top_terms]

    return vocab_map, idf_weights


async def _collect_from_audit_log(
    pg,
) -> tuple[list[list[dict[str, str]]], list[int], list[str]]:
    """
    Build training samples from production signal data in Postgres.

    Queries audit_log for signal-created memories and their feedback.
    Builds pseudo-conversations from memory content for the classifier.

    Returns (conversations, labels, signal_types).
    """
    conversations: list[list[dict[str, str]]] = []
    labels: list[int] = []
    signal_types: list[str] = []

    try:
        # Get signal-created memories with their details
        rows = await pg.pool.fetch("""
            SELECT a.memory_id, a.details, a.session_id,
                   COALESCE(
                       (SELECT details->>'useful' FROM audit_log f
                        WHERE f.memory_id = a.memory_id
                        AND f.action = 'feedback'
                        ORDER BY f.timestamp DESC LIMIT 1),
                       'unknown'
                   ) AS feedback
            FROM audit_log a
            WHERE a.action = 'create' AND a.actor = 'signal'
            AND a.details IS NOT NULL
            ORDER BY a.timestamp DESC
            LIMIT 500
        """)

        for row in rows:
            details = row["details"] if isinstance(row["details"], dict) else {}
            signal_type = details.get("signal_type", "fact")
            feedback = row["feedback"]

            # Signal-created memory with positive or no feedback = positive sample
            # Signal-created memory with negative feedback = false positive (negative)
            is_signal = feedback != "false"

            # Build pseudo-conversation from the signal content
            # The memory content is stored in Qdrant, but we can use
            # signal_type + session context as a proxy
            content = details.get("content", "")
            if not content:
                continue

            turns = [
                {"role": "user", "content": content},
                {"role": "assistant", "content": "Noted, I'll remember that."},
            ]

            conversations.append(turns)
            labels.append(1 if is_signal else 0)
            signal_types.append(signal_type if is_signal else "none")

        logger.info(
            "audit_log_training_data",
            total=len(rows),
            positives=sum(labels),
            negatives=len(labels) - sum(labels),
        )
    except Exception as e:
        logger.warning("audit_log_training_data_failed", error=str(e))

    return conversations, labels, signal_types


async def train_signal_classifier(redis_store, pg=None) -> dict[str, Any]:
    """
    Train signal classifier from corpus data and store weights in Redis.

    Args:
        redis_store: Redis store for saving weights
        pg: Optional Postgres store for additional audit_log data

    Returns metadata dict with training metrics.
    Raises ValueError if insufficient training data.
    """
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score
    from sklearn.preprocessing import StandardScaler

    # Collect labeled data from all sources
    conversations, labels, signal_types = collect_training_data_from_corpus()

    # Source 3: JSON dataset files (generated_corpus.json, etc.)
    ds_convs, ds_labels, ds_types = load_dataset_files()
    conversations.extend(ds_convs)
    labels.extend(ds_labels)
    signal_types.extend(ds_types)

    # Source 4: Production data from Postgres audit_log
    if pg is not None:
        pg_convs, pg_labels, pg_types = await _collect_from_audit_log(pg)
        conversations.extend(pg_convs)
        labels.extend(pg_labels)
        signal_types.extend(pg_types)

    # Generate synthetic negatives
    negatives = generate_synthetic_negatives(40)
    for neg in negatives:
        conversations.append(neg)
        labels.append(0)
        signal_types.append("none")

    if len(conversations) < MIN_SAMPLES:
        raise ValueError(
            f"Insufficient training data: {len(conversations)} samples "
            f"(minimum {MIN_SAMPLES} required)"
        )

    # Build TF-IDF vocabulary from all conversation text
    max_vocab = 1000 if len(conversations) > 200 else 500
    all_texts = [" ".join(t.get("content", "") for t in conv) for conv in conversations]
    vocab, idf_weights = _build_vocabulary(all_texts, max_vocab=max_vocab)

    # Build feature matrix
    from .signal_classifier import tfidf_transform

    feat_rows: list[list[float]] = []
    for i, conv in enumerate(conversations):
        text = all_texts[i]
        tfidf_vec = tfidf_transform(text, vocab, idf_weights)
        conv_features = extract_conversation_features(conv)
        feat_rows.append(tfidf_vec + conv_features)

    features = np.array(feat_rows, dtype=np.float64)
    y_binary = np.array(labels, dtype=np.int32)

    # Scale features
    scaler = StandardScaler()
    feat_scaled = scaler.fit_transform(features)

    # Train binary classifier
    binary_model = LogisticRegression(
        class_weight="balanced",
        max_iter=1000,
        random_state=42,
    )
    binary_model.fit(feat_scaled, y_binary)

    # Cross-validation for binary
    n_folds = 5 if len(feat_rows) >= 50 else 3
    binary_cv = cross_val_score(
        binary_model,
        feat_scaled,
        y_binary,
        cv=n_folds,
        scoring="f1",
    )
    binary_cv_score = float(binary_cv.mean())

    # Bake scaler into binary weights
    coef_b = binary_model.coef_[0]
    intercept_b = binary_model.intercept_[0]
    scale = scaler.scale_
    mean = scaler.mean_

    binary_w_eff = (coef_b / scale).tolist()
    binary_b_eff = float(intercept_b - np.sum(coef_b * mean / scale))

    # Train type classifier (one-vs-rest) on positives only
    positive_mask = y_binary == 1
    feat_pos = feat_scaled[positive_mask]
    types_pos = [signal_types[i] for i in range(len(signal_types)) if labels[i] == 1]

    type_cv_score = 0.0
    type_classes: list[str] = []
    type_weights_eff: list[list[float]] = []
    type_biases_eff: list[float] = []

    if len(set(types_pos)) >= 2 and len(types_pos) >= 10:
        # Encode types as integers
        unique_types = sorted(set(types_pos))
        type_to_idx = {t: i for i, t in enumerate(unique_types)}
        y_type = np.array([type_to_idx[t] for t in types_pos], dtype=np.int32)

        type_model = LogisticRegression(
            class_weight="balanced",
            max_iter=1000,
            random_state=42,
        )
        type_model.fit(feat_pos, y_type)

        # Cross-validate type classifier
        type_n_folds = min(n_folds, len(set(y_type)))
        if type_n_folds >= 2:
            type_cv = cross_val_score(
                type_model, feat_pos, y_type, cv=type_n_folds, scoring="accuracy"
            )
            type_cv_score = float(type_cv.mean())

        # Bake scaler into type weights
        type_classes = unique_types
        for i in range(len(unique_types)):
            coef_t = type_model.coef_[i]
            intercept_t = type_model.intercept_[i]
            w_eff = (coef_t / scale).tolist()
            b_eff = float(intercept_t - np.sum(coef_t * mean / scale))
            type_weights_eff.append(w_eff)
            type_biases_eff.append(b_eff)

    trained_at = datetime.utcnow().isoformat()

    payload = {
        "version": 1,
        "vocab": vocab,
        "idf_weights": idf_weights,
        "binary": {
            "weights": binary_w_eff,
            "bias": binary_b_eff,
        },
        "type_classifier": {
            "classes": type_classes,
            "weights": type_weights_eff,
            "biases": type_biases_eff,
        },
        "conv_feature_names": CONV_FEATURE_NAMES,
        "trained_at": trained_at,
        "n_samples": len(conversations),
        "binary_cv_score": round(binary_cv_score, 4),
        "type_cv_score": round(type_cv_score, 4),
        "class_distribution": {
            "signal": int(np.sum(y_binary == 1)),
            "no_signal": int(np.sum(y_binary == 0)),
        },
        "type_distribution": {t: types_pos.count(t) for t in set(types_pos)} if types_pos else {},
    }

    await redis_store.client.set(REDIS_KEY, json.dumps(payload))

    logger.info(
        "signal_classifier_trained",
        n_samples=len(conversations),
        vocab_size=len(vocab),
        binary_cv_score=round(binary_cv_score, 4),
        type_cv_score=round(type_cv_score, 4),
    )

    return {
        "status": "ok",
        "n_samples": len(conversations),
        "vocab_size": len(vocab),
        "binary_cv_score": round(binary_cv_score, 4),
        "type_cv_score": round(type_cv_score, 4),
        "type_classes": type_classes,
        "trained_at": trained_at,
    }
