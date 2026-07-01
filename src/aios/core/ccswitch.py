from __future__ import annotations

import json
from pathlib import Path

from aios.core.context_builder import safe_model_name
from aios.core.executions import latest_execution_for_task, load_executions, save_executions
from aios.core.paths import require_aios
from aios.core.tasks import get_task
from aios.utils.json_utils import write_json
from aios.utils.text import now_iso


FORMAT_VERSION = "1"


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
