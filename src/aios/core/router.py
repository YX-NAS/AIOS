from __future__ import annotations

from pathlib import Path

from aios.core.models import get_model, load_model_library, model_runtime_status
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
    elif root is not None and preferred_models and recommended_model != preferred_models[0]:
        current_model = get_model(root, recommended_model)
        top_model = get_model(root, preferred_models[0])
        current_ready = model_runtime_status(current_model).get("ready") if current_model else False
        top_ready = model_runtime_status(top_model).get("ready") if top_model else False
        if top_ready and not current_ready:
            recommended_model = preferred_models[0]
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
    runtime_by_id = {model["id"]: model_runtime_status(model) for model in enabled}
    matching = [model["id"] for model in enabled if task_type in model["task_types"]]
    if matching:
        fallback = [model["id"] for model in enabled if model["id"] not in matching]
        weights = compute_model_weights(root)
        matching = apply_learned_order(matching, task_type, weights)
        return _prioritize_ready_models(matching, fallback, runtime_by_id)
    enabled_ids = {model["id"] for model in enabled}
    preferred = [model for model in default_preferred if model in enabled_ids]
    fallback = [model for model in default_fallback if model in enabled_ids and model not in preferred]
    if preferred:
        weights = compute_model_weights(root)
        preferred = apply_learned_order(preferred, task_type, weights)
        return _prioritize_ready_models(preferred, fallback, runtime_by_id)
    remaining = [model["id"] for model in enabled]
    if remaining:
        ready_remaining = [model_id for model_id in remaining if runtime_by_id.get(model_id, {}).get("ready")]
        if ready_remaining:
            first = ready_remaining[0]
            tail = [model_id for model_id in remaining if model_id != first]
            return [first], tail
        return [remaining[0]], remaining[1:]
    return default_preferred, default_fallback


def _prioritize_ready_models(
    preferred: list[str],
    fallback: list[str],
    runtime_by_id: dict[str, dict],
) -> tuple[list[str], list[str]]:
    ready_preferred = [model_id for model_id in preferred if runtime_by_id.get(model_id, {}).get("ready")]
    nonready_preferred = [model_id for model_id in preferred if model_id not in ready_preferred]
    ready_fallback = [model_id for model_id in fallback if runtime_by_id.get(model_id, {}).get("ready")]
    nonready_fallback = [model_id for model_id in fallback if model_id not in ready_fallback]
    if ready_preferred:
        return ready_preferred + nonready_preferred, ready_fallback + nonready_fallback
    if ready_fallback:
        return ready_fallback, nonready_preferred + nonready_fallback
    return preferred, fallback


def log_routing(root: Path, route_result: dict) -> None:
    log_path = aios_path(root) / "routing-log.json"
    entries = read_json(log_path, [])
    entry = {**route_result, "routed_at": now_iso()}
    entries.append(entry)
    write_json(log_path, entries)
