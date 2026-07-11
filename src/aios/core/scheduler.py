from __future__ import annotations

from pathlib import Path

from aios.core.ccswitch import with_bridge_runtime_signal
from aios.core.context_builder import inspect_context_pack
from aios.core.executions import latest_execution_for_task
from aios.core.models import get_model, model_runtime_status
from aios.core.router import route_task
from aios.core.runtime_policy import budget_guard_for_task, load_runtime_policy
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
    bridge_confirmation = [item for item in items if item["scheduler_state"] == "bridge_confirmation"]
    review_pending = [item for item in items if item["scheduler_state"] == "review_pending"]
    failed = [item for item in items if item["scheduler_state"] == "failed"]
    active = [item for item in items if item["scheduler_state"] == "active"]

    next_item = None
    runtime_policy = load_runtime_policy(root)
    dispatch_strategy = runtime_policy.get("dispatch_strategy") or "default"
    for state in ("review_pending", "failed", "bridge_confirmation", "ready", "active"):
        state_items = [item for item in items if item["scheduler_state"] == state]
        if state == "ready" and dispatch_strategy == "cheapest_first":
            state_items = sorted(
                state_items,
                key=lambda item: (
                    item.get("budget", {}).get("estimated_total_cost") is None,
                    item.get("budget", {}).get("estimated_total_cost") or 0.0,
                    item.get("task_id") or "",
                ),
            )
        next_item = state_items[0] if state_items else None
        if next_item:
            break

    return {
        "items": items,
        "ready_count": len(ready),
        "blocked_count": len(blocked),
        "bridge_pending_count": len(bridge_confirmation),
        "review_pending_count": len(review_pending),
        "failed_count": len(failed),
        "active_count": len(active),
        "next_task_id": next_item["task_id"] if next_item else None,
        "next_task_title": next_item["task_title"] if next_item else None,
        "next_action": next_item["next_action"] if next_item else None,
        "dispatch_strategy": dispatch_strategy,
    }


