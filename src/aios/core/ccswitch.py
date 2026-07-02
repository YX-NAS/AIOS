from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

from aios.core.context_builder import safe_model_name
from aios.core.executions import build_execution_resume
from aios.core.handoff import build_handoff
from aios.core.executions import latest_execution_for_task, load_executions, save_executions
from aios.core.models import get_model, infer_provider
from aios.core.paths import require_aios
from aios.core.tasks import get_task
from aios.core.terminal_resume import launch_command_in_terminal
from aios.utils.json_utils import write_json
from aios.utils.text import now_iso


FORMAT_VERSION = "1"
SESSION_HANDOFF_VERSION = "1"
BRIDGE_VERSION = "1"
SUPPORTED_APPS = {"claude", "codex", "gemini", "opencode", "openclaw"}


def export_ccswitch_payload(root: Path, task_id: str, model: str | None = None) -> dict:
    task = get_task(root, task_id)
    execution = latest_execution_for_task(root, task_id)
    if not execution:
        raise ValueError("No execution record found. Run `aios run --manual TASK-ID` first.")

    export_model = (model or execution.get("planned_model") or task.get("recommended_model") or "").strip()
    if not export_model:
        raise ValueError("No export model available for this task.")

    payload = {
        "task_id": task["id"],
        "task_title": task["title"],
        "execution_id": execution["execution_id"],
        "planned_model": execution.get("planned_model"),
        "export_model": export_model,
        "fallback_models": execution.get("fallback_models") or task.get("fallback_models") or [],
        "context_pack_path": execution.get("pack_path"),
        "handoff_path": execution.get("handoff_path"),
        "operator_note": execution.get("operator_note"),
        "exported_at": now_iso(),
        "format_version": FORMAT_VERSION,
    }
    export_path = _write_export_file(root, payload)
    updated_execution = _record_export(root, execution["execution_id"], export_path, payload["exported_at"], export_model)
    return {
        "task": task,
        "payload": payload,
        "export_path": str(export_path.relative_to(root)),
        "execution": updated_execution,
    }


