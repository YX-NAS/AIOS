from __future__ import annotations

import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from aios.core.instance_manager import ensure_state_dir
from aios.core.templates import DEFAULT_ROUTING
from aios.utils.json_utils import read_json, write_json
from aios.utils.text import now_iso


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

PROVIDER_AUTH_PROBE_PATHS = {
    "openai": "/models",
    "anthropic": "/v1/models",
    "deepseek": "/models",
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
                "input_cost_per_1m": None,
                "output_cost_per_1m": None,
                "cost_currency": "USD",
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


def model_handshake_cache_path(root: Path | None = None) -> Path:
    return ensure_state_dir() / "model-handshakes.json"


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
                "input_cost_per_1m": _clean_optional_number(model.get("input_cost_per_1m")),
                "output_cost_per_1m": _clean_optional_number(model.get("output_cost_per_1m")),
                "cost_currency": str(model.get("cost_currency") or "USD").strip().upper(),
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
    input_cost_per_1m: float | None = None,
    output_cost_per_1m: float | None = None,
    cost_currency: str | None = None,
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
        "input_cost_per_1m": _clean_optional_number(input_cost_per_1m),
        "output_cost_per_1m": _clean_optional_number(output_cost_per_1m),
        "cost_currency": str(cost_currency or "USD").strip().upper(),
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
    input_cost_per_1m: float | None = None,
    output_cost_per_1m: float | None = None,
    cost_currency: str | None = None,
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
            model["input_cost_per_1m"] = _clean_optional_number(input_cost_per_1m)
            model["output_cost_per_1m"] = _clean_optional_number(output_cost_per_1m)
            model["cost_currency"] = str(cost_currency or "USD").strip().upper()
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
        "provider_handshake_ready_count": len([model for model in models if model["enabled"] and runtime[model["id"]]["handshake_status"] == "ok"]),
        "provider_handshake_failed_count": len([model for model in models if model["enabled"] and runtime[model["id"]]["handshake_status"] == "failed"]),
        "provider_api_verified_count": len([model for model in models if model["enabled"] and runtime[model["id"]]["auth_probe_status"] == "ok"]),
        "provider_api_failed_count": len([model for model in models if model["enabled"] and runtime[model["id"]]["auth_probe_status"] == "failed"]),
        "priced_model_count": len([model for model in models if model.get("input_cost_per_1m") is not None or model.get("output_cost_per_1m") is not None]),
    }


def get_model(root: Path | None, model_id: str) -> dict | None:
    target = str(model_id or "").strip()
    if not target:
        return None
    for model in load_model_library(root):
        if model["id"] == target:
            return model
    return None


def estimate_model_cost(
    root: Path | None,
    model_id: str,
    prompt_tokens: int | None = None,
    output_tokens: int | None = None,
) -> dict:
    model = get_model(root, model_id)
    input_rate = _clean_optional_number((model or {}).get("input_cost_per_1m"))
    output_rate = _clean_optional_number((model or {}).get("output_cost_per_1m"))
    currency = str((model or {}).get("cost_currency") or "USD").strip().upper()
    prompt = max(0, int(prompt_tokens or 0))
    output = max(0, int(output_tokens or 0))
    input_cost = round(prompt / 1_000_000 * input_rate, 6) if input_rate is not None else None
    output_cost = round(output / 1_000_000 * output_rate, 6) if output_rate is not None else None
    total_cost = None
    if input_cost is not None or output_cost is not None:
        total_cost = round((input_cost or 0.0) + (output_cost or 0.0), 6)
    return {
        "model_id": model_id,
        "prompt_tokens": prompt,
        "output_tokens": output,
        "total_tokens": prompt + output,
        "input_cost_per_1m": input_rate,
        "output_cost_per_1m": output_rate,
        "estimated_input_cost": input_cost,
        "estimated_output_cost": output_cost,
        "estimated_total_cost": total_cost,
        "cost_currency": currency,
    }


def default_auth_env_vars(provider: str) -> list[str]:
    return list(DEFAULT_PROVIDER_AUTH_ENV_VARS.get(str(provider or "").strip().lower(), []))


def load_model_handshakes(root: Path | None = None) -> dict[str, dict]:
    payload = read_json(model_handshake_cache_path(root), {"models": {}})
    models = payload.get("models")
    if isinstance(models, dict):
        return models
    return {}


