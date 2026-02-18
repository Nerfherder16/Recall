"""
Reranker training module.

Collects feedback data from Postgres audit_log, trains a LogisticRegression
model, bakes StandardScaler into weights, and stores to Redis.
"""

import json
import math
from datetime import datetime

import structlog

from .reranker import DURABILITY_SCORES, FEATURE_NAMES, REDIS_KEY

logger = structlog.get_logger()

MIN_SAMPLES = 30


async def collect_training_data(pg, qdrant) -> tuple[list[list[float]], list[int]]:
    """
    Build feature matrix X and label vector y from feedback audit entries.

    Each feedback entry has: useful (bool), similarity, memory features.
    Returns (X, y) where X is list of feature vectors and y is 0/1 labels.
    """
    rows = await pg.get_audit_log(action="feedback", limit=10000)

    X: list[list[float]] = []
    y: list[int] = []

    for row in rows:
        details = row.get("details")
        if not details:
            continue

        memory_id = row.get("memory_id")
        if not memory_id:
            continue

        is_useful = details.get("useful", False)
        similarity = details.get("similarity", 0.0)

        # Try enriched features first (from Task 5 enrichment)
        importance = details.get("importance")
        if importance is not None:
            # Enriched entry — use stored features
            features = [
                float(importance),
                float(details.get("stability", 0.5)),
                float(details.get("confidence", 0.5)),
                math.log1p(int(details.get("access_count", 0))),
                0.0,  # hours_since_last_access — not available in audit
                0.0,  # hours_since_creation — not available in audit
                1.0 if details.get("pinned", False) else 0.0,
                _durability_score(details.get("durability")),
                float(similarity),
                0.0,  # has_graph_path — not tracked in feedback
                0.0,  # retrieval_path_len — not tracked in feedback
            ]
        else:
            # Legacy entry — use old_importance/old_stability from audit
            # (avoids Qdrant lookups for deleted memories)
            if "old_importance" not in details:
                continue
            features = [
                float(details.get("old_importance", 0.5)),
                float(details.get("old_stability", 0.5)),
                0.5,  # confidence — not in legacy audit
                0.0,  # access_count — not in legacy audit
                0.0,  # hours_since_last_access
                0.0,  # hours_since_creation
                0.0,  # is_pinned — not in legacy audit
                0.5,  # durability — default durable
                float(similarity),
                0.0,  # has_graph_path
                0.0,  # retrieval_path_len
            ]

        X.append(features)
        y.append(1 if is_useful else 0)

    return X, y


def _durability_score(durability_str: str | None) -> float:
    """Map durability string to numeric score."""
    if not durability_str:
        return 0.5  # default = durable
    mapping = {"ephemeral": 0.0, "durable": 0.5, "permanent": 1.0}
    return mapping.get(durability_str, 0.5)


def _features_from_payload(payload: dict, similarity: float) -> list[float]:
    """Extract feature vector from Qdrant payload."""
    return [
        float(payload.get("importance", 0.5)),
        float(payload.get("stability", 0.5)),
        float(payload.get("confidence", 0.5)),
        math.log1p(int(payload.get("access_count", 0))),
        0.0,  # hours_since_last_access — snapshot not available
        0.0,  # hours_since_creation — snapshot not available
        1.0 if payload.get("pinned") == "true" else 0.0,
        _durability_score(payload.get("durability")),
        float(similarity),
        0.0,  # has_graph_path
        0.0,  # retrieval_path_len
    ]


async def train_reranker(pg, qdrant, redis_store) -> dict:
    """
    Train reranker from feedback data and store weights in Redis.

    Returns metadata dict with n_samples, cv_score, trained_at.
    Raises ValueError if insufficient training data.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score
    from sklearn.preprocessing import StandardScaler
    import numpy as np

    X_list, y_list = await collect_training_data(pg, qdrant)

    if len(X_list) < MIN_SAMPLES:
        raise ValueError(
            f"Insufficient training data: {len(X_list)} samples "
            f"(minimum {MIN_SAMPLES} required)"
        )

    X = np.array(X_list, dtype=np.float64)
    y = np.array(y_list, dtype=np.int32)

    # Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Train logistic regression
    model = LogisticRegression(
        class_weight="balanced",
        max_iter=1000,
        random_state=42,
    )
    model.fit(X_scaled, y)

    # Cross-validation
    n_folds = 5 if len(X_list) >= 50 else 3
    cv_scores = cross_val_score(model, X_scaled, y, cv=n_folds, scoring="accuracy")
    cv_score = float(cv_scores.mean())

    # Bake scaler into weights: w_eff[i] = coef[i] / scale[i]
    # b_eff = intercept - sum(coef * mean / scale)
    coef = model.coef_[0]
    intercept = model.intercept_[0]
    scale = scaler.scale_
    mean = scaler.mean_

    w_eff = (coef / scale).tolist()
    b_eff = float(intercept - np.sum(coef * mean / scale))

    trained_at = datetime.utcnow().isoformat()

    payload = {
        "features": FEATURE_NAMES,
        "weights": w_eff,
        "bias": b_eff,
        "trained_at": trained_at,
        "n_samples": len(X_list),
        "cv_score": round(cv_score, 4),
        "class_distribution": {
            "useful": int(np.sum(y == 1)),
            "not_useful": int(np.sum(y == 0)),
        },
    }

    await redis_store.client.set(REDIS_KEY, json.dumps(payload))

    logger.info(
        "reranker_trained",
        n_samples=len(X_list),
        cv_score=round(cv_score, 4),
        weights=w_eff,
    )

    return {
        "status": "ok",
        "n_samples": len(X_list),
        "cv_score": round(cv_score, 4),
        "trained_at": trained_at,
    }
