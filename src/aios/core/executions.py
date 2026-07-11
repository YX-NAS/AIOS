from __future__ import annotations

import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

from aios.core.context_builder import estimate_tokens
from aios.core.executors import (
    build_executor_command,
    executor_supports_session_resume,
    extract_executor_session_ref,
    get_available_executor,
    get_executor,
    resume_shell_preview,
    shell_preview,
)
from aios.core.git_commit import auto_commit_task_changes, git_snapshot
from aios.core.git_pr import auto_create_pr_draft
from aios.core.git_push import auto_push_commit
from aios.core.handoff import build_handoff
from aios.core.models import estimate_model_cost
from aios.core.paths import require_aios
from aios.core.router import route_task
from aios.core.scoring import save_score
from aios.core.terminal_resume import launch_command_in_terminal
from aios.core.tasks import get_task, set_task_status, update_task_fields
from aios.core.workflow import finalize_task
from aios.utils.json_utils import read_json, write_json
from aios.utils.text import now_iso, today


ACTIVE_STATUSES = {"prepared", "running"}
OPEN_STATUSES = {"prepared", "running", "review_pending"}

NETWORK_FAILURE_MARKERS = [
    "connection refused",
    "could not resolve",
    "name or service not known",
    "temporary failure in name resolution",
    "network is unreachable",
    "connection timed out",
    "read timed out",
    "timed out",
    "dns",
]

AUTH_FAILURE_MARKERS = [
    "unauthorized",
    "forbidden",
    "invalid api key",
    "missing api key",
    "authentication",
    "auth failed",
    "permission denied",
]


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
    return max(matches, key=lambda item: (item.get("updated_at") or item.get("finished_at") or "", item.get("execution_id") or ""))


def get_execution(root: Path, execution_id: str) -> dict | None:
    target = str(execution_id or "").strip()
    if not target:
        return None
    for item in load_executions(root):
        if item.get("execution_id") == target:
            return item
    return None


def latest_active_execution_for_task(root: Path, task_id: str) -> dict | None:
    matches = [
        item
        for item in load_executions(root)
        if item.get("task_id") == task_id and item.get("status") in ACTIVE_STATUSES
    ]
    if not matches:
        return None
    return max(matches, key=lambda item: (item.get("updated_at") or item.get("started_at") or "", item.get("execution_id") or ""))


def latest_open_execution_for_task(root: Path, task_id: str) -> dict | None:
    matches = [
        item
        for item in load_executions(root)
        if item.get("task_id") == task_id and item.get("status") in OPEN_STATUSES
    ]
    if not matches:
        return None
    return max(matches, key=lambda item: (item.get("updated_at") or item.get("started_at") or "", item.get("execution_id") or ""))


def execution_log_path(root: Path, execution_id: str) -> Path:
    return require_aios(root) / "logs" / f"{execution_id}.log"


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
    execution = prepare_execution_record(
        root,
        task,
        route,
        handoff,
        mode="manual",
        status="running" if start else "prepared",
        note=note,
    )
    if start:
        set_task_status(root, task_id, "running")
    progress = None
    if task.get("goal_id"):
        from aios.core.progress import advance_goal_progress

        progress = advance_goal_progress(root, task["goal_id"])
    return {
        "task": get_task(root, task_id),
        "route": route,
        "handoff": handoff,
        "execution": execution,
        "progress": progress,
    }


