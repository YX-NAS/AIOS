from __future__ import annotations

import re
import shlex
import shutil
import subprocess
from pathlib import Path

from aios.core.instance_manager import ensure_state_dir
from aios.utils.json_utils import read_json, write_json


EXECUTOR_KINDS = ["manual", "command"]


def _raw_default_executor_library() -> list[dict]:
    return [
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
            "resume_args": [],
            "continue_args": [],
            "resume_in_project_root": True,
            "session_ref_label": "session",
            "session_capture_patterns": [],
            "healthcheck_args": [],
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
            "resume_args": ["resume", "{session_ref}"],
            "continue_args": ["resume", "--last"],
            "resume_in_project_root": True,
            "session_ref_label": "session_id",
            "session_capture_patterns": [
                {"pattern": r"session[_\\s-]?id[:=]\\s*(?P<session_id>[0-9a-fA-F-]{8,})", "source": "combined"},
                {
                    "pattern": r"(?P<session_id>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
                    "source": "combined",
                },
            ],
            "healthcheck_args": ["--version"],
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
            "resume_args": ["--resume", "{session_ref}"],
            "continue_args": ["--continue"],
            "resume_in_project_root": True,
            "session_ref_label": "session_id_or_name",
            "session_capture_patterns": [
                {"pattern": r"session[_\\s-]?id[:=]\\s*(?P<session_id>[A-Za-z0-9._:-]{6,})", "source": "combined"},
                {"pattern": r"--resume\\s+(?P<session_id>[A-Za-z0-9._:-]{6,})", "source": "combined"},
            ],
            "healthcheck_args": ["--version"],
        },
    ]


def default_executor_library() -> list[dict]:
    return normalize_executors(_raw_default_executor_library())


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
    runtime = {item["id"]: executor_runtime_status(item) for item in executors}
    return {
        "executors": [{**item, "runtime": runtime[item["id"]]} for item in executors],
        "enabled_executor_count": len([item for item in executors if item["enabled"]]),
        "available_executor_count": len([item for item in executors if runtime[item["id"]]["available"]]),
        "kinds": EXECUTOR_KINDS,
    }


def get_executor(root: Path | None, executor_id: str) -> dict:
    for executor in load_executor_library(root):
        if executor["id"] == executor_id:
            return executor
    raise ValueError(f"Executor not found: {executor_id}")


def get_default_executor(root: Path | None = None, command_only: bool = False, available_only: bool = False) -> dict:
    executors = [item for item in load_executor_library(root) if item.get("enabled", True)]
    for executor in executors:
        if command_only and executor.get("kind") != "command":
            continue
        if available_only and not executor_runtime_status(executor)["available"]:
            continue
        if executor.get("kind") == "command":
            return executor
    if executors:
        if command_only or available_only:
            raise ValueError("No enabled executor matches the requested availability constraints.")
        return executors[0]
    raise ValueError("No enabled executor is available.")


def get_available_executor(root: Path | None, executor_id: str) -> dict:
    executor = get_executor(root, executor_id)
    runtime = executor_runtime_status(executor)
    if not runtime["available"]:
        raise ValueError(runtime["reason"] or f"Executor is not available: {executor_id}")
    return executor


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
    resume_args: list[str] | None = None,
    continue_args: list[str] | None = None,
    resume_in_project_root: bool = True,
    session_ref_label: str | None = None,
    session_capture_patterns: list[dict] | None = None,
    healthcheck_args: list[str] | None = None,
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
        "resume_args": [str(arg) for arg in (resume_args or [])],
        "continue_args": [str(arg) for arg in (continue_args or [])],
        "resume_in_project_root": bool(resume_in_project_root),
        "session_ref_label": _clean_session_ref_label(session_ref_label),
        "session_capture_patterns": _clean_session_capture_patterns(session_capture_patterns or []),
        "healthcheck_args": [str(arg) for arg in (healthcheck_args or [])],
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
    resume_args: list[str] | None = None,
    continue_args: list[str] | None = None,
    resume_in_project_root: bool = True,
    session_ref_label: str | None = None,
    session_capture_patterns: list[dict] | None = None,
    healthcheck_args: list[str] | None = None,
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
        executor["resume_args"] = [str(arg) for arg in (resume_args or [])]
        executor["continue_args"] = [str(arg) for arg in (continue_args or [])]
        executor["resume_in_project_root"] = bool(resume_in_project_root)
        executor["session_ref_label"] = _clean_session_ref_label(session_ref_label)
        executor["session_capture_patterns"] = _clean_session_capture_patterns(session_capture_patterns or [])
        executor["healthcheck_args"] = [str(arg) for arg in (healthcheck_args or [])]
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


def executor_supports_session_resume(executor: dict) -> bool:
    return bool(executor.get("resume_args") or executor.get("continue_args"))


def extract_executor_session_ref(executor: dict, stdout: str, stderr: str) -> dict | None:
    patterns = _clean_session_capture_patterns(executor.get("session_capture_patterns") or [])
    if not patterns:
        return None
    outputs = {
        "stdout": stdout or "",
        "stderr": stderr or "",
        "combined": "\n".join(part for part in [stdout or "", stderr or ""] if part),
    }
    for item in patterns:
        haystack = outputs.get(item["source"], outputs["combined"])
        if not haystack:
            continue
        match = re.search(item["pattern"], haystack, flags=re.IGNORECASE | re.MULTILINE)
        if not match:
            continue
        session_id = _clean_optional_capture(match.groupdict().get("session_id"))
        session_name = _clean_optional_capture(match.groupdict().get("session_name"))
        session_ref = session_id or session_name
        if not session_ref:
            session_ref = _clean_optional_capture(match.group(1) if match.groups() else None)
        if not session_ref:
            continue
        return {
            "session_id": session_id or session_ref,
            "session_name": session_name,
            "session_ref": session_ref,
            "pattern": item["pattern"],
            "source": item["source"],
        }
    return None


