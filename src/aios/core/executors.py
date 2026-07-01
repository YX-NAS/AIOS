from __future__ import annotations

import shlex
from pathlib import Path

from aios.core.instance_manager import ensure_state_dir
from aios.utils.json_utils import read_json, write_json


EXECUTOR_KINDS = ["manual", "command"]


def default_executor_library() -> list[dict]:
    return normalize_executors(
        [
            {
                "id": "manual",
                "label": "Manual",
                "kind": "manual",
                "enabled": True,
                "rank": 1,
                "binary": None,
                "args": [],
                "timeout_seconds": None,
                "pass_model_as_flag": False,
                "env": {},
            },
            {
                "id": "codex-cli",
                "label": "Codex CLI",
                "kind": "command",
                "enabled": True,
                "rank": 2,
                "binary": "codex",
                "args": ["exec", "--sandbox", "workspace-write", "--model", "{model}", "{prompt}"],
                "timeout_seconds": 1800,
                "pass_model_as_flag": True,
                "env": {},
            },
            {
                "id": "claude-code-cli",
                "label": "Claude Code CLI",
                "kind": "command",
                "enabled": True,
                "rank": 3,
                "binary": "claude",
                "args": ["-p", "--permission-mode", "bypassPermissions", "{prompt}"],
                "timeout_seconds": 1800,
                "pass_model_as_flag": False,
                "env": {},
            },
        ]
    )


def executor_library_path(root: Path | None = None) -> Path:
    return ensure_state_dir() / "executors.json"


def load_executor_library(root: Path | None = None) -> list[dict]:
    path = executor_library_path(root)
    payload = read_json(path, {"executors": default_executor_library()})
    executors = payload.get("executors")
    if isinstance(executors, list):
        return normalize_executors(executors)
    return default_executor_library()


def save_executor_library(root: Path | None, executors: list[dict]) -> None:
    path = executor_library_path(root)
    write_json(path, {"executors": normalize_executors(executors)})


def reset_executor_library(root: Path | None = None) -> list[dict]:
    executors = default_executor_library()
    save_executor_library(root, executors)
    return executors


def executor_summary(root: Path | None = None) -> dict:
    executors = load_executor_library(root)
    return {
        "executors": executors,
        "enabled_executor_count": len([item for item in executors if item["enabled"]]),
        "kinds": EXECUTOR_KINDS,
    }


def get_executor(root: Path | None, executor_id: str) -> dict:
    for executor in load_executor_library(root):
        if executor["id"] == executor_id:
            return executor
    raise ValueError(f"Executor not found: {executor_id}")


def create_executor(
    root: Path | None,
    executor_id: str,
    label: str | None = None,
    kind: str = "command",
    enabled: bool = True,
    rank: int = 1,
    binary: str | None = None,
    args: list[str] | None = None,
    timeout_seconds: int | None = None,
    pass_model_as_flag: bool = False,
    env: dict[str, str] | None = None,
) -> dict:
    executors = load_executor_library(root)
    cleaned_id = _clean_executor_id(executor_id)
    if any(item["id"] == cleaned_id for item in executors):
        raise ValueError(f"Executor already exists: {cleaned_id}")
    executor = {
        "id": cleaned_id,
        "label": (label or cleaned_id).strip(),
        "kind": _clean_kind(kind),
        "enabled": enabled,
        "rank": max(1, rank),
        "binary": (binary or "").strip() or None,
        "args": list(args or []),
        "timeout_seconds": timeout_seconds if timeout_seconds and timeout_seconds > 0 else None,
        "pass_model_as_flag": bool(pass_model_as_flag),
        "env": _clean_env(env or {}),
    }
    executors.append(executor)
    save_executor_library(root, executors)
    return get_executor(root, cleaned_id)