def export_payload_as_text(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def build_ccswitch_deeplink(root: Path, task_id: str, app: str = "codex", model: str | None = None, open_link: bool = False) -> dict:
    task, execution, export_model, normalized_app = _resolve_task_execution(root, task_id, app, model)

    if execution.get("handoff_path"):
        handoff_path = root / execution["handoff_path"]
        handoff_content = handoff_path.read_text(encoding="utf-8") if handoff_path.exists() else None
    else:
        handoff = build_handoff(root, task_id, model, False)
        handoff_content = handoff["content"]

    if not handoff_content:
        raise ValueError("No handoff content available for this task.")

    deeplink = build_prompt_deeplink_url(
        app=normalized_app,
        name=f"{task['id']} {task['title']}",
        content=handoff_content,
        description=f"AIOS handoff for {task['id']} | model={export_model or 'unknown'}",
    )
    opened_at = None
    if open_link:
        open_ccswitch_deeplink(deeplink)
        opened_at = now_iso()
    updated_execution = _record_deeplink(root, execution["execution_id"], deeplink, normalized_app, opened_at)
    return {
        "task": task,
        "deeplink": deeplink,
        "app": normalized_app,
        "opened": bool(opened_at),
        "opened_at": opened_at,
        "execution": updated_execution,
    }


def build_ccswitch_provider_deeplink(
    root: Path,
    task_id: str,
    app: str = "codex",
    model: str | None = None,
    open_link: bool = False,
) -> dict:
    task, execution, export_model, normalized_app = _resolve_task_execution(root, task_id, app, model)
    model_config = get_model(None, export_model) or {}
    provider_name = str(model_config.get("provider") or infer_provider(export_model)).strip().lower()
    deeplink = build_provider_deeplink_url(
        app=normalized_app,
        name=model_config.get("label") or export_model,
        provider=provider_name,
        model=export_model,
        endpoint=model_config.get("endpoint"),
        homepage=model_config.get("homepage"),
        notes=model_config.get("notes") or f"AIOS provider handoff for {task['id']}",
        config_url=model_config.get("config_url"),
    )
    opened_at = None
    if open_link:
        open_ccswitch_deeplink(deeplink)
        opened_at = now_iso()
    updated_execution = _record_provider_deeplink(
        root,
        execution["execution_id"],
        deeplink,
        normalized_app,
        provider_name,
        export_model,
        opened_at,
    )
    return {
        "task": task,
        "deeplink": deeplink,
        "app": normalized_app,
        "provider": provider_name,
        "model": export_model,
        "opened": bool(opened_at),
        "opened_at": opened_at,
        "execution": updated_execution,
    }


def export_ccswitch_session_handoff(
    root: Path,
    task_id: str,
    app: str = "codex",
    model: str | None = None,
) -> dict:
    task, execution, export_model, normalized_app = _resolve_task_execution(root, task_id, app, model)
    prompt_payload = build_ccswitch_deeplink(root, task_id, app=normalized_app, model=export_model, open_link=False)
    provider_payload = build_ccswitch_provider_deeplink(root, task_id, app=normalized_app, model=export_model, open_link=False)
    model_config = get_model(None, export_model) or {}
    provider_name = str(model_config.get("provider") or infer_provider(export_model)).strip().lower()
    handoff = {
        "format_version": SESSION_HANDOFF_VERSION,
        "task_id": task["id"],
        "task_title": task["title"],
        "execution_id": execution["execution_id"],
        "app": normalized_app,
        "provider": provider_name,
        "model": export_model,
        "project_root": str(root),
        "pack_path": execution.get("pack_path"),
        "handoff_path": execution.get("handoff_path"),
        "provider_deeplink": provider_payload["deeplink"],
        "prompt_deeplink": prompt_payload["deeplink"],
        "provider_config": {
            "provider": provider_name,
            "label": model_config.get("label") or export_model,
            "endpoint": model_config.get("endpoint"),
            "homepage": model_config.get("homepage"),
            "notes": model_config.get("notes"),
            "config_url": model_config.get("config_url"),
        },
        "session_search_keywords": [
            task["id"],
            task["title"],
            root.name,
            export_model,
            provider_name,
        ],
        "resume_guidance": [
            "First, try restoring an existing session from CC Switch Session Manager using the project root and task keywords.",
            "If no reusable session exists, import the provider deeplink, then import the prompt deeplink, then start a new session.",
            "After execution, return to AIOS and finish the task so execution records, tests, and delivery artifacts stay aligned.",
        ],
        "exported_at": now_iso(),
    }
    export_path = _write_session_handoff_file(root, handoff)
    updated_execution = _record_session_handoff(
        root,
        execution["execution_id"],
        export_path,
        normalized_app,
        provider_name,
        export_model,
    )
    return {
        "task": task,
        "handoff": handoff,
        "handoff_path": str(export_path.relative_to(root)),
        "execution": updated_execution,
    }


def build_ccswitch_bridge(
    root: Path,
    task_id: str,
    app: str = "codex",
    model: str | None = None,
    latest: bool = False,
    open_bundle: bool = False,
    terminal_app: str = "Terminal",
    delay_ms: int = 1200,
) -> dict:
    if delay_ms < 0:
        raise ValueError("delay_ms must be >= 0.")

    task, execution, export_model, normalized_app = _resolve_task_execution(root, task_id, app, model)
    session_handoff = export_ccswitch_session_handoff(root, task_id, app=normalized_app, model=export_model)
    resume_payload = build_execution_resume(root, task_id, latest=latest)
    mode = resume_payload["mode"]
    exported_at = now_iso()
    payload = {
        "format_version": BRIDGE_VERSION,
        "task_id": task["id"],
        "task_title": task["title"],
        "execution_id": execution["execution_id"],
        "app": normalized_app,
        "model": export_model,
        "provider": session_handoff["handoff"]["provider"],
        "project_root": str(root),
        "bridge_mode": mode,
        "delay_ms": delay_ms,
        "terminal_app": terminal_app,
        "provider_deeplink": session_handoff["handoff"]["provider_deeplink"],
        "prompt_deeplink": session_handoff["handoff"]["prompt_deeplink"],
        "resume_command": resume_payload["command"],
        "session_ref": resume_payload.get("session_ref"),
        "session_handoff_path": session_handoff["handoff_path"],
        "steps": [
            {"type": "deeplink", "label": "provider", "value": session_handoff["handoff"]["provider_deeplink"]},
            {"type": "wait", "label": "provider_delay_ms", "value": delay_ms},
            {"type": "deeplink", "label": "prompt", "value": session_handoff["handoff"]["prompt_deeplink"]},
            {"type": "wait", "label": "prompt_delay_ms", "value": delay_ms},
            {"type": "terminal_command", "label": mode, "value": resume_payload["command"]},
        ],
        "exported_at": exported_at,
    }
    export_path = _write_bridge_file(root, payload)
    opened_at = None
    if open_bundle:
        if sys.platform != "darwin":
            raise ValueError("Opening the full ccswitch bridge is currently supported on macOS only.")
        _open_ccswitch_bridge(payload)
        opened_at = now_iso()
    updated_execution = _record_bridge(
        root,
        execution["execution_id"],
        export_path,
        normalized_app,
        mode,
        terminal_app,
        opened_at,
    )
    return {
        "task": task,
        "bridge": payload,
        "bridge_path": str(export_path.relative_to(root)),
        "opened": bool(opened_at),
        "opened_at": opened_at,
        "execution": updated_execution,
    }


def build_prompt_deeplink_url(app: str, name: str, content: str, description: str | None = None) -> str:
    params = {
        "resource": "prompt",
        "app": app,
        "name": name,
        "content": content,
    }
    if description:
        params["description"] = description
    return f"ccswitch://v1/import?{urlencode(params)}"


def build_provider_deeplink_url(
    app: str,
    name: str,
    provider: str,
    model: str | None = None,
    endpoint: str | None = None,
    homepage: str | None = None,
    notes: str | None = None,
    config_url: str | None = None,
) -> str:
    params = {
        "resource": "provider",
        "app": app,
        "name": name,
    }
    if endpoint:
        params["endpoint"] = endpoint
    if homepage:
        params["homepage"] = homepage
    if model:
        params["model"] = model
    if notes:
        params["notes"] = notes
    if config_url:
        params["configUrl"] = config_url
    return f"ccswitch://v1/import?{urlencode(params)}"


def open_ccswitch_deeplink(deeplink: str) -> None:
    if sys.platform == "darwin":
        command = ["open", deeplink]
    elif sys.platform.startswith("linux"):
        command = ["xdg-open", deeplink]
    elif sys.platform == "win32":
        command = ["cmd", "/c", "start", "", deeplink]
    else:
        raise ValueError(f"Unsupported platform for opening ccswitch deeplink: {sys.platform}")
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "Failed to open deeplink").strip()
        raise ValueError(message)


