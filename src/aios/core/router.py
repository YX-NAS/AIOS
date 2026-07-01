from __future__ import annotations

from pathlib import Path

from aios.core.models import load_model_library
from aios.core.paths import aios_path
from aios.core.templates import DEFAULT_ROUTING
from aios.core.route_learning import apply_learned_order, compute_model_weights
from aios.utils.json_utils import read_json, write_json
from aios.utils.text import now_iso


def route_task(task: dict, root: Path | None = None) -> dict:
    rule = DEFAULT_ROUTING.get(task["type"], DEFAULT_ROUTING["simple_coding"])
    preferred_models = list(rule["preferred_models"])
    fallback_models = list(rule["fallback_models"])
    if root is not None:
        preferred_models, fallback_models = resolve_models_for_task(root, task["type"], preferred_models, fallback_models)
    recommended_model = task.get("recommended_model")
    if not recommended_model or (preferred_models and recommended_model not in preferred_models and recommended_model not in fallback_models):
        recommended_model = preferred_models[0] if preferred_models else fallback_models[0]
    return {
        "task_id": task["id"],
        "title": task["title"],
        "type": task["type"],
        "complexity": task["complexity"],
        "recommended_model": recommended_model,
        "fallback_models": fallback_models,
        "max_cost_level": rule["max_cost_level"],
        "reason": rule["reason"],
    }


def resolve_models_for_task(
    root: Path,
    task_type: str,
    default_preferred: list[str],
    default_fallback: list[str],
) -> tuple[list[str], list[str]]:
    models = load_model_library(root)
    enabled = [model for model in models if model["enabled"]]
    matching = [model["id"] for model in enabled if task_type in model["task_types"]]
    if matching:
        fallback = [model["id"] for model in enabled if model["id"] not in matching]
        weights = compute_model_weights(root)
        matching = apply_learned_order(matching, task_type, weights)
        return matching, fallback
    enabled_ids = {model["id"] for model in enabled}
    preferred = [model for model in default_preferred if model in enabled_ids]
    fallback = [model for model in default_fallback if model in enabled_ids and model not in preferred]
    if preferred:
        weights = compute_model_weights(root)
        preferred = apply_learned_order(preferred, task_type, weights)
        return preferred, fallback
    remaining = [model["id"] for model in enabled]
    if remaining:
        return [remaining[0]], remaining[1:]
    return default_preferred, default_fallback


def log_routing(root: Path, route_result: dict) -> None:
    log_path = aios_path(root) / "routing-log.json"
    entries = read_json(log_path, [])
    entry = {**route_result, "routed_at": now_iso()}
    entries.append(entry)
    write_json(log_path, entries)