def update_executor(
    root: Path | None,
    current_executor_id: str,
    executor_id: str,
    label: str | None,
    kind: str,
    enabled: bool,
    rank: int,
    binary: str | None,
    args: list[str],
    timeout_seconds: int | None,
    pass_model_as_flag: bool,
    env: dict[str, str],
) -> dict:
    executors = load_executor_library(root)
    cleaned_id = _clean_executor_id(executor_id)
    for executor in executors:
        if executor["id"] != current_executor_id:
            continue
        if cleaned_id != current_executor_id and any(item["id"] == cleaned_id for item in executors):
            raise ValueError(f"Executor already exists: {cleaned_id}")
        executor["id"] = cleaned_id
        executor["label"] = (label or cleaned_id).strip()
        executor["kind"] = _clean_kind(kind)
        executor["enabled"] = bool(enabled)
        executor["rank"] = max(1, rank)
        executor["binary"] = (binary or "").strip() or None
        executor["args"] = list(args)
        executor["timeout_seconds"] = timeout_seconds if timeout_seconds and timeout_seconds > 0 else None
        executor["pass_model_as_flag"] = bool(pass_model_as_flag)
        executor["env"] = _clean_env(env)
        save_executor_library(root, executors)
        return get_executor(root, cleaned_id)
    raise ValueError(f"Executor not found: {current_executor_id}")


def delete_executor(root: Path | None, executor_id: str) -> list[dict]:
    if executor_id == "manual":
        raise ValueError("The built-in manual executor cannot be deleted.")
    executors = load_executor_library(root)
    remaining = [item for item in executors if item["id"] != executor_id]
    if len(remaining) == len(executors):
        raise ValueError(f"Executor not found: {executor_id}")
    save_executor_library(root, remaining)
    return remaining


def shell_preview(executor: dict, prompt: str, model: str | None) -> str:
    command = build_executor_command(executor, prompt, model)
    return shlex.join(command)


def build_executor_command(executor: dict, prompt: str, model: str | None) -> list[str]:
    kind = executor.get("kind")
    if kind != "command":
        raise ValueError(f"Executor does not support automated command execution: {executor.get('id')}")
    binary = str(executor.get("binary") or "").strip()
    if not binary:
        raise ValueError(f"Executor binary is not configured: {executor.get('id')}")
    substitutions = {
        "prompt": prompt,
        "model": model or "",
    }
    args = [str(arg).format(**substitutions) for arg in executor.get("args", [])]
    return [binary, *args]


def _clean_executor_id(executor_id: str) -> str:
    cleaned = str(executor_id).strip()
    if not cleaned:
        raise ValueError("Executor ID is required.")
    return cleaned


def _clean_kind(kind: str) -> str:
    cleaned = str(kind or "").strip().lower()
    if cleaned not in EXECUTOR_KINDS:
        raise ValueError(f"Unsupported executor kind: {kind}")
    return cleaned


def _clean_env(env: dict[str, str]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, value in env.items():
        env_key = str(key).strip()
        if not env_key:
            continue
        cleaned[env_key] = str(value)
    return cleaned


def normalize_executors(executors: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for index, executor in enumerate(executors):
        executor_id = str(executor.get("id") or "").strip()
        if not executor_id:
            continue
        kind = str(executor.get("kind") or "command").strip().lower()
        if kind not in EXECUTOR_KINDS:
            continue
        normalized.append(
            {
                "id": executor_id,
                "label": str(executor.get("label") or executor_id).strip(),
                "kind": kind,
                "enabled": bool(executor.get("enabled", True)),
                "rank": max(1, int(executor.get("rank", index + 1))),
                "binary": (str(executor.get("binary") or "").strip() or None),
                "args": [str(arg) for arg in executor.get("args", [])],
                "timeout_seconds": executor.get("timeout_seconds") or None,
                "pass_model_as_flag": bool(executor.get("pass_model_as_flag", False)),
                "env": _clean_env(executor.get("env") or {}),
            }
        )
    _ensure_unique_ids(normalized)
    normalized.sort(key=lambda item: (item["rank"], item["label"]))
    return normalized


def _ensure_unique_ids(executors: list[dict]) -> None:
    seen: set[str] = set()
    for executor in executors:
        if executor["id"] in seen:
            raise ValueError(f"Duplicate executor ID: {executor['id']}")
        seen.add(executor["id"])
