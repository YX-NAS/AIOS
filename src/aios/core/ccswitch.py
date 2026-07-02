from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode

from aios.core.context_builder import safe_model_name
from aios.core.handoff import build_handoff
from aios.core.executions import latest_execution_for_task, load_executions, save_executions
from aios.core.paths import require_aios
from aios.core.tasks import get_task
from aios.utils.json_utils import write_json
from aios.utils.text import now_iso


FORMAT_VERSION = "1"
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
    task = get_task(root, task_id)
    execution = latest_execution_for_task(root, task_id)
    if not execution:
        raise ValueError("No execution record found. Run `aios run --manual TASK-ID` first.")
    normalized_app = str(app or "").strip().lower()
    if normalized_app not in SUPPORTED_APPS:
        raise ValueError(f"Unsupported ccswitch app: {app}")

    if execution.get("handoff_path"):
        handoff_path = root / execution["handoff_path"]
        handoff_content = handoff_path.read_text(encoding="utf-8") if handoff_path.exists() else None
    else:
        handoff = build_handoff(root, task_id, model, False)
        handoff_content = handoff["content"]

    if not handoff_content:
        raise ValueError("No handoff content available for this task.")

    export_model = (model or execution.get("planned_model") or task.get("recommended_model") or "").strip()
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