def _write_export_file(root: Path, payload: dict) -> Path:
    aios_dir = require_aios(root)
    export_dir = aios_dir / "ccswitch"
    export_dir.mkdir(parents=True, exist_ok=True)
    target = export_dir / (
        f"{payload['task_id']}-{payload['execution_id']}-{safe_model_name(payload['export_model'])}-ccswitch.json"
    )
    write_json(target, payload)
    return target


def _write_session_handoff_file(root: Path, payload: dict) -> Path:
    aios_dir = require_aios(root)
    export_dir = aios_dir / "ccswitch"
    export_dir.mkdir(parents=True, exist_ok=True)
    target = export_dir / (
        f"{payload['task_id']}-{payload['execution_id']}-{safe_model_name(payload['model'])}-session-handoff.json"
    )
    write_json(target, payload)
    return target


def _write_bridge_file(root: Path, payload: dict) -> Path:
    aios_dir = require_aios(root)
    export_dir = aios_dir / "ccswitch"
    export_dir.mkdir(parents=True, exist_ok=True)
    target = export_dir / (
        f"{payload['task_id']}-{payload['execution_id']}-{safe_model_name(payload['model'])}-bridge.json"
    )
    write_json(target, payload)
    return target


def _record_export(root: Path, execution_id: str, export_path: Path, exported_at: str, export_model: str) -> dict:
    executions = load_executions(root)
    for item in executions:
        if item.get("execution_id") != execution_id:
            continue
        item["ccswitch_export_path"] = str(export_path.relative_to(root))
        item["ccswitch_exported_at"] = exported_at
        item["ccswitch_export_model"] = export_model
        item["updated_at"] = exported_at
        save_executions(root, executions)
        return item
    raise ValueError(f"Execution not found: {execution_id}")