def build_scheduler_item(root: Path, task: dict, task_map: dict[str, dict]) -> dict:
    route = route_task(task, root)
    effective_model = route.get("recommended_model") or task.get("recommended_model")
    execution = with_bridge_runtime_signal(root, latest_execution_for_task(root, task["id"]))
    bridge_confirmation_status = str(execution.get("ccswitch_bridge_effective_confirmation_status") or execution.get("ccswitch_bridge_confirmation_status") or "").strip() if execution else ""
    # CLI command executors pass the model directly via --model flag,
    # so ccswitch bridge confirmation is not required for dispatching.
    # Only manual-mode executions need the bridge guard.
    is_cli_mode = bool(execution and execution.get("mode") == "cli")
    dependency_ids = task.get("depends_on_task_ids") or []
    unmet_dependencies = [task_id for task_id in dependency_ids if task_map.get(task_id, {}).get("status") != "done"]
    pack_quality = "unknown"
    try:
        warnings, severe_warnings = inspect_context_pack(root, task, effective_model)
        pack_quality = "warning" if severe_warnings else "ok"
    except Exception:  # noqa: BLE001
        warnings = []
    model_block = _task_model_block_reason(effective_model)

    if task["status"] == "done":
        scheduler_state = "done"
        next_action = None
        reason = "任务已完成。"
    elif execution and execution.get("status") == "review_pending" and execution.get("failure_category") == "verification_failed":
        scheduler_state = "review_pending"
        next_action = execution.get("failure_next_action") or "retry_or_finish"
        reason = execution.get("failure_summary") or "验证失败，等待人工确认或重试。"
    elif execution and execution.get("status") == "review_pending":
        scheduler_state = "review_pending"
        next_action = "review_finish"
        reason = "CLI 执行已完成，等待人工 review 和 finish。"
    elif execution and execution.get("status") == "failed":
        scheduler_state = "failed"
        next_action = execution.get("failure_next_action") or "inspect_retry"
        reason = execution.get("failure_summary") or execution.get("executor_stderr_excerpt") or "最近一次执行失败。"
    elif is_cli_mode and bridge_confirmation_status in ("pending_confirmation", "signal_detected"):
        # CLI executors bypass ccswitch — model is passed via --model flag.
        # Bridge confirmation is irrelevant for automated dispatch.
        scheduler_state = "ready"
        next_action = "run_executor"
        reason = "模型已由执行器命令行参数指定，bridge 对 CLI 模式透明，自动推进。"
    elif execution and bridge_confirmation_status == "confirmed_failed":
        scheduler_state = "failed"
        next_action = "retry_bridge"
        reason = execution.get("ccswitch_bridge_confirmation_note") or execution.get("ccswitch_bridge_error") or "Bridge 已确认失败，需重新切换或重试。"
    elif execution and bridge_confirmation_status == "signal_detected":
        scheduler_state = "bridge_confirmation"
        next_action = "validate_resumed_session"
        reason = "已检测到终端恢复信号，建议先确认恢复到正确会话后再继续。"
    elif execution and bridge_confirmation_status == "pending_confirmation":
        scheduler_state = "bridge_confirmation"
        next_action = "confirm_bridge"
        reason = execution.get("ccswitch_bridge_error") or "Bridge 已执行，等待确认外部切换结果后再继续。"
    elif task["status"] == "running":
        scheduler_state = "active"
        next_action = "monitor_running"
        reason = "任务正在执行或等待执行结果。"
    elif unmet_dependencies:
        scheduler_state = "blocked"
        next_action = "wait_dependencies"
        reason = f"等待依赖任务完成：{', '.join(unmet_dependencies)}"
    elif model_block:
        scheduler_state = "blocked"
        next_action = model_block["next_action"]
        reason = model_block["reason"]
    elif pack_quality == "warning":
        scheduler_state = "blocked"
        next_action = "fix_pack"
        reason = "Context Pack 质量存在强告警，建议先修复上下文后再执行。"
    else:
        budget = budget_guard_for_task(root, task, effective_model)
        if budget["status"] == "blocked":
            scheduler_state = "blocked"
            next_action = "adjust_budget"
            reason = budget["reason"]
        else:
            scheduler_state = "ready"
            next_action = "run_executor"
            reason = "依赖已满足，可以启动执行。"
    if 'budget' not in locals():
        budget = budget_guard_for_task(root, task, effective_model) if task["status"] != "done" else None

    return {
        "task_id": task["id"],
        "task_title": task["title"],
        "task_status": task["status"],
        "recommended_model": effective_model,
        "scheduler_state": scheduler_state,
        "next_action": next_action,
        "reason": reason,
        "depends_on_task_ids": dependency_ids,
        "unmet_dependencies": unmet_dependencies,
        "pack_quality": pack_quality,
        "pack_warnings": warnings,
        "budget": budget,
        "latest_execution_status": execution.get("status") if execution else None,
        "failure_category": execution.get("failure_category") if execution else None,
        "failure_retryable": execution.get("failure_retryable") if execution else None,
        "bridge_confirmation_status": bridge_confirmation_status or None,
        "bridge_resume_signal_status": execution.get("ccswitch_bridge_resume_signal_status") if execution else None,
    }


def _task_model_block_reason(model_id: str | None) -> dict | None:
    model_id = str(model_id or "").strip()
    if not model_id:
        return None
    model = get_model(None, model_id)
    if not model:
        return {
            "next_action": "fix_model_routing",
            "reason": f"推荐模型不存在于全局模型库：{model_id}",
        }
    runtime = model_runtime_status(model)
    if runtime.get("provider_config_status") != "ready":
        return {
            "next_action": "fix_provider_config",
            "reason": f"推荐模型 {model_id} 缺少 provider 配置。",
        }
    if runtime.get("auth_status") == "missing_env":
        return {
            "next_action": "fix_provider_auth_env",
            "reason": runtime.get("reason") or f"推荐模型 {model_id} 缺少鉴权环境变量。",
        }
    if runtime.get("auth_status") == "not_configured":
        return {
            "next_action": "fix_provider_auth_env",
            "reason": runtime.get("reason") or f"推荐模型 {model_id} 未配置鉴权环境变量。",
        }
    if runtime.get("handshake_status") == "failed":
        return {
            "next_action": "probe_provider",
            "reason": runtime.get("reason") or f"推荐模型 {model_id} 最近一次 provider 握手失败。",
        }
    if runtime.get("auth_probe_status") == "failed":
        return {
            "next_action": "fix_provider_auth",
            "reason": runtime.get("reason") or f"推荐模型 {model_id} 的 provider API 权限验证失败。",
        }
    return None
