"""P2-2: Route learning tests."""

from __future__ import annotations

import json
from pathlib import Path

from aios.core.route_learning import apply_learned_order, compute_model_weights
from aios.core.scoring import save_score
from aios.main import main


def test_compute_model_weights_with_enough_samples(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    for i, score in enumerate([5, 4, 5]):
        save_score(tmp_path, f"TASK-{i}", "gpt-5.5", score, None, "complex_coding")
    save_score(tmp_path, "TASK-10", "deepseek-v4-pro", 3, None, "complex_coding")
    weights = compute_model_weights(tmp_path)
    assert weights[("gpt-5.5", "complex_coding")] > 0
    assert weights[("deepseek-v4-pro", "complex_coding")] == 0.0


def test_compute_model_weights_with_few_samples(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    save_score(tmp_path, "TASK-1", "gpt-5.5", 5, None, "simple_coding")
    save_score(tmp_path, "TASK-2", "gpt-5.5", 4, None, "simple_coding")
    weights = compute_model_weights(tmp_path)
    assert weights[("gpt-5.5", "simple_coding")] == 0.0


def test_resolve_models_uses_learned_weights(tmp_path: Path) -> None:
    from aios.core.router import resolve_models_for_task
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    for i, score in enumerate([5, 5, 5]):
        save_score(tmp_path, f"TASK-{i}", "deepseek-v4-pro", score, None, "simple_coding")
    for i, score in enumerate([1, 1, 2]):
        save_score(tmp_path, f"TASK-{i+10}", "gpt-5.4-mini", score, None, "simple_coding")
    preferred, fallback = resolve_models_for_task(
        tmp_path, "simple_coding",
        ["deepseek-v4-pro", "gpt-5.4-mini"],
        ["minimax-m2.7-highspeed"],
    )
    assert preferred[0] == "deepseek-v4-pro"


def test_resolve_models_preserves_rank_without_scores(tmp_path: Path) -> None:
    from aios.core.router import resolve_models_for_task
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    preferred, fallback = resolve_models_for_task(
        tmp_path, "simple_coding",
        ["deepseek-v4-pro", "gpt-5.4-mini"],
        ["minimax-m2.7-highspeed"],
    )
    # Global model library may contain extra models matching simple_coding;
    # key invariant: deepseek-v4-pro should appear before gpt-5.4-mini
    assert preferred.index("deepseek-v4-pro") < preferred.index("gpt-5.4-mini")


def test_apply_learned_order_mixed_weights() -> None:
    weights = {("A", "coding"): 3.5, ("B", "coding"): 1.2, ("C", "coding"): 0.0}
    result = apply_learned_order(["C", "A", "B"], "coding", weights)
    assert result == ["A", "B", "C"]


def test_apply_learned_order_all_zero_weights() -> None:
    weights = {("A", "coding"): 0.0, ("B", "coding"): 0.0}
    result = apply_learned_order(["B", "A"], "coding", weights)
    assert result == ["B", "A"]
