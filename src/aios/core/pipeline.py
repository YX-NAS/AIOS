"""P4-2: End-to-end multi-task serial pipeline.

Builds on auto_switch to run multiple tasks in sequence:
one finishes, the next one starts automatically.
Stops when the queue is empty or an unrecoverable failure occurs.
"""

from __future__ import annotations

import time
from pathlib import Path

from aios.core.auto_switch import run_auto_pipeline_step
from aios.core.executions import latest_execution_for_task
from aios.core.scheduler import scheduler_summary
from aios.core.takeover import (
    enqueue_takeover,
    should_takeover,
    takeover_suggested_action,
    takeover_summary,
)


def run_full_pipeline(
    root: Path,
    executor_id: str | None = None,
    model: str | None = None,
    auto_switch: bool = True,
    switch_delay: float = 2.0,
    max_tasks: int = 20,
    max_recovery_attempts_per_task: int = 3,
    step_delay_seconds: float = 1.0,
) -> dict:
    """Run all dispatchable tasks in sequence until the queue is empty.

    Returns a summary with per-task results, takeover entries, and timing.
    """
    started_at = time.time()
    task_results: list[dict] = []
    takeover_entries: list[dict] = []
    stopped_at = 0

    for iteration in range(max_tasks):
        summary = scheduler_summary(root)

        if summary.get("ready_count", 0) == 0:
            stopped_at = iteration
            break

        result = run_auto_pipeline_step(
            root,
            executor_id=executor_id,
            model=model,
            auto_switch=auto_switch,
            switch_delay=switch_delay,
            auto_finish=True,
        )

        task_id = result.get("task_id", "")
        pipeline_status = result.get("pipeline_status", "unknown")

        task_result = {
            "iteration": iteration + 1,
            "task_id": task_id,
            "task_title": result.get("task_title", ""),
            "pipeline_status": pipeline_status,
            "model": result.get("model_id", ""),
        }
        task_results.append(task_result)

        # Check for unrecoverable failures
        if pipeline_status in ("switch_failed", "executor_unavailable", "execution_failed", "blocked"):
            execution = latest_execution_for_task(root, task_id) if task_id else None
            failure_category = (execution or {}).get("failure_category")
            recovery_used = (execution or {}).get("auto_recovery_attempts_used") or 0

            if should_takeover(failure_category, recovery_used, max_recovery_attempts_per_task):
                entry = enqueue_takeover(
                    root,
                    task_id or "unknown",
                    reason=result.get("reason", f"Pipeline stopped: {pipeline_status}"),
                    failure_category=failure_category,
                    execution_id=(execution or {}).get("execution_id"),
                    suggested_action=takeover_suggested_action(failure_category),
                    evidence={"pipeline_status": pipeline_status, "pipeline_steps": result.get("pipeline_steps")},
                )
                takeover_entries.append(entry)
                stopped_at = iteration + 1
                break

            # For non-takeover failures, continue to next task
            continue

        # Brief delay between tasks
        if iteration < max_tasks - 1:
            time.sleep(step_delay_seconds)
    else:
        stopped_at = max_tasks

    elapsed = round(time.time() - started_at, 2)

    return {
        "pipeline_completed": len(takeover_entries) == 0,
        "total_tasks": len(task_results),
        "completed_tasks": len([t for t in task_results if t["pipeline_status"] == "completed"]),
        "failed_tasks": len([t for t in task_results if t["pipeline_status"] != "completed"]),
        "takeover_entries": len(takeover_entries),
        "elapsed_seconds": elapsed,
        "task_results": task_results,
        "takeover_summary": takeover_summary(root),
    }
