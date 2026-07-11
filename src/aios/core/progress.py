from __future__ import annotations

from pathlib import Path

from aios.core.goals import get_active_goal, get_goal, update_goal
from aios.core.router import route_task
from aios.core.scheduler import scheduler_summary
from aios.core.tasks import load_tasks


CURRENT_STATE_ORDER = ("active", "review_pending", "bridge_confirmation", "failed", "ready")
TASK_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def create_goal_with_plan(root: Path, title: str, priority: str = "high", summary: str | None = None) -> dict:
    """Create the project goal and its executable task tree as one user action."""
    from aios.core.goals import create_goal
    from aios.core.tasks import plan_goal

    goal = create_goal(root, title, priority=priority, summary=summary)
    tasks = plan_goal(root, goal["title"], priority=priority, create=True, goal_id=goal["goal_id"])
    root_task_ids = [task["id"] for task in tasks if not task.get("parent_task_id")]
    update_goal(root, goal["goal_id"], {"root_task_ids": root_task_ids})
    progress = advance_goal_progress(root, goal["goal_id"])
    return {"goal": progress["goal"], "tasks": tasks, "progress": progress}


def build_goal_progress(root: Path, goal_id: str) -> dict:
    goal = get_goal(root, goal_id)
    tasks = [task for task in load_tasks(root) if task.get("goal_id") == goal_id]
    schedule = scheduler_summary(root)
    items_by_id = {item["task_id"]: item for item in schedule["items"] if item["task_id"] in {task["id"] for task in tasks}}
    current_item = select_current_task(tasks, items_by_id)
    done_count = sum(1 for task in tasks if task.get("status") == "done")
    total_count = len(tasks)
    progress_percent = round((done_count / total_count) * 100) if total_count else 0
    current_task = next((task for task in tasks if current_item and task["id"] == current_item["task_id"]), None)

    if total_count and done_count == total_count:
        derived_status = "done"
        blocked_reason = None
    elif current_item and current_item.get("scheduler_state") in {"failed", "bridge_confirmation"}:
        derived_status = "blocked"
        blocked_reason = current_item.get("reason")
    elif current_item:
        derived_status = "active"
        blocked_reason = None
    elif total_count:
        derived_status = "blocked"
        blocked_reason = "没有可推进任务，请检查任务依赖、模型状态或执行失败记录。"
    else:
        derived_status = "active"
        blocked_reason = None

    route = route_task(current_task, root) if current_task else None
    return {
        "goal": goal,
        "tasks": tasks,
        "task_count": total_count,
        "done_count": done_count,
        "open_count": total_count - done_count,
        "progress_percent": progress_percent,
        "current_task": current_task,
        "current_scheduler_item": current_item,
        "route": route,
        "next_action": current_item.get("next_action") if current_item else None,
        "reason": current_item.get("reason") if current_item else blocked_reason,
        "derived_status": derived_status,
        "blocked_reason": blocked_reason,
        "state_counts": _state_counts(tasks, items_by_id),
    }


def select_current_task(tasks: list[dict], items_by_id: dict[str, dict]) -> dict | None:
    tasks_by_id = {task["id"]: task for task in tasks}
    for scheduler_state in CURRENT_STATE_ORDER:
        candidates = [item for item in items_by_id.values() if item.get("scheduler_state") == scheduler_state]
        if candidates:
            return min(candidates, key=lambda item: _scheduler_item_sort_key(item, tasks_by_id.get(item["task_id"], {})))
    return None


def advance_goal_progress(root: Path, goal_id: str | None = None) -> dict:
    goal = get_goal(root, goal_id) if goal_id else get_active_goal(root)
    if not goal:
        return empty_progress()
    progress = build_goal_progress(root, goal["goal_id"])
    next_goal = update_goal(
        root,
        goal["goal_id"],
        {
            "status": progress["derived_status"],
            "current_task_id": progress["current_task"]["id"] if progress["current_task"] else None,
            "blocked_reason": progress["blocked_reason"],
        },
    )
    progress["goal"] = next_goal
    return progress


def project_progress_summary(root: Path) -> dict:
    goal = get_active_goal(root)
    if not goal:
        return empty_progress()
    progress = build_goal_progress(root, goal["goal_id"])
    return {**progress, "last_progress_at": progress["goal"].get("updated_at")}


def empty_progress() -> dict:
    return {
        "goal": None,
        "tasks": [],
        "task_count": 0,
        "done_count": 0,
        "open_count": 0,
        "progress_percent": 0,
        "current_task": None,
        "current_scheduler_item": None,
        "route": None,
        "next_action": None,
        "reason": None,
        "derived_status": None,
        "blocked_reason": None,
        "state_counts": {},
        "last_progress_at": None,
    }


def _scheduler_item_sort_key(item: dict, task: dict) -> tuple[int, int, str]:
    return (
        TASK_PRIORITY_ORDER.get(task.get("priority"), 1),
        int(task.get("sequence_order") or 999999),
        item.get("task_id") or "",
    )


def _state_counts(tasks: list[dict], items_by_id: dict[str, dict]) -> dict[str, int]:
    counts: dict[str, int] = {"done": 0}
    for task in tasks:
        state = "done" if task.get("status") == "done" else (items_by_id.get(task["id"], {}).get("scheduler_state") or "unknown")
        counts[state] = counts.get(state, 0) + 1
    return counts