def save_model_handshakes(root: Path | None, items: dict[str, dict]) -> None:
    write_json(model_handshake_cache_path(root), {"models": items})


def latest_model_handshake(root: Path | None, model_id: str) -> dict | None:
    return load_model_handshakes(root).get(str(model_id or "").strip()) or None


def probe_model_provider(root: Path | None, model_id: str, timeout_seconds: float = 3.0) -> dict:
    model = get_model(root, model_id)
    if not model:
        raise ValueError(f"Model not found: {model_id}")
    runtime = model_runtime_status(model)
    target_url = runtime.get("endpoint") or runtime.get("config_url")
    if not target_url:
        result = {
            "model_id": model["id"],
            "status": "failed",
            "target_url": None,
            "checked_at": now_iso(),
            "http_status": None,
            "latency_ms": None,
            "reason": "Provider endpoint or config URL is missing.",
        }
        _save_model_handshake(root, model["id"], result)
        return result

    handshake = _run_probe_request(
        target_url,
        timeout_seconds=timeout_seconds,
        headers={
            "User-Agent": "AIOS/handshake",
            "Accept": "application/json, text/plain, */*",
        },
        ok_http_status=lambda code: 200 <= code < 500,
        failure_reason=lambda code: f"Provider returned HTTP {code}",
    )
    auth_probe = _run_auth_probe(model, runtime, timeout_seconds)
    status = "failed" if handshake["status"] == "failed" or auth_probe["status"] == "failed" else "ok"
    reason = auth_probe["reason"] if auth_probe["status"] == "failed" else handshake["reason"]

    result = {
        "model_id": model["id"],
        "status": status,
        "target_url": target_url,
        "checked_at": now_iso(),
        "http_status": handshake["http_status"],
        "latency_ms": handshake["latency_ms"],
        "reason": reason,
        "auth_probe_status": auth_probe["status"],
        "auth_probe_checked_at": auth_probe["checked_at"],
        "auth_probe_http_status": auth_probe["http_status"],
        "auth_probe_latency_ms": auth_probe["latency_ms"],
        "auth_probe_target_url": auth_probe["target_url"],
        "auth_probe_reason": auth_probe["reason"],
    }
    _save_model_handshake(root, model["id"], result)
    return result


def probe_models(root: Path | None, model_id: str | None = None, timeout_seconds: float = 3.0) -> list[dict]:
    if model_id:
        return [probe_model_provider(root, model_id, timeout_seconds=timeout_seconds)]
    return [probe_model_provider(root, model["id"], timeout_seconds=timeout_seconds) for model in load_model_library(root)]


def model_runtime_status(model: dict) -> dict:
    provider = str(model.get("provider") or "").strip().lower()
    endpoint = str(model.get("endpoint") or "").strip()
    config_url = str(model.get("config_url") or "").strip()
    auth_env_vars = _clean_auth_env_vars(model.get("auth_env_vars"), provider)
    present_env_vars = [name for name in auth_env_vars if str(os.environ.get(name) or "").strip()]
    missing_env_vars = [name for name in auth_env_vars if name not in present_env_vars]
    auth_status = "ready" if auth_env_vars and not missing_env_vars else ("not_configured" if not auth_env_vars else "missing_env")
    provider_config_status = "ready" if endpoint or config_url else "missing_config"
    handshake = latest_model_handshake(None, model.get("id") or "")
    handshake_status = str((handshake or {}).get("status") or "unknown").strip().lower()
    auth_probe_status = str((handshake or {}).get("auth_probe_status") or "unknown").strip().lower()
    ready = bool(
        provider
        and provider_config_status == "ready"
        and auth_status == "ready"
        and handshake_status != "failed"
        and auth_probe_status != "failed"
    )
    if not provider:
        reason = "Provider is not configured."
    elif provider_config_status != "ready":
        reason = "Provider endpoint or config URL is missing."
    elif auth_status == "missing_env":
        reason = f"Missing auth env vars: {', '.join(missing_env_vars)}"
    elif auth_status == "not_configured":
        reason = "No auth env vars configured for this provider."
    elif handshake_status == "failed":
        reason = (handshake or {}).get("reason") or "Provider handshake failed."
    elif auth_probe_status == "failed":
        reason = (handshake or {}).get("auth_probe_reason") or "Provider API auth probe failed."
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
        "handshake_status": handshake_status,
        "handshake_checked_at": (handshake or {}).get("checked_at"),
        "handshake_http_status": (handshake or {}).get("http_status"),
        "handshake_latency_ms": (handshake or {}).get("latency_ms"),
        "handshake_target_url": (handshake or {}).get("target_url"),
        "handshake_reason": (handshake or {}).get("reason"),
        "auth_probe_status": auth_probe_status,
        "auth_probe_checked_at": (handshake or {}).get("auth_probe_checked_at"),
        "auth_probe_http_status": (handshake or {}).get("auth_probe_http_status"),
        "auth_probe_latency_ms": (handshake or {}).get("auth_probe_latency_ms"),
        "auth_probe_target_url": (handshake or {}).get("auth_probe_target_url"),
        "auth_probe_reason": (handshake or {}).get("auth_probe_reason"),
        "reason": reason,
    }