def build_executor_resume_command(
    executor: dict,
    project_root: Path,
    session_ref: str | None = None,
    latest: bool = False,
) -> list[str]:
    binary = str(executor.get("binary") or "").strip()
    if not binary:
        raise ValueError(f"Executor binary is not configured: {executor.get('id')}")
    template_args = executor.get("continue_args") if latest else executor.get("resume_args")
    if not template_args:
        mode_label = "continue" if latest else "resume"
        raise ValueError(f"Executor does not support {mode_label}: {executor.get('id')}")
    if not latest and not str(session_ref or "").strip():
        raise ValueError(f"Executor resume requires a session reference: {executor.get('id')}")
    substitutions = {
        "session_ref": str(session_ref or "").strip(),
        "project_root": str(project_root),
    }
    args = [str(arg).format(**substitutions) for arg in template_args]
    return [binary, *args]


def resume_shell_preview(
    executor: dict,
    project_root: Path,
    session_ref: str | None = None,
    latest: bool = False,
) -> str:
    command = build_executor_resume_command(executor, project_root, session_ref=session_ref, latest=latest)
    preview = shlex.join(command)
    if executor.get("resume_in_project_root", True):
        return f"cd {shlex.quote(str(project_root))} && {preview}"
    return preview


def executor_runtime_status(executor: dict) -> dict:
    kind = str(executor.get("kind") or "command").strip().lower()
    if kind == "manual":
        return {
            "available": True,
            "binary_found": True,
            "binary_path": None,
            "healthcheck_status": "not_applicable",
            "healthcheck_command": None,
            "healthcheck_output": None,
            "reason": None,
        }
    binary = str(executor.get("binary") or "").strip()
    if not binary:
        return {
            "available": False,
            "binary_found": False,
            "binary_path": None,
            "healthcheck_status": "missing_binary",
            "healthcheck_command": None,
            "healthcheck_output": None,
            "reason": f"Executor binary is not configured: {executor.get('id')}",
        }
    resolved = shutil.which(binary)
    if not resolved:
        return {
            "available": False,
            "binary_found": False,
            "binary_path": None,
            "healthcheck_status": "missing_binary",
            "healthcheck_command": None,
            "healthcheck_output": None,
            "reason": f"Executor binary not found in PATH: {binary}",
        }
    healthcheck_args = [str(arg) for arg in executor.get("healthcheck_args", [])]
    if not healthcheck_args:
        return {
            "available": True,
            "binary_found": True,
            "binary_path": resolved,
            "healthcheck_status": "skipped",
            "healthcheck_command": shlex.join([resolved]),
            "healthcheck_output": None,
            "reason": None,
        }
    command = [resolved, *healthcheck_args]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "binary_found": True,
            "binary_path": resolved,
            "healthcheck_status": "failed",
            "healthcheck_command": shlex.join(command),
            "healthcheck_output": str(exc),
            "reason": f"Executor healthcheck failed: {binary}",
        }
    output = (completed.stdout or completed.stderr or "").strip() or None
    if completed.returncode != 0:
        return {
            "available": False,
            "binary_found": True,
            "binary_path": resolved,
            "healthcheck_status": "failed",
            "healthcheck_command": shlex.join(command),
            "healthcheck_output": output,
            "reason": f"Executor healthcheck exited with code {completed.returncode}: {binary}",
        }
    return {
        "available": True,
        "binary_found": True,
        "binary_path": resolved,
        "healthcheck_status": "ok",
        "healthcheck_command": shlex.join(command),
        "healthcheck_output": output,
        "reason": None,
    }


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
    defaults_by_id = {item["id"]: item for item in _raw_default_executor_library()}
    normalized: list[dict] = []
    for index, executor in enumerate(executors):
        executor_id = str(executor.get("id") or "").strip()
        if not executor_id:
            continue
        kind = str(executor.get("kind") or "command").strip().lower()
        if kind not in EXECUTOR_KINDS:
            continue
        default_executor = defaults_by_id.get(executor_id, {})
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
                "resume_args": [str(arg) for arg in executor.get("resume_args", [])],
                "continue_args": [str(arg) for arg in executor.get("continue_args", [])],
                "resume_in_project_root": bool(executor.get("resume_in_project_root", True)),
                "session_ref_label": _clean_session_ref_label(executor.get("session_ref_label")),
                "session_capture_patterns": _clean_session_capture_patterns(executor.get("session_capture_patterns") or []),
                "healthcheck_args": [str(arg) for arg in executor.get("healthcheck_args", default_executor.get("healthcheck_args", []))],
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


def _clean_session_ref_label(value: object) -> str:
    cleaned = str(value or "").strip()
    return cleaned or "session"


def _clean_session_capture_patterns(patterns: list[dict]) -> list[dict]:
    cleaned: list[dict] = []
    for item in patterns:
        if not isinstance(item, dict):
            continue
        pattern = str(item.get("pattern") or "").strip()
        if not pattern:
            continue
        source = str(item.get("source") or "combined").strip().lower()
        if source not in {"stdout", "stderr", "combined"}:
            source = "combined"
        cleaned.append({"pattern": pattern, "source": source})
    return cleaned


def _clean_optional_capture(value: object) -> str | None:
    cleaned = str(value or "").strip()
    return cleaned or None
