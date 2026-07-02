from __future__ import annotations

import os
from pathlib import Path

from aios.core.instance_manager import ensure_state_dir
from aios.core.templates import DEFAULT_ROUTING
from aios.utils.json_utils import read_json, write_json


TASK_TYPES = list(DEFAULT_ROUTING.keys())

DEFAULT_CONTEXT_WINDOWS = {
    "gpt-5.5": 200000,
    "claude": 200000,
    "deepseek-v4-pro": 128000,
    "deepseek-v4-flash": 128000,
    "gpt-5.4-mini": 128000,
    "minimax-m2.7-highspeed": 32000,
}

DEFAULT_PROVIDER_ENDPOINTS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "deepseek": "https://api.deepseek.com/v1",
    "minimax": "https://api.minimax.chat/v1",
}

DEFAULT_PROVIDER_AUTH_ENV_VARS = {
    "openai": ["OPENAI_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "minimax": ["MINIMAX_API_KEY"],
}


def default_model_library() -> list[dict]:
    model_tasks: dict[str, set[str]] = {}
    order: list[str] = []
    for task_type, rule in DEFAULT_ROUTING.items():
        for model in rule["preferred_models"] + rule["fallback_models"]:
            if model not in model_tasks:
                model_tasks[model] = set()
                order.append(model)
            model_tasks[model].add(task_type)
    models: list[dict] = []
    for index, model in enumerate(order):
        models.append(
            {
                "id": model,
                "label": model,
                "provider": infer_provider(model),
                "enabled": True,
                "rank": index + 1,
                "task_types": sorted(model_tasks[model]),
                "context_window": DEFAULT_CONTEXT_WINDOWS.get(model),
                "endpoint": DEFAULT_PROVIDER_ENDPOINTS.get(infer_provider(model)),
                "homepage": None,
                "notes": None,
                "config_url": None,
                "auth_env_vars": default_auth_env_vars(infer_provider(model)),
            }
        )
    return models


def infer_provider(model_id: str) -> str:
    lowered = model_id.lower()
    if "gpt" in lowered:
        return "openai"
    if "claude" in lowered:
        return "anthropic"
    if "deepseek" in lowered:
        return "deepseek"
    if "minimax" in lowered:
        return "minimax"
    return "custom"


def model_library_path(root: Path | None = None) -> Path:
    return ensure_state_dir() / "models.json"


def load_model_library(root: Path | None = None) -> list[dict]:
    path = model_library_path(root)
    payload = read_json(path, {"models": default_model_library()})
    models = payload.get("models")
    if isinstance(models, list):
        return normalize_models(models)
    return default_model_library()


def save_model_library(root: Path | None, models: list[dict]) -> None:
    path = model_library_path(root)
    write_json(path, {"models": normalize_models(models)})


def reset_model_library(root: Path | None = None) -> list[dict]:
    models = default_model_library()
    save_model_library(root, models)
    return models


def normalize_models(models: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for index, model in enumerate(models):
        task_types = model.get("task_types") or []
        cleaned_task_types = [task_type for task_type in task_types if task_type in TASK_TYPES]
        model_id = str(model.get("id") or "").strip()
        if not model_id:
            continue
        normalized.append(
            {
                "id": model_id,
                "label": str(model.get("label") or model_id).strip(),
                "provider": str(model.get("provider") or infer_provider(model_id)).strip().lower(),
                "enabled": bool(model.get("enabled", True)),
                "rank": max(1, int(model.get("rank", index + 1))),
                "task_types": sorted(dict.fromkeys(cleaned_task_types)),
                "context_window": model.get("context_window") or DEFAULT_CONTEXT_WINDOWS.get(model_id),
                "endpoint": _clean_optional_text(model.get("endpoint")) or DEFAULT_PROVIDER_ENDPOINTS.get(str(model.get("provider") or infer_provider(model_id)).strip().lower()),
                "homepage": _clean_optional_text(model.get("homepage")),
                "notes": _clean_optional_text(model.get("notes")),
                "config_url": _clean_optional_text(model.get("config_url")),
                "auth_env_vars": _clean_auth_env_vars(model.get("auth_env_vars"), str(model.get("provider") or infer_provider(model_id)).strip().lower()),
            }
        )
    _ensure_unique_ids(normalized)
    normalized.sort(key=lambda item: (item["rank"], item["label"]))
    return normalized


def create_model(
    root: Path | None,
    model_id: str,
    label: str | None = None,
    provider: str | None = None,
    enabled: bool = True,
    rank: int = 1,
    task_types: list[str] | None = None,
    endpoint: str | None = None,
    homepage: str | None = None,
    notes: str | None = None,
    config_url: str | None = None,
    auth_env_vars: list[str] | None = None,
) -> dict:
    models = load_model_library(root)
    model_id = _clean_model_id(model_id)
    if any(model["id"] == model_id for model in models):
        raise ValueError(f"Model already exists: {model_id}")
    model = {
        "id": model_id,
        "label": (label or model_id).strip(),
        "provider": (provider or infer_provider(model_id)).strip().lower(),
        "enabled": enabled,
        "rank": max(1, rank),
        "task_types": _clean_task_types(task_types or []),
        "context_window": DEFAULT_CONTEXT_WINDOWS.get(model_id),
        "endpoint": _clean_optional_text(endpoint) or DEFAULT_PROVIDER_ENDPOINTS.get((provider or infer_provider(model_id)).strip().lower()),
        "homepage": _clean_optional_text(homepage),
        "notes": _clean_optional_text(notes),
        "config_url": _clean_optional_text(config_url),
        "auth_env_vars": _clean_auth_env_vars(auth_env_vars, (provider or infer_provider(model_id)).strip().lower()),
    }
    models.append(model)
    save_model_library(root, models)
    return next(item for item in load_model_library(root) if item["id"] == model_id)


def update_model(
    root: Path | None,
    current_model_id: str,
    model_id: str,
    label: str | None,
    provider: str | None,
    enabled: bool,
    rank: int,
    task_types: list[str],
    endpoint: str | None = None,
    homepage: str | None = None,
    notes: str | None = None,
    config_url: str | None = None,
    auth_env_vars: list[str] | None = None,
) -> dict:
    models = load_model_library(root)
    target_id = _clean_model_id(model_id)
    for model in models:
        if model["id"] == current_model_id:
            if target_id != current_model_id and any(item["id"] == target_id for item in models):
                raise ValueError(f"Model already exists: {target_id}")
            model["id"] = target_id
            model["label"] = (label or target_id).strip()
            model["provider"] = (provider or infer_provider(target_id)).strip().lower()
            model["enabled"] = enabled
            model["rank"] = max(1, rank)
            model["task_types"] = _clean_task_types(task_types)
            model["context_window"] = model.get("context_window") or DEFAULT_CONTEXT_WINDOWS.get(target_id)
            model["endpoint"] = _clean_optional_text(endpoint) or DEFAULT_PROVIDER_ENDPOINTS.get(model["provider"])
            model["homepage"] = _clean_optional_text(homepage)
            model["notes"] = _clean_optional_text(notes)
            model["config_url"] = _clean_optional_text(config_url)
            model["auth_env_vars"] = _clean_auth_env_vars(auth_env_vars, model["provider"])
            save_model_library(root, models)
            return next(item for item in load_model_library(root) if item["id"] == target_id)
    raise ValueError(f"Model not found: {current_model_id}")


def delete_model(root: Path | None, model_id: str) -> list[dict]:
    models = load_model_library(root)
    remaining = [model for model in models if model["id"] != model_id]
    if len(remaining) == len(models):
        raise ValueError(f"Model not found: {model_id}")
    save_model_library(root, remaining)
    return remaining


def model_summary(root: Path | None = None) -> dict:
    models = load_model_library(root)
    runtime = {model["id"]: model_runtime_status(model) for model in models}
    return {
        "models": [{**model, "runtime": runtime[model["id"]]} for model in models],
        "task_types": TASK_TYPES,
        "enabled_model_count": len([model for model in models if model["enabled"]]),
        "provider_ready_count": len([model for model in models if model["enabled"] and runtime[model["id"]]["ready"]]),
    }


def get_model(root: Path | None, model_id: str) -> dict | None:
    target = str(model_id or "").strip()
    if not target:
        return None
    for model in load_model_library(root):
        if model["id"] == target:
            return model
    return None


def default_auth_env_vars(provider: str) -> list[str]:
    return list(DEFAULT_PROVIDER_AUTH_ENV_VARS.get(str(provider or "").strip().lower(), []))


def model_runtime_status(model: dict) -> dict:
    provider = str(model.get("provider") or "").strip().lower()
    endpoint = str(model.get("endpoint") or "").strip()
    config_url = str(model.get("config_url") or "").strip()
    auth_env_vars = _clean_auth_env_vars(model.get("auth_env_vars"), provider)
    present_env_vars = [name for name in auth_env_vars if str(os.environ.get(name) or "").strip()]
    missing_env_vars = [name for name in auth_env_vars if name not in present_env_vars]
    auth_status = "ready" if auth_env_vars and not missing_env_vars else ("not_configured" if not auth_env_vars else "missing_env")
    provider_config_status = "ready" if endpoint or config_url else "missing_config"
    ready = bool(provider and provider_config_status == "ready" and auth_status == "ready")
    if not provider:
        reason = "Provider is not configured."
    elif provider_config_status != "ready":
        reason = "Provider endpoint or config URL is missing."
    elif auth_status == "missing_env":
        reason = f"Missing auth env vars: {', '.join(missing_env_vars)}"
    elif auth_status == "not_configured":
        reason = "No auth env vars configured for this provider."
    else:
        reason = None
    return {
        "ready": ready,
        "provider_config_status": provider_config_status,
        "auth_status": auth_status,
        "auth_env_vars": auth_env_vars,
        "present_auth_env_vars": present_env_vars,
        "missing_auth_env_vars": missing_env_vars,
        "endpoint": endpoint or None,
        "config_url": config_url or None,
        "reason": reason,
    }


def _clean_model_id(model_id: str) -> str:
    cleaned = str(model_id).strip()
    if not cleaned:
        raise ValueError("Model ID is required.")
    return cleaned


def _clean_task_types(task_types: list[str]) -> list[str]:
    return sorted(dict.fromkeys(task_type for task_type in task_types if task_type in TASK_TYPES))


def _clean_optional_text(value: object) -> str | None:
    cleaned = str(value or "").strip()
    return cleaned or None


def _clean_auth_env_vars(values: object, provider: str) -> list[str]:
    if values is None:
        return default_auth_env_vars(provider)
    if isinstance(values, str):
        raw_items = [item.strip() for item in values.split(",")]
    else:
        raw_items = [str(item).strip() for item in (values or [])]
    return [item for item in dict.fromkeys(raw_items) if item]


def _ensure_unique_ids(models: list[dict]) -> None:
    seen: set[str] = set()
    for model in models:
        if model["id"] in seen:
            raise ValueError(f"Duplicate model ID: {model['id']}")
        seen.add(model["id"])
