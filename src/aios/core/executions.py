from __future__ import annotations

import re
from pathlib import Path

from aios.core.handoff import build_handoff
from aios.core.paths import require_aios
from aios.core.router import route_task
from aios.core.scoring import save_score
from aios.core.tasks import get_task, set_task_status
from aios.core.workflow import finalize_task
from aios.utils.json_utils import read_json, write_json
from aios.utils.text import now_iso, today


ACTIVE_STATUSES = {"prepared", "running"}


def executions_path(root: Path) -> Path:
    return require_aios(root) / "executions.json"


def load_executions(root: Path) -> list[dict]:
    payload = read_json(executions_path(root), {"executions": []})
    executions = payload.get("executions")
    if isinstance(executions, list):
        return executions
    return []


def save_executions(root: Path, executions: list[dict]) -> None:
    write_json(executions_path(root), {"executions": executions})


def latest_execution_for_task(root: Path, task_id: str) -> dict | None:
    matches = [item for item in load_executions(root) if item.get("task_id") == task_id]
    if not matches:
        return None
    return max(matches, key=lambda item: item.get("updated_at") or item.get("finished_at") or "")


def latest_active_execution_for_task(root: Path, task_id: str) -> dict | None:
    matches = [
        item
        for item in load_executions(root)
        if item.get("task_id") == task_id and item.get("status") in ACTIVE_STATUSES
    ]
    if not matches:
        return None
    return max(matches, key=lambda item: item.get("updated_at") or item.get("started_at") or "")


def prepare_manual_execution(
    root: Path,
    task_id: str,
    model: str | None = None,
    refresh_pack: bool = False,
    start: bool = False,
    note: str | None = None,
) -> dict:
    task = get_task(root, task_id)
    route = route_task(task, root)
    handoff = build_handoff(root, task_id, model, refresh_pack)
    selected_model = handoff["model"]
    timestamp = now_iso()
    executions = load_executions(root)
    active = latest_active_execution_for_task(root, task_id)

    if active:
        for item in executions:
            if item.get("execution_id") != active.get("execution_id"):
                continue
            item["planned_model"] = selected_model
            item["fallback_models"] = route["fallback_models"]
            item["pack_path"] = handoff["pack_path"]
            item["handoff_path"] = handoff["handoff_path"]
            item["operator_note"] = note
            if start:
                item["status"] = "running"
                item["started_at"] = item.get("started_at") or timestamp
                set_task_status(root, task_id, "running")
            item["updated_at"] = timestamp
            execution = item
            break
    else:
        execution = {
            "execution_id": next_execution_id(executions),
            "task_id": task["id"],
            "task_title": task["title"],
            "mode": "manual",
            "status": "running" if start else "prepared",
            "planned_model": selected_model,
            "actual_model": None,
            "fallback_models": route["fallback_models"],
            "pack_path": handoff["pack_path"],
            "handoff_path": handoff["handoff_path"],
            "started_at": timestamp if start else None,
            "finished_at": None,
            "operator_note": note,
            "test_command": None,
            "test_result": None,
            "completion_summary": None,
            "updated_at": timestamp,
        }
        executions.append(execution)
        if start:
            set_task_status(root, task_id, "running")

    save_executions(root, executions)
    return {
        "task": get_task(root, task_id),
        "route": route,
        "handoff": handoff,
        "execution": latest_execution_for_task(root, task_id),
    }


def finish_manual_execution(
    root: Path,
    task_id: str,
    summary: str,
    actual_model: str | None = None,
    test_command: str | None = None,
    test_result: str | None = None,
    score: int | None = None,
    score_note: str | None = None,
) -> dict:
    executions = load_executions(root)
    active = latest_active_execution_for_task(root, task_id)
    execution = None
    task = get_task(root, task_id)
    resolved_model = actual_model or task.get("recommended_model")
    timestamp = now_iso()

    if active:
        for item in executions:
            if item.get("execution_id") != active.get("execution_id"):
                continue
            item["status"] = "finished"
            item["actual_model"] = actual_model or item.get("actual_model") or item.get("planned_model")
            item["test_command"] = test_command
            item["test_result"] = test_result
            item["completion_summary"] = summary
            item["finished_at"] = timestamp
            item["updated_at"] = timestamp
            execution = item
            resolved_model = item["actual_model"] or item.get("planned_model") or resolved_model
            break
        save_executions(root, executions)

    task = finalize_task(
        root,
        task_id,
        summary,
        actual_model=resolved_model,
        test_command=test_command,
        test_result=test_result,
    )

    if score is not None:
        save_score(root, task_id, resolved_model or "unknown", score, score_note, task.get("type"))

    return {
        "task": task,
        "execution": execution or latest_execution_for_task(root, task_id),
    }


def execution_summary(root: Path) -> dict:
    executions = load_executions(root)
    active = [item for item in executions if item.get("status") in ACTIVE_STATUSES]
    latest = max(executions, key=lambda item: item.get("updated_at") or "", default=None)
    return {
        "execution_count": len(executions),
        "active_execution_count": len(active),
        "latest_execution_status": latest.get("status") if latest else None,
        "last_execution_updated_at": latest.get("updated_at") if latest else None,
    }


def next_execution_id(executions: list[dict]) -> str:
    date_part = today().replace("-", "")
    pattern = re.compile(rf"^EXEC-{date_part}-(\d{{3}})$")
    max_number = 0
    for item in executions:
        match = pattern.match(item.get("execution_id", ""))
        if match:
            max_number = max(max_number, int(match.group(1)))
    return f"EXEC-{date_part}-{max_number + 1:03d}"
