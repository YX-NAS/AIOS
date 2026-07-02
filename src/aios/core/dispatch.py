from __future__ import annotations

from pathlib import Path

from aios.core.ccswitch import confirm_ccswitch_bridge
from aios.core.executions import auto_finish_execution, run_executor_with_auto_finish
from aios.core.executors import executor_summary, get_default_executor
from aios.core.scheduler import scheduler_summary


def auto_progress_next_step(
    root: Path,
    executor_id: str | None = None,
    model: str | None = None,
    refresh_pack: bool = False,
    note: str | None = None,
    auto_finish: bool = False,
    summary: str | None = None,
    actual_model: str | None = None,
    verify_command: str | None = None,
    score: int | None = None,
    score_note: str | None = None,
    auto_commit: bool = False,
    auto_push: bool = False,
    push_remote: str = "origin",
    allow_protected_push: bool = False,
    auto_pr: bool = False,
    pr_base_branch: str = "main",
    auto_confirm_bridge_signal: bool = False,
) -> dict:
    before = scheduler_summary(root)
    next_action = before.get("next_action")

    if next_action == "review_finish" and auto_finish and before.get("next_task_id"):
        finish_result = auto_finish_execution(
            root,
            before["next_task_id"],
            summary=summary,
            actual_model=actual_model,
            verify_command=verify_command,
            score=score,
            score_note=score_note,
            auto_commit=auto_commit,
            auto_push=auto_push,
            push_remote=push_remote,
            allow_protected_push=allow_protected_push,
            auto_pr=auto_pr,
            pr_base_branch=pr_base_branch,
        )
        return {
            "progressed": finish_result["finished"],
            "dispatched": False,
            "auto_finished": finish_result["finished"],
            "executor": None,
            "scheduler_before": before,
            "scheduler_after": scheduler_summary(root),
            "scheduler_item": next_scheduler_item(before),
            "reason": finish_result.get("reason"),
            "route": None,
            "handoff": None,
            **finish_result,
        }

    if next_action == "validate_resumed_session" and auto_confirm_bridge_signal and before.get("next_task_id"):
        confirm_result = confirm_ccswitch_bridge(
            root,
            before["next_task_id"],
            confirmation_status="confirmed_ready",
            note="Auto-confirmed from bridge resume signal.",
        )
        after = scheduler_summary(root)
        return {
            "progressed": True,
            "dispatched": False,
            "auto_finished": False,
            "auto_confirmed_bridge": True,
            "executor": None,
            "scheduler_before": before,
            "scheduler_after": after,
            "scheduler_item": next_scheduler_item(after),
            "reason": "Bridge resume signal detected and auto-confirmed.",
            "task": confirm_result["task"],
            "route": None,
            "handoff": None,
            "execution": confirm_result["execution"],
            "bridge": confirm_result["bridge"],
            "bridge_path": confirm_result["bridge_path"],
        }

    candidate = next_dispatch_candidate(before["items"])
    if candidate is None:
        default_executor = None
        try:
            default_executor = get_default_executor(None, command_only=True, available_only=True)
        except ValueError:
            default_executor = None
        return {
            "progressed": False,
            "dispatched": False,
            "auto_finished": False,
            "auto_confirmed_bridge": False,
            "executor": default_executor,
            "scheduler_before": before,
            "scheduler_after": before,
            "scheduler_item": None,
            "reason": build_dispatch_block_reason(before),
            "task": None,
            "route": None,
            "handoff": None,
            "execution": None,
        }

    executor = None
    selected_executor_id = executor_id
    if not executor_id:
        try:
            executor = get_default_executor(None, command_only=True, available_only=True)
            selected_executor_id = executor["id"]
        except ValueError:
            return {
                "progressed": False,
                "dispatched": False,
                "auto_finished": False,
                "auto_confirmed_bridge": False,
                "executor": None,
                "scheduler_before": before,
                "scheduler_after": before,
                "scheduler_item": candidate,
                "reason": "当前没有可用的命令型执行器，请先运行 `aios executor doctor` 检查 CLI 安装状态。",
                "task": None,
                "route": None,
                "handoff": None,
                "execution": None,
                "executor_summary": executor_summary(),
            }
    result = run_executor_with_auto_finish(
        root,
        candidate["task_id"],
        selected_executor_id,
        model=model,
        refresh_pack=refresh_pack,
        note=note,
        auto_finish=auto_finish,
        summary=summary,
        actual_model=actual_model,
        verify_command=verify_command,
        score=score,
        score_note=score_note,
        auto_commit=auto_commit,
        auto_push=auto_push,
        push_remote=push_remote,
        allow_protected_push=allow_protected_push,
        auto_pr=auto_pr,
        pr_base_branch=pr_base_branch,
    )
    return {
        "progressed": True,
        "dispatched": True,
        "auto_confirmed_bridge": False,
        "scheduler_before": before,
        "scheduler_after": scheduler_summary(root),
        "scheduler_item": candidate,
        **result,
    }


def auto_dispatch_next_task(
    root: Path,
    executor_id: str | None = None,
    model: str | None = None,
    refresh_pack: bool = False,
    note: str | None = None,
    auto_confirm_bridge_signal: bool = False,
) -> dict:
    return auto_progress_next_step(
        root,
        executor_id=executor_id,
        model=model,
        refresh_pack=refresh_pack,
        note=note,
        auto_confirm_bridge_signal=auto_confirm_bridge_signal,
    )


def next_dispatch_candidate(items: list[dict]) -> dict | None:
    for item in items:
        if item.get("scheduler_state") == "ready" and item.get("next_action") == "run_executor":
            return item
    return None


def next_scheduler_item(summary: dict) -> dict | None:
    next_task_id = summary.get("next_task_id")
    if not next_task_id:
        return None
    return next((item for item in summary.get("items", []) if item.get("task_id") == next_task_id), None)


def build_dispatch_block_reason(summary: dict) -> str:
    if summary.get("review_pending_count"):
        return "存在待复核任务，需先 review 并 finish；如需自动收口，请提供 summary 并启用 auto finish。"
    if summary.get("failed_count"):
        return "存在执行失败任务，需先排查失败原因。"
    if summary.get("bridge_pending_count"):
        return "存在待确认的 bridge 切换任务，需先确认外部模型/会话切换结果。"
    if summary.get("active_count"):
        return "存在执行中的任务，暂不自动派发新任务。"
    if summary.get("blocked_count"):
        return "当前没有可执行任务，仍有依赖或 Context Pack 告警阻塞。"
    return "当前没有可自动派发的任务。"
