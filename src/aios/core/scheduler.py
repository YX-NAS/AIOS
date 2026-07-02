from __future__ import annotations

from pathlib import Path

from aios.core.context_builder import inspect_context_pack
from aios.core.executions import latest_execution_for_task
from aios.core.tasks import get_task, load_tasks


def scheduler_summary(root: Path) -> dict:
    tasks = load_tasks(root)
    task_map = {task["id"]: task for task in tasks}
    items: list[dict] = []

    for task in tasks:
        item = build_scheduler_item(root, task, task_map)
        items.append(item)

    ready = [item for item in items if item["scheduler_state"] == "ready"]
    blocked = [item for item in items if item["scheduler_state"] == "blocked"]
    review_pending = [item for item in items if item["scheduler_state"] == "review_pending"]
    failed = [item for item in items if item["scheduler_state"] == "failed"]
    active = [item for item in items if item["scheduler_state"] == "active"]

    next_item = None
    for state in ("review_pending", "failed", "ready", "active"):
        next_item = next((item for item in items if item["scheduler_state"] == state), None)
        if next_item:
            break

    return {
        "items": items,
        "ready_count": len(ready),
        "blocked_count": len(blocked),
        "review_pending_count": len(review_pending),
        "failed_count": len(failed),
        "active_count": len(active),
        "next_task_id": next_item["task_id"] if next_item else None,
        "next_task_title": next_item["task_title"] if next_item else None,
        "next_action": next_item["next_action"] if next_item else None,
    }


def build_scheduler_item(root: Path, task: dict, task_map: dict[str, dict]) -> dict:
    execution = latest_execution_for_task(root, task["id"])
    dependency_ids = task.get("depends_on_task_ids") or []
    unmet_dependencies = [task_id for task_id in dependency_ids if task_map.get(task_id, {}).get("status") != "done"]
    pack_quality = "unknown"
    try:
        warnings, severe_warnings = inspect_context_pack(root, task, task["recommended_model"])
        pack_quality = "warning" if severe_warnings else "ok"
    except Exception:  # noqa: BLE001
        warnings = []

    if task["status"] == "done":
        scheduler_state = "done"
        next_action = None
        reason = "任务已完成。"
    elif execution and execution.get("status") == "review_pending":
        scheduler_state = "review_pending"
        next_action = "review_finish"
        reason = "CLI 执行已完成，等待人工 review 和 finish。"
    elif execution and execution.get("status") == "failed":
        scheduler_state = "failed"
        next_action = "inspect_retry"
        reason = execution.get("executor_stderr_excerpt") or "最近一次执行失败。"
    elif task["status"] == "running":
        scheduler_state = "active"
        next_action = "monitor_running"
        reason = "任务正在执行或等待执行结果。"
    elif unmet_dependencies:
        scheduler_state = "blocked"
        next_action = "wait_dependencies"
        reason = f"等待依赖任务完成：{', '.join(unmet_dependencies)}"
    elif pack_quality == "warning":
        scheduler_state = "blocked"
        next_action = "fix_pack"
        reason = "Context Pack 质量存在强告警，建议先修复上下文后再执行。"
    else:
        scheduler_state = "ready"
        next_action = "run_executor"
        reason = "依赖已满足，可以启动执行。"

    return {
        "task_id": task["id"],
        "task_title": task["title"],
        "task_status": task["status"],
        "scheduler_state": scheduler_state,
        "next_action": next_action,
        "reason": reason,
        "depends_on_task_ids": dependency_ids,
        "unmet_dependencies": unmet_dependencies,
        "pack_quality": pack_quality,
        "pack_warnings": warnings,
        "latest_execution_status": execution.get("status") if execution else None,
    }