def _save_model_handshake(root: Path | None, model_id: str, result: dict) -> None:
    items = load_model_handshakes(root)
    items[str(model_id).strip()] = result
    save_model_handshakes(root, items)


def _run_auth_probe(model: dict, runtime: dict, timeout_seconds: float) -> dict:
    provider = str(model.get("provider") or "").strip().lower()
    path = PROVIDER_AUTH_PROBE_PATHS.get(provider)
    if not path:
        return {
            "status": "skipped",
            "target_url": None,
            "checked_at": now_iso(),
            "http_status": None,
            "latency_ms": None,
            "reason": "Provider auth probe is not supported for this provider yet.",
        }
    if runtime.get("auth_status") != "ready":
        return {
            "status": "skipped",
            "target_url": None,
            "checked_at": now_iso(),
            "http_status": None,
            "latency_ms": None,
            "reason": "Auth env vars are not ready for provider auth probe.",
        }
    base_url = str(runtime.get("endpoint") or "").rstrip("/")
    target_url = f"{base_url}{path}"
    api_key = ""
    for name in runtime.get("present_auth_env_vars") or []:
        value = str(os.environ.get(name) or "").strip()
        if value:
            api_key = value
            break
    if not api_key:
        return {
            "status": "skipped",
            "target_url": target_url,
            "checked_at": now_iso(),
            "http_status": None,
            "latency_ms": None,
            "reason": "Provider auth env var is empty.",
        }
    headers = _auth_probe_headers(provider, api_key)
    return _run_probe_request(
        target_url,
        timeout_seconds=timeout_seconds,
        headers=headers,
        ok_http_status=lambda code: 200 <= code < 300,
        failure_reason=lambda code: _auth_probe_failure_reason(provider, code),
    )


def _auth_probe_headers(provider: str, api_key: str) -> dict[str, str]:
    headers = {
        "User-Agent": "AIOS/auth-probe",
        "Accept": "application/json, text/plain, */*",
    }
    if provider == "anthropic":
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
        return headers
    headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _auth_probe_failure_reason(provider: str, status_code: int) -> str:
    if status_code in (401, 403):
        return f"Provider auth probe rejected credentials with HTTP {status_code}."
    return f"Provider auth probe returned HTTP {status_code}."


def _run_probe_request(
    target_url: str,
    *,
    timeout_seconds: float,
    headers: dict[str, str],
    ok_http_status,
    failure_reason,
) -> dict:
    started = time.perf_counter()
    request = Request(
        target_url,
        headers=headers,
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            http_status = response.status
            status = "ok" if ok_http_status(http_status) else "failed"
            reason = None if status == "ok" else failure_reason(http_status)
    except HTTPError as exc:
        http_status = exc.code
        status = "ok" if ok_http_status(exc.code) else "failed"
        reason = None if status == "ok" else failure_reason(exc.code)
    except URLError as exc:
        http_status = None
        status = "failed"
        reason = str(exc.reason or exc)
    return {
        "status": status,
        "target_url": target_url,
        "checked_at": now_iso(),
        "http_status": http_status,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
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


def _clean_optional_number(value: object) -> float | None:
    if value is None or value == "":
        return None
    cleaned = float(value)
    if cleaned < 0:
        raise ValueError("Numeric model fields cannot be negative.")
    return round(cleaned, 6)


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