def run_executor_execution(
    root: Path,
    task_id: str,
    executor_id: str,
    model: str | None = None,
    refresh_pack: bool = False,
    note: str | None = None,
) -> dict:
    executor = get_available_executor(None, executor_id)
    if not executor.get("enabled", True):
        raise ValueError(f"Executor is disabled: {executor_id}")
    if executor.get("kind") == "manual":
        result = prepare_manual_execution(root, task_id, model=model, refresh_pack=refresh_pack, start=True, note=note)
        result["executor"] = executor
        return result

    task = get_task(root, task_id)
    route = route_task(task, root)
    handoff = build_handoff(root, task_id, model, refresh_pack)
    selected_model = handoff["model"]
    execution = prepare_execution_record(
        root,
        task,
        route,
        handoff,
        mode="cli",
        status="running",
        note=note,
        executor=executor,
    )
    set_task_status(root, task_id, "running")
    prompt = Path(root / handoff["handoff_path"]).read_text(encoding="utf-8")
    command = build_executor_command(executor, prompt, selected_model if executor.get("pass_model_as_flag") else None)
    preview = shell_preview(executor, prompt, selected_model if executor.get("pass_model_as_flag") else None)
    env = os.environ.copy()
    env.update({key: str(value) for key, value in (executor.get("env") or {}).items()})
    env.update(
        {
            "AIOS_TASK_ID": task["id"],
            "AIOS_TASK_TITLE": task["title"],
            "AIOS_TASK_MODEL": selected_model,
            "AIOS_CONTEXT_PACK_PATH": str(root / handoff["pack_path"]),
            "AIOS_HANDOFF_PATH": str(root / handoff["handoff_path"]),
            "AIOS_PROJECT_ROOT": str(root),
        }
    )
    timeout_seconds = executor.get("timeout_seconds") or None
    log_path = execution_log_path(root, execution["execution_id"])
    started_monotonic = time.monotonic()

    try:
        completed = subprocess.run(
            command,
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        status = "review_pending" if completed.returncode == 0 else "failed"
        finished_at = now_iso()
        output_tokens = estimate_tokens("\n".join(part for part in [completed.stdout or "", completed.stderr or ""] if part))
        cost = estimate_model_cost(root, selected_model, execution.get("prompt_token_estimate"), output_tokens)
        _write_execution_log(
            log_path,
            preview,
            completed.stdout,
            completed.stderr,
            completed.returncode,
        )
        update_execution(
            root,
            execution["execution_id"],
            {
                "status": status,
                "finished_at": finished_at,
                "updated_at": finished_at,
                "executor_command": preview,
                "executor_exit_code": completed.returncode,
                "executor_log_path": str(log_path.relative_to(root)),
                "executor_stdout_excerpt": _truncate_output(completed.stdout),
                "executor_stderr_excerpt": _truncate_output(completed.stderr),
                "output_token_estimate": output_tokens,
                "total_token_estimate": cost["total_tokens"],
                "estimated_output_cost": cost["estimated_output_cost"],
                "estimated_total_cost": cost["estimated_total_cost"],
                "cost_currency": cost["cost_currency"],
                "duration_seconds": round(time.monotonic() - started_monotonic, 3),
                **(_classify_failed_execution(completed.stdout or "", completed.stderr or "", completed.returncode) if status == "failed" else _clear_failure_fields()),
            },
        )
        _auto_attach_executor_session(root, execution["execution_id"], executor, completed.stdout, completed.stderr)
    except FileNotFoundError as exc:
        finished_at = now_iso()
        update_execution(
            root,
            execution["execution_id"],
            {
                "status": "failed",
                "finished_at": finished_at,
                "updated_at": finished_at,
                "executor_command": preview,
                "executor_exit_code": None,
                "executor_log_path": str(log_path.relative_to(root)),
                "executor_stderr_excerpt": str(exc),
                "duration_seconds": round(time.monotonic() - started_monotonic, 3),
                **_failure_fields(
                    category="executor_missing_binary",
                    summary=f"Executor binary not found: {executor.get('binary')}",
                    retryable=False,
                    next_action="fix_executor_binary",
                    source="executor",
                ),
            },
        )
        raise ValueError(f"Executor binary not found: {executor.get('binary')}") from exc
    except subprocess.TimeoutExpired as exc:
        finished_at = now_iso()
        output_tokens = estimate_tokens("\n".join(part for part in [exc.stdout or "", exc.stderr or ""] if part))
        _write_execution_log(
            log_path,
            preview,
            exc.stdout or "",
            exc.stderr or f"Execution timed out after {timeout_seconds} seconds.",
            None,
        )
        update_execution(
            root,
            execution["execution_id"],
            {
                "status": "failed",
                "finished_at": finished_at,
                "updated_at": finished_at,
                "executor_command": preview,
                "executor_exit_code": None,
                "executor_log_path": str(log_path.relative_to(root)),
                "executor_stdout_excerpt": _truncate_output(exc.stdout or ""),
                "executor_stderr_excerpt": _truncate_output(exc.stderr or f"Execution timed out after {timeout_seconds} seconds."),
                "output_token_estimate": output_tokens,
                "total_token_estimate": int(execution.get("prompt_token_estimate") or 0) + output_tokens,
                "duration_seconds": round(time.monotonic() - started_monotonic, 3),
                **_failure_fields(
                    category="executor_timeout",
                    summary=f"Executor timed out after {timeout_seconds} seconds.",
                    retryable=True,
                    next_action="inspect_timeout",
                    source="executor",
                ),
            },
        )
        raise ValueError(f"Executor timed out after {timeout_seconds} seconds.") from exc

    return {
        "task": get_task(root, task_id),
        "route": route,
        "handoff": handoff,
        "execution": get_execution(root, execution["execution_id"]),
        "executor": executor,
    }


def attach_execution_session(
    root: Path,
    task_id: str,
    executor_id: str | None = None,
    session_id: str | None = None,
    session_name: str | None = None,
    session_note: str | None = None,
) -> dict:
    execution = latest_open_execution_for_task(root, task_id) or latest_execution_for_task(root, task_id)
    if not execution:
        raise ValueError("No execution record found. Start one execution before attaching a session.")

    resolved_executor_id = (executor_id or execution.get("executor_id") or "").strip()
    if not resolved_executor_id:
        raise ValueError("Executor ID is required to attach a session.")
    executor = get_executor(None, resolved_executor_id)
    if not executor_supports_session_resume(executor):
        raise ValueError(f"Executor does not support session resume: {resolved_executor_id}")

    resolved_session_id = str(session_id or "").strip() or None
    resolved_session_name = str(session_name or "").strip() or None
    if not resolved_session_id and not resolved_session_name:
        raise ValueError("Use `session_id` or `session_name` to attach one session.")

    session_ref = resolved_session_id or resolved_session_name
    attached_at = now_iso()
    updates = {
        "executor_id": executor["id"],
        "executor_label": executor.get("label"),
        "executor_session_id": resolved_session_id,
        "executor_session_name": resolved_session_name,
        "executor_session_note": str(session_note or "").strip() or None,
        "executor_session_attached_at": attached_at,
        "executor_session_auto_captured": False,
        "executor_session_capture_source": "manual",
        "executor_session_capture_pattern": None,
        "executor_session_ref_label": executor.get("session_ref_label") or "session",
        "executor_resume_supported": True,
        "executor_resume_command": resume_shell_preview(executor, root, session_ref=session_ref, latest=False),
        "executor_continue_command": resume_shell_preview(executor, root, latest=True) if executor.get("continue_args") else None,
        "executor_resume_history_session_ref": None,
        "executor_resume_history_session_kind": None,
        "executor_resume_history_task_id": None,
        "executor_resume_history_task_title": None,
        "executor_resume_history_execution_id": None,
        "updated_at": attached_at,
    }
    updated_execution = update_execution(root, execution["execution_id"], updates)
    return {
        "task": get_task(root, task_id),
        "execution": updated_execution,
        "executor": executor,
        "session_ref": session_ref,
    }


def build_execution_resume(
    root: Path,
    task_id: str,
    latest: bool = False,
    history_fallback: bool = False,
) -> dict:
    execution = latest_open_execution_for_task(root, task_id) or latest_execution_for_task(root, task_id)
    if not execution:
        raise ValueError("No execution record found for this task.")
    executor_id = str(execution.get("executor_id") or "").strip()
    if not executor_id:
        raise ValueError("This execution has no executor attached yet.")
    executor = get_executor(None, executor_id)
    if not executor_supports_session_resume(executor):
        raise ValueError(f"Executor does not support session resume: {executor_id}")

    session_ref = str(execution.get("executor_session_id") or execution.get("executor_session_name") or "").strip() or None
    mode = "latest"
    history_candidate = None
    if not latest and session_ref:
        mode = "attached"
        command = resume_shell_preview(executor, root, session_ref=session_ref, latest=False)
    elif not latest and history_fallback:
        history_candidate = find_best_historical_session(root, task_id, executor_id=executor_id)
        if history_candidate:
            mode = "history"
            session_ref = history_candidate["session_ref"]
            command = resume_shell_preview(executor, root, session_ref=session_ref, latest=False)
        elif executor.get("continue_args"):
            command = resume_shell_preview(executor, root, latest=True)
        else:
            label = executor.get("session_ref_label") or "session"
            raise ValueError(f"No attached {label} is available, and no historical session candidate was found.")
    else:
        if not executor.get("continue_args"):
            label = executor.get("session_ref_label") or "session"
            raise ValueError(f"No attached {label} is available, and this executor does not support continue-latest.")
        command = resume_shell_preview(executor, root, latest=True)

    generated_at = now_iso()
    updated_execution = update_execution(
        root,
        execution["execution_id"],
        {
            "executor_resume_supported": True,
            "executor_resume_last_command": command,
            "executor_resume_last_mode": mode,
            "executor_resume_generated_at": generated_at,
            "executor_resume_history_session_ref": history_candidate.get("session_ref") if history_candidate else None,
            "executor_resume_history_session_kind": history_candidate.get("session_kind") if history_candidate else None,
            "executor_resume_history_task_id": history_candidate.get("task_id") if history_candidate else None,
            "executor_resume_history_task_title": history_candidate.get("task_title") if history_candidate else None,
            "executor_resume_history_execution_id": history_candidate.get("execution_id") if history_candidate else None,
            "updated_at": generated_at,
        },
    )
    return {
        "task": get_task(root, task_id),
        "execution": updated_execution,
        "executor": executor,
        "mode": mode,
        "session_ref": session_ref,
        "command": command,
    }


def open_execution_resume_in_terminal(
    root: Path,
    task_id: str,
    latest: bool = False,
    history_fallback: bool = False,
    terminal_app: str = "Terminal",
) -> dict:
    result = build_execution_resume(root, task_id, latest=latest, history_fallback=history_fallback)
    launch_result = launch_command_in_terminal(result["command"], app=terminal_app)
    launched_at = now_iso()
    updated_execution = update_execution(
        root,
        result["execution"]["execution_id"],
        {
            "executor_terminal_launch_supported": True,
            "executor_terminal_launch_status": "opened",
            "executor_terminal_launch_app": launch_result["app"],
            "executor_terminal_launch_command": launch_result["command"],
            "executor_terminal_launch_mode": result["mode"],
            "executor_terminal_launch_at": launched_at,
            "updated_at": launched_at,
        },
    )
    result["execution"] = updated_execution
    result["terminal"] = launch_result
    return result


def run_executor_with_auto_finish(
    root: Path,
    task_id: str,
    executor_id: str,
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
) -> dict:
    result = run_executor_execution(
        root,
        task_id,
        executor_id,
        model=model,
        refresh_pack=refresh_pack,
        note=note,
    )
    result["auto_finished"] = False
    result["verification"] = None
    result["reason"] = None
    result["git_commit"] = None
    if not auto_finish:
        return result
    auto_finish_result = auto_finish_execution(
        root,
        task_id,
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
    result["auto_finished"] = auto_finish_result["finished"]
    result["verification"] = auto_finish_result.get("verification")
    result["reason"] = auto_finish_result.get("reason")
    result["git_commit"] = auto_finish_result.get("git_commit")
    if auto_finish_result["finished"]:
        result["task"] = auto_finish_result["task"]
        result["execution"] = auto_finish_result["execution"]
    else:
        result["execution"] = auto_finish_result["execution"]
    return result


def retry_execution_after_verification_failure(
    root: Path,
    task_id: str,
    executor_id: str,
    verification: dict,
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
) -> dict | None:
    try:
        executor = get_available_executor(None, executor_id)
    except ValueError:
        return None

    retry = requeue_execution_after_verification_failure(root, task_id, verification)
    if not retry["retried"]:
        return None

    result = run_executor_with_auto_finish(
        root,
        task_id,
        executor["id"],
        model=retry["retry_model"],
        refresh_pack=False,
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
    if result.get("execution"):
        updated_retry_execution = update_execution(
            root,
            result["execution"]["execution_id"],
            {
                "retry_source_execution_id": retry["execution"]["execution_id"],
                "retry_source_model": retry["failed_model"],
                "retry_attempt": retry["retry_attempt"],
            },
        )
        result["execution"] = updated_retry_execution
    result["retry"] = retry
    result["previous_verification"] = verification
    result["auto_retried"] = True
    return result


def attempt_automatic_recovery(
    root: Path,
    task_id: str,
    executor_id: str,
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
) -> dict | None:
    execution = latest_execution_for_task(root, task_id)
    if not execution:
        return None

    if execution.get("status") == "review_pending" and execution.get("failure_category") == "verification_failed":
        verification = {
            "summary": execution.get("test_result") or execution.get("failure_summary") or "Verification failed.",
            "exit_code": execution.get("executor_exit_code") or 1,
        }
        return retry_execution_after_verification_failure(
            root,
            task_id,
            executor_id,
            verification,
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

    recovery = requeue_failed_execution_for_recovery(root, task_id)
    if not recovery or not recovery.get("retried"):
        return None

    result = run_executor_with_auto_finish(
        root,
        task_id,
        executor_id,
        model=recovery["retry_model"],
        refresh_pack=False,
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
    if result.get("execution"):
        updated_recovery_execution = update_execution(
            root,
            result["execution"]["execution_id"],
            {
                "retry_source_execution_id": recovery["execution"]["execution_id"],
                "retry_source_model": recovery["failed_model"],
                "retry_attempt": recovery["retry_attempt"],
                "recovery_strategy": recovery["recovery_strategy"],
                "recovery_trigger": recovery["recovery_trigger"],
            },
        )
        result["execution"] = updated_recovery_execution
    result["recovery"] = recovery
    result["auto_recovered"] = True
    return result


def run_automatic_recovery_chain(
    root: Path,
    task_id: str,
    executor_id: str,
    *,
    max_attempts: int,
    policy: dict | None = None,
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
) -> dict | None:
    task = get_task(root, task_id)
    attempts_used = int(task.get("auto_recovery_count") or 0)
    latest = latest_execution_for_task(root, task_id)
    allowed_attempts, blocked_reason, next_retry_at = _automatic_recovery_guard(task, latest, policy, max_attempts)
    if blocked_reason:
        if latest:
            updated = update_execution(
                root,
                latest["execution_id"],
                {
                    "recovery_blocked_reason": blocked_reason,
                    "recovery_next_retry_at": next_retry_at,
                    "updated_at": now_iso(),
                },
            )
            latest = updated
        return None
    if attempts_used >= allowed_attempts:
        return None

    chain: list[dict] = []
    last_result: dict | None = None

    while attempts_used < allowed_attempts:
        result = attempt_automatic_recovery(
            root,
            task_id,
            executor_id,
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
        if not result:
            break

        chain.append(
            {
                "execution_id": (result.get("execution") or {}).get("execution_id"),
                "status": (result.get("execution") or {}).get("status"),
                "trigger": (result.get("recovery") or {}).get("recovery_trigger")
                or (result.get("retry") or {}).get("retry_trigger")
                or (result.get("execution") or {}).get("failure_category"),
                "strategy": (result.get("recovery") or {}).get("recovery_strategy")
                or ("reroute_fallback_model" if result.get("auto_retried") else None),
            }
        )
        last_result = result
        task = get_task(root, task_id)
        attempts_used = int(task.get("auto_recovery_count") or 0)
        latest = result.get("execution")
        if not latest:
            break
        if latest.get("status") == "finished":
            break
        if latest.get("status") == "review_pending" and latest.get("failure_category") != "verification_failed":
            break
        if latest.get("status") not in {"failed", "review_pending"}:
            break
        allowed_attempts, blocked_reason, next_retry_at = _automatic_recovery_guard(task, latest, policy, max_attempts)
        if blocked_reason:
            updated = update_execution(
                root,
                latest["execution_id"],
                {
                    "recovery_blocked_reason": blocked_reason,
                    "recovery_next_retry_at": next_retry_at,
                    "updated_at": now_iso(),
                },
            )
            if last_result is not None:
                last_result["execution"] = updated
            break

    if not last_result:
        return None
    last_result["recovery_chain"] = chain
    last_result["auto_recovery_attempts_used"] = attempts_used
    last_result["auto_recovery_limit_reached"] = attempts_used >= allowed_attempts
    return last_result


def finish_manual_execution(
    root: Path,
    task_id: str,
    summary: str,
    actual_model: str | None = None,
    test_command: str | None = None,
    test_result: str | None = None,
    score: int | None = None,
    score_note: str | None = None,
    auto_commit: bool = False,
    auto_push: bool = False,
    push_remote: str = "origin",
    allow_protected_push: bool = False,
    auto_pr: bool = False,
    pr_base_branch: str = "main",
) -> dict:
    executions = load_executions(root)
    active = latest_open_execution_for_task(root, task_id)
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
            item["status"] = "finished"
            item["duration_seconds"] = execution_duration_seconds({**item, "finished_at": timestamp}) or item.get("duration_seconds")
            item.update(_clear_failure_fields())
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

    commit_result = None
    if auto_commit:
        commit_result = auto_commit_task_changes(root, execution or latest_execution_for_task(root, task_id) or {}, task, summary)
        if execution:
            update_execution(
                root,
                execution["execution_id"],
                {
                    "auto_commit_enabled": True,
                    "auto_commit_status": "committed" if commit_result.get("committed") else "skipped",
                    "auto_commit_reason": commit_result.get("reason"),
                    "git_commit_after": commit_result.get("commit"),
                    "git_branch_after": commit_result.get("branch"),
                    "auto_commit_paths": commit_result.get("paths"),
                    "auto_commit_subject": commit_result.get("subject"),
                    "updated_at": now_iso(),
                },
            )
            execution = latest_execution_for_task(root, task_id)

    push_result = None
    if auto_push:
        push_result = auto_push_commit(
            root,
            commit_result,
            remote=push_remote,
            allow_protected=allow_protected_push,
        )
        latest_execution = execution or latest_execution_for_task(root, task_id)
        if latest_execution:
            update_execution(
                root,
                latest_execution["execution_id"],
                {
                    "auto_push_enabled": True,
                    "auto_push_status": "pushed" if push_result.get("pushed") else "skipped",
                    "auto_push_reason": push_result.get("reason"),
                    "auto_push_remote": push_result.get("remote"),
                    "auto_push_branch": push_result.get("branch"),
                    "updated_at": now_iso(),
                },
            )
            execution = latest_execution_for_task(root, task_id)

    pr_result = None
    if auto_pr:
        pr_result = auto_create_pr_draft(
            root,
            task,
            summary,
            push_result,
            base_branch=pr_base_branch,
        )
        latest_execution = execution or latest_execution_for_task(root, task_id)
        if latest_execution:
            update_execution(
                root,
                latest_execution["execution_id"],
                {
                    "auto_pr_enabled": True,
                    "auto_pr_status": "created" if pr_result.get("created") else "skipped",
                    "auto_pr_reason": pr_result.get("reason"),
                    "auto_pr_url": pr_result.get("url"),
                    "auto_pr_number": pr_result.get("number"),
                    "auto_pr_base_branch": pr_result.get("base_branch"),
                    "updated_at": now_iso(),
                },
            )
            execution = latest_execution_for_task(root, task_id)

    progress = None
    if task.get("goal_id"):
        from aios.core.progress import advance_goal_progress

        progress = advance_goal_progress(root, task["goal_id"])

    return {
        "task": task,
        "execution": execution or latest_execution_for_task(root, task_id),
        "git_commit": commit_result,
        "git_push": push_result,
        "git_pr": pr_result,
        "progress": progress,
    }


def auto_finish_execution(
    root: Path,
    task_id: str,
    summary: str | None,
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
) -> dict:
    if not summary:
        raise ValueError("Use `--summary` when enabling auto finish.")
    execution = latest_open_execution_for_task(root, task_id) or latest_execution_for_task(root, task_id)
    if not execution:
        raise ValueError(f"No execution record for {task_id}.")
    if execution.get("status") != "review_pending":
        raise ValueError(f"Execution is not ready for auto finish: {task_id}")

    verification = None
    final_test_result = None
    if verify_command:
        verification = run_verification_command(root, verify_command)
        final_test_result = verification["summary"]
        update_execution(
            root,
            execution["execution_id"],
            {
                "test_command": verify_command,
                "test_result": final_test_result,
                "updated_at": now_iso(),
                **(_failure_fields(
                    category="verification_failed",
                    summary=f"Verification failed with exit code {verification['exit_code']}.",
                    retryable=True,
                    next_action="retry_or_finish",
                    source="verification",
                ) if verification["exit_code"] != 0 else _clear_failure_fields()),
            },
        )
        if verification["exit_code"] != 0:
            return {
                "finished": False,
                "reason": f"Verification failed with exit code {verification['exit_code']}.",
                "task": get_task(root, task_id),
                "execution": latest_execution_for_task(root, task_id),
                "verification": verification,
            }

    result = finish_manual_execution(
        root,
        task_id,
        summary,
        actual_model=actual_model,
        test_command=verify_command,
        test_result=final_test_result,
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
        "finished": True,
        "reason": None,
        **result,
        "verification": verification,
    }


def requeue_execution_after_verification_failure(root: Path, task_id: str, verification: dict | None = None) -> dict:
    execution = latest_execution_for_task(root, task_id)
    if not execution:
        raise ValueError(f"No execution record for {task_id}.")
    if execution.get("status") != "review_pending":
        raise ValueError(f"Execution is not ready for retry: {task_id}")

    task = get_task(root, task_id)
    failed_model = str(execution.get("actual_model") or execution.get("planned_model") or task.get("recommended_model") or "").strip()
    retry_models = _retry_model_candidates(task, failed_model)
    if not retry_models:
        return {
            "retried": False,
            "reason": "Verification failed and no fallback model remains for automatic retry.",
            "task": task,
            "execution": execution,
            "failed_model": failed_model or None,
            "retry_model": None,
            "retry_attempt": int(task.get("auto_retry_count") or 0),
        }

    retry_model = retry_models[0]
    remaining_models = retry_models[1:]
    retry_attempt = int(task.get("auto_retry_count") or 0) + 1
    timestamp = now_iso()
    retry_reason = (verification or {}).get("summary") or "Verification failed."

    updated_execution = update_execution(
        root,
        execution["execution_id"],
        {
            "status": "retry_queued",
            "finished_at": timestamp,
            "updated_at": timestamp,
            "retry_trigger": "verification_failed",
            "retry_reason": retry_reason,
            "retry_failed_model": failed_model or None,
            "retry_next_model": retry_model,
            "retry_attempt": retry_attempt,
        },
    )
    updated_task = update_task_fields(
        root,
        task_id,
        {
            "status": "todo",
            "recommended_model": retry_model,
            "fallback_models": remaining_models,
            "auto_retry_count": retry_attempt,
            "auto_recovery_count": int(task.get("auto_recovery_count") or 0) + 1,
            "last_retry_at": timestamp,
            "last_retry_reason": retry_reason,
            "last_failed_model": failed_model or None,
            "last_retry_execution_id": execution["execution_id"],
            "last_retry_trigger": "verification_failed",
            "last_recovery_at": timestamp,
            "last_recovery_reason": retry_reason,
            "last_recovery_execution_id": execution["execution_id"],
            "last_recovery_trigger": "verification_failed",
            "last_recovery_strategy": "reroute_fallback_model",
        },
    )
    return {
        "retried": True,
        "reason": None,
        "task": updated_task,
        "execution": updated_execution,
        "failed_model": failed_model or None,
        "retry_model": retry_model,
        "remaining_fallback_models": remaining_models,
        "retry_attempt": retry_attempt,
        "recovery_strategy": "reroute_fallback_model",
        "recovery_trigger": "verification_failed",
    }


def requeue_failed_execution_for_recovery(root: Path, task_id: str) -> dict | None:
    execution = latest_execution_for_task(root, task_id)
    if not execution or execution.get("status") != "failed":
        return None
    if execution.get("recovery_disposition") == "queued":
        return {
            "retried": False,
            "reason": "This failed execution has already been queued for automatic recovery.",
            "task": get_task(root, task_id),
            "execution": execution,
            "failed_model": execution.get("actual_model") or execution.get("planned_model"),
            "retry_model": None,
            "retry_attempt": int(execution.get("retry_attempt") or 0),
            "recovery_strategy": None,
            "recovery_trigger": execution.get("failure_category"),
        }

    category = str(execution.get("failure_category") or "").strip()
    if category not in {"provider_unreachable", "executor_timeout", "executor_nonzero_exit"}:
        return {
            "retried": False,
            "reason": "Current failure category is not eligible for automatic recovery.",
            "task": get_task(root, task_id),
            "execution": execution,
            "failed_model": execution.get("actual_model") or execution.get("planned_model"),
            "retry_model": None,
            "retry_attempt": int(execution.get("retry_attempt") or 0),
            "recovery_strategy": None,
            "recovery_trigger": category or None,
        }

    task = get_task(root, task_id)
    failed_model = str(execution.get("actual_model") or execution.get("planned_model") or task.get("recommended_model") or "").strip()
    retry_attempt = int(execution.get("retry_attempt") or 0) + 1
    timestamp = now_iso()
    trigger_reason = execution.get("failure_summary") or "Execution failed."

    updated_execution = update_execution(
        root,
        execution["execution_id"],
        {
            "status": "retry_queued",
            "finished_at": timestamp,
            "updated_at": timestamp,
            "retry_trigger": category,
            "retry_reason": trigger_reason,
            "retry_failed_model": failed_model or None,
            "retry_next_model": failed_model or None,
            "retry_attempt": retry_attempt,
            "recovery_disposition": "queued",
            "recovery_strategy": "rerun_same_model",
        },
    )
    updated_task = update_task_fields(
        root,
        task_id,
        {
            "status": "todo",
            "auto_recovery_count": int(task.get("auto_recovery_count") or 0) + 1,
            "last_recovery_at": timestamp,
            "last_recovery_reason": trigger_reason,
            "last_recovery_execution_id": execution["execution_id"],
            "last_recovery_trigger": category,
            "last_recovery_strategy": "rerun_same_model",
        },
    )
    return {
        "retried": True,
        "reason": None,
        "task": updated_task,
        "execution": updated_execution,
        "failed_model": failed_model or None,
        "retry_model": failed_model or None,
        "retry_attempt": retry_attempt,
        "recovery_strategy": "rerun_same_model",
        "recovery_trigger": category,
    }


def _automatic_recovery_guard(task: dict, execution: dict | None, policy: dict | None, max_attempts: int) -> tuple[int, str | None, str | None]:
    category = str((execution or {}).get("failure_category") or "verification_failed").strip()
    limits = dict((policy or {}).get("auto_recovery_limits") or {})
    category_limit = limits.get(category)
    if category_limit is None:
        category_limit = max_attempts
    category_limit = int(category_limit)
    allowed_attempts = min(max_attempts, category_limit)
    attempts_used = int(task.get("auto_recovery_count") or 0)
    if attempts_used >= allowed_attempts:
        return allowed_attempts, f"自动恢复已达到当前失败类别上限：{category} -> {allowed_attempts} 次。", None

    cooldown_seconds = int((policy or {}).get("auto_recovery_cooldown_seconds") or 0)
    if cooldown_seconds <= 0:
        return allowed_attempts, None, None
    last_recovery_at = str(task.get("last_recovery_at") or "").strip()
    if not last_recovery_at:
        return allowed_attempts, None, None
    try:
        last_dt = datetime.fromisoformat(last_recovery_at)
    except ValueError:
        return allowed_attempts, None, None
    now_dt = datetime.fromisoformat(now_iso())
    elapsed = (now_dt - last_dt).total_seconds()
    if elapsed >= cooldown_seconds:
        return allowed_attempts, None, None
    next_retry_at = last_dt.timestamp() + cooldown_seconds
    next_retry_iso = datetime.fromtimestamp(next_retry_at).isoformat(timespec="seconds")
    return allowed_attempts, f"自动恢复冷却中，需等待到 {next_retry_iso}。", next_retry_iso


def execution_summary(root: Path) -> dict:
    executions = load_executions(root)
    active = [item for item in executions if item.get("status") in ACTIVE_STATUSES]
    latest = max(executions, key=lambda item: item.get("updated_at") or "", default=None)
    finished_with_duration = [item for item in executions if execution_duration_seconds(item) is not None]
    total_prompt_tokens = sum(int(item.get("prompt_token_estimate") or 0) for item in executions)
    total_output_tokens = sum(int(item.get("output_token_estimate") or 0) for item in executions)
    total_cost = round(sum(float(item.get("estimated_total_cost") or 0.0) for item in executions), 6)
    return {
        "execution_count": len(executions),
        "active_execution_count": len(active),
        "latest_execution_status": latest.get("status") if latest else None,
        "last_execution_updated_at": latest.get("updated_at") if latest else None,
        "latest_execution_duration_seconds": execution_duration_seconds(latest) if latest else None,
        "total_prompt_token_estimate": total_prompt_tokens,
        "total_output_token_estimate": total_output_tokens,
        "total_token_estimate": total_prompt_tokens + total_output_tokens,
        "total_estimated_cost": total_cost,
        "cost_currency": latest.get("cost_currency") if latest and latest.get("cost_currency") else "USD",
        "average_duration_seconds": round(sum(execution_duration_seconds(item) or 0.0 for item in finished_with_duration) / len(finished_with_duration), 3) if finished_with_duration else None,
    }


def list_execution_sessions(
    root: Path,
    task_id: str | None = None,
    executor_id: str | None = None,
    query: str | None = None,
    limit: int = 5,
) -> list[dict]:
    target_task = get_task(root, task_id) if task_id else None
    target_execution = latest_execution_for_task(root, task_id) if task_id else None
    resolved_executor_id = str(executor_id or (target_execution or {}).get("executor_id") or "").strip() or None
    target_title = str((target_task or {}).get("title") or "").strip()
    target_model = str((target_task or {}).get("recommended_model") or "").strip()
    query_text = str(query or "").strip().lower()

    sessions_by_key: dict[tuple[str, str, str], dict] = {}
    for execution in load_executions(root):
        session_ref = _execution_session_ref(execution)
        if not session_ref:
            continue
        candidate_executor_id = str(execution.get("executor_id") or "").strip()
        if resolved_executor_id and candidate_executor_id != resolved_executor_id:
            continue
        candidate = {
            "execution_id": execution.get("execution_id"),
            "task_id": execution.get("task_id"),
            "task_title": execution.get("task_title"),
            "execution_status": execution.get("status"),
            "executor_id": candidate_executor_id or None,
            "executor_label": execution.get("executor_label"),
            "session_id": execution.get("executor_session_id"),
            "session_name": execution.get("executor_session_name"),
            "session_ref": session_ref,
            "session_kind": "session_id" if execution.get("executor_session_id") else "session_name",
            "session_note": execution.get("executor_session_note"),
            "session_source": "auto" if execution.get("executor_session_auto_captured") else "manual",
            "session_capture_source": execution.get("executor_session_capture_source"),
            "session_ref_label": execution.get("executor_session_ref_label"),
            "model": execution.get("actual_model") or execution.get("planned_model"),
            "attached_at": execution.get("executor_session_attached_at") or execution.get("updated_at"),
            "updated_at": execution.get("updated_at"),
        }
        haystack = " ".join(
            str(value or "")
            for value in (
                candidate["session_ref"],
                candidate["session_name"],
                candidate["task_id"],
                candidate["task_title"],
                candidate["model"],
                candidate["executor_id"],
            )
        ).lower()
        if query_text and query_text not in haystack:
            continue
        score = 0
        if resolved_executor_id and candidate_executor_id == resolved_executor_id:
            score += 3
        if task_id and execution.get("task_id") == task_id:
            score += 6
        if target_title and str(execution.get("task_title") or "").strip() == target_title:
            score += 4
        if target_model and str(execution.get("actual_model") or execution.get("planned_model") or "").strip() == target_model:
            score += 2
        candidate["match_score"] = score
        key = (
            candidate_executor_id,
            str(candidate.get("session_id") or ""),
            str(candidate.get("session_name") or ""),
        )
        current = sessions_by_key.get(key)
        if not current or _session_candidate_sort_key(candidate) > _session_candidate_sort_key(current):
            sessions_by_key[key] = candidate

    ordered = sorted(sessions_by_key.values(), key=_session_candidate_sort_key, reverse=True)
    return ordered[: max(1, int(limit or 5))]


def find_best_historical_session(
    root: Path,
    task_id: str,
    executor_id: str | None = None,
    query: str | None = None,
) -> dict | None:
    sessions = list_execution_sessions(
        root,
        task_id=task_id,
        executor_id=executor_id,
        query=query,
        limit=1,
    )
    return sessions[0] if sessions else None


def run_verification_command(root: Path, command: str) -> dict:
    completed = subprocess.run(
        command,
        cwd=root,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        shell=True,
        check=False,
    )
    stdout_excerpt = _truncate_output(completed.stdout or "")
    stderr_excerpt = _truncate_output(completed.stderr or "")
    parts = [f"exit code: {completed.returncode}"]
    if stdout_excerpt:
        parts.append(f"stdout: {stdout_excerpt}")
    if stderr_excerpt:
        parts.append(f"stderr: {stderr_excerpt}")
    return {
        "command": command,
        "exit_code": completed.returncode,
        "stdout_excerpt": stdout_excerpt,
        "stderr_excerpt": stderr_excerpt,
        "summary": " | ".join(parts),
    }


def _retry_model_candidates(task: dict, failed_model: str | None) -> list[str]:
    ordered: list[str] = []
    for model in [task.get("recommended_model"), *(task.get("fallback_models") or [])]:
        cleaned = str(model or "").strip()
        if cleaned and cleaned not in ordered:
            ordered.append(cleaned)
    if not ordered:
        return []
    failed = str(failed_model or "").strip()
    if failed and failed in ordered:
        return ordered[ordered.index(failed) + 1 :]
    return ordered[1:]


def prepare_execution_record(
    root: Path,
    task: dict,
    route: dict,
    handoff: dict,
    mode: str,
    status: str,
    note: str | None = None,
    executor: dict | None = None,
) -> dict:
    timestamp = now_iso()
    executions = load_executions(root)
    active = latest_active_execution_for_task(root, task["id"])
    git_state = git_snapshot(root)

    if active:
        for item in executions:
            if item.get("execution_id") != active.get("execution_id"):
                continue
            prompt_tokens = _prompt_token_estimate(root, handoff["pack_path"])
            cost = estimate_model_cost(root, handoff["model"], prompt_tokens, int(item.get("output_token_estimate") or 0))
            item["mode"] = mode
            item["status"] = status
            item["planned_model"] = handoff["model"]
            item["fallback_models"] = route["fallback_models"]
            item["pack_path"] = handoff["pack_path"]
            item["handoff_path"] = handoff["handoff_path"]
            item["prompt_token_estimate"] = prompt_tokens
            item["total_token_estimate"] = cost["total_tokens"]
            item["input_cost_per_1m"] = cost["input_cost_per_1m"]
            item["output_cost_per_1m"] = cost["output_cost_per_1m"]
            item["estimated_input_cost"] = cost["estimated_input_cost"]
            item["estimated_total_cost"] = cost["estimated_total_cost"]
            item["cost_currency"] = cost["cost_currency"]
            item["operator_note"] = note
            item.update(_clear_failure_fields())
            item["executor_id"] = executor.get("id") if executor else None
            item["executor_label"] = executor.get("label") if executor else None
            item["executor_resume_supported"] = executor_supports_session_resume(executor) if executor else False
            item["executor_continue_command"] = (
                resume_shell_preview(executor, root, latest=True) if executor and executor.get("continue_args") else None
            )
            item["git_is_repo_before"] = git_state["is_git_repo"]
            item["git_branch_before"] = git_state["branch"]
            item["git_commit_before"] = git_state["commit"]
            item["git_status_before"] = git_state["status_map"]
            item["git_is_clean_before"] = git_state["is_clean"]
            if status == "running":
                item["started_at"] = item.get("started_at") or timestamp
            item["updated_at"] = timestamp
            save_executions(root, executions)
            return item

    prompt_tokens = _prompt_token_estimate(root, handoff["pack_path"])
    cost = estimate_model_cost(root, handoff["model"], prompt_tokens, 0)
    execution = {
        "execution_id": next_execution_id(executions),
        "task_id": task["id"],
        "task_title": task["title"],
        "mode": mode,
        "status": status,
        "planned_model": handoff["model"],
        "actual_model": None,
        "fallback_models": route["fallback_models"],
        "pack_path": handoff["pack_path"],
        "handoff_path": handoff["handoff_path"],
        "started_at": timestamp if status == "running" else None,
        "finished_at": None,
        "operator_note": note,
        "test_command": None,
        "test_result": None,
        "completion_summary": None,
        "failure_source": None,
        "failure_category": None,
        "failure_summary": None,
        "failure_retryable": None,
        "failure_next_action": None,
        "failure_detected_at": None,
        "prompt_token_estimate": prompt_tokens,
        "output_token_estimate": 0,
        "total_token_estimate": cost["total_tokens"],
        "input_cost_per_1m": cost["input_cost_per_1m"],
        "output_cost_per_1m": cost["output_cost_per_1m"],
        "estimated_input_cost": cost["estimated_input_cost"],
        "estimated_output_cost": cost["estimated_output_cost"],
        "estimated_total_cost": cost["estimated_total_cost"],
        "cost_currency": cost["cost_currency"],
        "duration_seconds": None,
        "executor_id": executor.get("id") if executor else None,
        "executor_label": executor.get("label") if executor else None,
        "executor_command": None,
        "executor_exit_code": None,
        "executor_log_path": None,
        "executor_stdout_excerpt": None,
        "executor_stderr_excerpt": None,
        "executor_resume_supported": executor_supports_session_resume(executor) if executor else False,
        "executor_session_id": None,
        "executor_session_name": None,
        "executor_session_note": None,
        "executor_session_attached_at": None,
        "executor_session_auto_captured": False,
        "executor_session_capture_source": None,
        "executor_session_capture_pattern": None,
        "executor_session_ref_label": executor.get("session_ref_label") if executor else None,
        "executor_resume_command": None,
        "executor_continue_command": resume_shell_preview(executor, root, latest=True) if executor and executor.get("continue_args") else None,
        "executor_resume_last_command": None,
        "executor_resume_last_mode": None,
        "executor_resume_generated_at": None,
        "executor_resume_history_session_ref": None,
        "executor_resume_history_session_kind": None,
        "executor_resume_history_task_id": None,
        "executor_resume_history_task_title": None,
        "executor_resume_history_execution_id": None,
        "executor_terminal_launch_supported": False,
        "executor_terminal_launch_status": None,
        "executor_terminal_launch_app": None,
        "executor_terminal_launch_command": None,
        "executor_terminal_launch_mode": None,
        "executor_terminal_launch_at": None,
        "git_is_repo_before": git_state["is_git_repo"],
        "git_branch_before": git_state["branch"],
        "git_commit_before": git_state["commit"],
        "git_status_before": git_state["status_map"],
        "git_is_clean_before": git_state["is_clean"],
        "git_branch_after": None,
        "git_commit_after": None,
        "auto_commit_enabled": False,
        "auto_commit_status": None,
        "auto_commit_reason": None,
        "auto_commit_paths": None,
        "auto_commit_subject": None,
        "auto_push_enabled": False,
        "auto_push_status": None,
        "auto_push_reason": None,
        "auto_push_remote": None,
        "auto_push_branch": None,
        "auto_pr_enabled": False,
        "auto_pr_status": None,
        "auto_pr_reason": None,
        "auto_pr_url": None,
        "auto_pr_number": None,
        "auto_pr_base_branch": None,
        "updated_at": timestamp,
    }
    executions.append(execution)
    save_executions(root, executions)
    return execution


def update_execution(root: Path, execution_id: str, updates: dict) -> dict:
    executions = load_executions(root)
    for item in executions:
        if item.get("execution_id") != execution_id:
            continue
        item.update(updates)
        save_executions(root, executions)
        return item
    raise ValueError(f"Execution not found: {execution_id}")


def next_execution_id(executions: list[dict]) -> str:
    date_part = today().replace("-", "")
    pattern = re.compile(rf"^EXEC-{date_part}-(\d{{3}})$")
    max_number = 0
    for item in executions:
        match = pattern.match(item.get("execution_id", ""))
        if match:
            max_number = max(max_number, int(match.group(1)))
    return f"EXEC-{date_part}-{max_number + 1:03d}"


def _write_execution_log(log_path: Path, command_preview: str, stdout: str, stderr: str, exit_code: int | None) -> None:
    body = [
        f"Command: {command_preview}",
        f"Exit code: {exit_code if exit_code is not None else '-'}",
        "",
        "STDOUT:",
        stdout.rstrip(),
        "",
        "STDERR:",
        stderr.rstrip(),
        "",
    ]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("\n".join(body), encoding="utf-8")


def _truncate_output(text: str, limit: int = 800) -> str | None:
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _failure_fields(
    *,
    category: str,
    summary: str,
    retryable: bool,
    next_action: str,
    source: str,
) -> dict:
    return {
        "failure_source": source,
        "failure_category": category,
        "failure_summary": summary,
        "failure_retryable": retryable,
        "failure_next_action": next_action,
        "failure_detected_at": now_iso(),
    }


def _clear_failure_fields() -> dict:
    return {
        "failure_source": None,
        "failure_category": None,
        "failure_summary": None,
        "failure_retryable": None,
        "failure_next_action": None,
        "failure_detected_at": None,
    }


def _classify_failed_execution(stdout: str, stderr: str, exit_code: int | None) -> dict:
    combined = "\n".join(part for part in [stdout or "", stderr or ""] if part).lower()
    if any(marker in combined for marker in AUTH_FAILURE_MARKERS):
        return _failure_fields(
            category="provider_auth_failed",
            summary=f"Execution failed with exit code {exit_code}. Provider authentication appears invalid.",
            retryable=False,
            next_action="fix_provider_auth",
            source="executor",
        )
    if any(marker in combined for marker in NETWORK_FAILURE_MARKERS):
        return _failure_fields(
            category="provider_unreachable",
            summary=f"Execution failed with exit code {exit_code}. Provider network appears unreachable.",
            retryable=True,
            next_action="probe_provider",
            source="executor",
        )
    return _failure_fields(
        category="executor_nonzero_exit",
        summary=f"Execution failed with exit code {exit_code}.",
        retryable=True,
        next_action="inspect_executor_failure",
        source="executor",
    )


def _prompt_token_estimate(root: Path, relative_pack_path: str | None) -> int:
    if not relative_pack_path:
        return 0
    path = root / relative_pack_path
    if not path.exists():
        return 0
    return estimate_tokens(path.read_text(encoding="utf-8"))


def execution_duration_seconds(execution: dict | None) -> float | None:
    if not execution:
        return None
    if execution.get("duration_seconds") is not None:
        return float(execution["duration_seconds"])
    started_at = str(execution.get("started_at") or "").strip()
    finished_at = str(execution.get("finished_at") or "").strip()
    if not started_at or not finished_at:
        return None
    try:
        return round((datetime.fromisoformat(finished_at) - datetime.fromisoformat(started_at)).total_seconds(), 3)
    except ValueError:
        return None


def _auto_attach_executor_session(root: Path, execution_id: str, executor: dict, stdout: str, stderr: str) -> dict | None:
    if not executor_supports_session_resume(executor):
        return None
    captured = extract_executor_session_ref(executor, stdout, stderr)
    if not captured:
        return None
    session_ref = captured["session_ref"]
    attached_at = now_iso()
    updates = {
        "executor_session_id": captured["session_id"],
        "executor_session_name": captured["session_name"],
        "executor_session_attached_at": attached_at,
        "executor_session_auto_captured": True,
        "executor_session_capture_source": captured["source"],
        "executor_session_capture_pattern": captured["pattern"],
        "executor_session_ref_label": executor.get("session_ref_label") or "session",
        "executor_resume_supported": True,
        "executor_resume_command": resume_shell_preview(executor, root, session_ref=session_ref, latest=False),
        "executor_continue_command": resume_shell_preview(executor, root, latest=True) if executor.get("continue_args") else None,
        "executor_resume_history_session_ref": None,
        "executor_resume_history_session_kind": None,
        "executor_resume_history_task_id": None,
        "executor_resume_history_task_title": None,
        "executor_resume_history_execution_id": None,
        "updated_at": attached_at,
    }
    return update_execution(root, execution_id, updates)


def _execution_session_ref(execution: dict) -> str | None:
    return str(execution.get("executor_session_id") or execution.get("executor_session_name") or "").strip() or None


def _session_candidate_sort_key(candidate: dict) -> tuple[int, str, str]:
    return (
        int(candidate.get("match_score") or 0),
        str(candidate.get("attached_at") or candidate.get("updated_at") or ""),
        str(candidate.get("execution_id") or ""),
    )
