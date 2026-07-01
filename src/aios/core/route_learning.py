"""P2-2: Route learning — adjust model order based on historical scores."""

from __future__ import annotations

import math
from pathlib import Path

from aios.core.scoring import load_scores

# Minimum sample count before learned weights take effect.
MIN_SAMPLES = 3


def compute_model_weights(root: Path) -> dict[tuple[str, str], float]:
    """Compute learned weights keyed by (model_id, task_type).

    Weight formula: avg_score * ln(sample_count + 1)
    Returns 0 weight when sample count < MIN_SAMPLES.
    """
    scores = load_scores(root)
    buckets: dict[tuple[str, str], list[int]] = {}
    for entry in scores:
        key = (entry["model"], entry.get("task_type", "unknown"))
        buckets.setdefault(key, []).append(entry["score"])

    weights: dict[tuple[str, str], float] = {}
    for key, score_list in buckets.items():
        if len(score_list) < MIN_SAMPLES:
            weights[key] = 0.0
        else:
            avg = sum(score_list) / len(score_list)
            weights[key] = avg * math.log(len(score_list) + 1)
    return weights


def apply_learned_order(
    candidates: list[str],
    task_type: str,
    weights: dict[tuple[str, str], float],
) -> list[str]:
    """Re-order candidates by learned weight for a given task_type.

    Models with weight > 0 are sorted by weight descending first,
    then models with weight == 0 keep their original relative order
    after the weighted ones.
    """
    weighted: list[tuple[float, int, str]] = []
    unweighted: list[str] = []
    for idx, model in enumerate(candidates):
        w = weights.get((model, task_type), 0.0)
        if w > 0:
            weighted.append((w, idx, model))
        else:
            unweighted.append(model)
    weighted.sort(key=lambda t: (-t[0], t[1]))
    return [m for _, _, m in weighted] + unweighted