def _record_deeplink(root: Path, execution_id: str, deeplink: str, app: str, opened_at: str | None) -> dict:
    executions = load_executions(root)
    for item in executions:
        if item.get("execution_id") != execution_id:
            continue
        item["ccswitch_deeplink"] = deeplink
        item["ccswitch_deeplink_app"] = app
        item["ccswitch_deeplink_generated_at"] = now_iso()
        if opened_at:
            item["ccswitch_deeplink_opened_at"] = opened_at
        item["updated_at"] = now_iso()
        save_executions(root, executions)
        return item
    raise ValueError(f"Execution not found: {execution_id}")


def _record_provider_deeplink(
    root: Path,
    execution_id: str,
    deeplink: str,
    app: str,
    provider: str,
    model: str,
    opened_at: str | None,
) -> dict:
    executions = load_executions(root)
    generated_at = now_iso()
    for item in executions:
        if item.get("execution_id") != execution_id:
            continue
        item["ccswitch_provider_deeplink"] = deeplink
        item["ccswitch_provider_deeplink_app"] = app
        item["ccswitch_provider_name"] = provider
        item["ccswitch_provider_model"] = model
        item["ccswitch_provider_generated_at"] = generated_at
        if opened_at:
            item["ccswitch_provider_opened_at"] = opened_at
        item["updated_at"] = generated_at
        save_executions(root, executions)
        return item
    raise ValueError(f"Execution not found: {execution_id}")


def _record_session_handoff(
    root: Path,
    execution_id: str,
    handoff_path: Path,
    app: str,
    provider: str,
    model: str,
) -> dict:
    executions = load_executions(root)
    exported_at = now_iso()
    for item in executions:
        if item.get("execution_id") != execution_id:
            continue
        item["ccswitch_session_handoff_path"] = str(handoff_path.relative_to(root))
        item["ccswitch_session_app"] = app
        item["ccswitch_session_provider"] = provider
        item["ccswitch_session_model"] = model
        item["ccswitch_session_exported_at"] = exported_at
        item["updated_at"] = exported_at
        save_executions(root, executions)
        return item
    raise ValueError(f"Execution not found: {execution_id}")


def _record_bridge(
    root: Path,
    execution_id: str,
    bridge_path: Path,
    app: str,
    mode: str,
    terminal_app: str,
    opened_at: str | None,
) -> dict:
    executions = load_executions(root)
    generated_at = now_iso()
    for item in executions:
        if item.get("execution_id") != execution_id:
            continue
        item["ccswitch_bridge_path"] = str(bridge_path.relative_to(root))
        item["ccswitch_bridge_app"] = app
        item["ccswitch_bridge_mode"] = mode
        item["ccswitch_bridge_terminal_app"] = terminal_app
        item["ccswitch_bridge_generated_at"] = generated_at
        if opened_at:
            item["ccswitch_bridge_opened_at"] = opened_at
        item["updated_at"] = generated_at
        save_executions(root, executions)
        return item
    raise ValueError(f"Execution not found: {execution_id}")


def _open_ccswitch_bridge(payload: dict) -> None:
    delay_seconds = max(int(payload.get("delay_ms") or 0), 0) / 1000
    open_ccswitch_deeplink(payload["provider_deeplink"])
    if delay_seconds:
        time.sleep(delay_seconds)
    open_ccswitch_deeplink(payload["prompt_deeplink"])
    if delay_seconds:
        time.sleep(delay_seconds)
    launch_command_in_terminal(payload["resume_command"], app=str(payload.get("terminal_app") or "Terminal"))


def _resolve_task_execution(root: Path, task_id: str, app: str, model: str | None) -> tuple[dict, dict, str, str]:
    task = get_task(root, task_id)
    execution = latest_execution_for_task(root, task_id)
    if not execution:
        raise ValueError("No execution record found. Run `aios run --manual TASK-ID` first.")
    normalized_app = str(app or "").strip().lower()
    if normalized_app not in SUPPORTED_APPS:
        raise ValueError(f"Unsupported ccswitch app: {app}")
    export_model = (model or execution.get("planned_model") or task.get("recommended_model") or "").strip()
    if not export_model:
        raise ValueError("No export model available for this task.")
    return task, execution, export_model, normalized_app
