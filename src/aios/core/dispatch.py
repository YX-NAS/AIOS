from __future__ import annotations

from pathlib import Path

from aios.core.executions import run_executor_execution
from aios.core.executors import get_default_executor
from aios.core.scheduler import scheduler_summary


def auto_dispatch_next_task(
    root: Path,
    executor_id: str | None = None,
    model: str | None = None,
    refresh_pack: bool = False,
    note: str | None = None,
) -> dict:
    before = scheduler_summary(root)
    candidate = next_dispatch_candidate(before["items"])
    if candidate is None:
        return {
            "dispatched": False,
            "executor": get_default_executor(None),
            "scheduler_before": before,
            "scheduler_after": before,
            "scheduler_item": None,
            "reason": build_dispatch_block_reason(before),
            "task": None,
            "route": None,
            "handoff": None,
            "execution": None,
        }

    executor = get_default_executor(None) if not executor_id else None
    selected_executor_id = executor_id or executor["id"]
    result = run_executor_execution(
        root,
        candidate["task_id"],
        selected_executor_id,
        model=model,
        refresh_pack=refresh_pack,
        note=note,
    )
    return {
        "dispatched": True,
        "scheduler_before": before,
        "scheduler_after": scheduler_summary(root),
        "scheduler_item": candidate,
        **result,
    }


def next_dispatch_candidate(items: list[dict]) -> dict | None:
    for item in items:
        if item.get("scheduler_state") == "ready" and item.get("next_action") == "run_executor":
            return item
    return None


def build_dispatch_block_reason(summary: dict) -> str:
    if summary.get("review_pending_count"):
        return "存在待复核任务，需先 review 并 finish。"
    if summary.get("failed_count"):
        return "存在执行失败任务，需先排查失败原因。"
    if summary.get("active_count"):
        return "存在执行中的任务，暂不自动派发新任务。"
    if summary.get("blocked_count"):
        return "当前没有可执行任务，仍有依赖或 Context Pack 告警阻塞。"
    return "当前没有可自动派发的任务。"
