"""Session persistence and smart resume for AIOS.

Handles saving and restoring execution session state, enabling
automatic continuation after interruptions.

Features:
- Session snapshots capturing execution state
- Smart resume strategy selection (continue > resume session > history)
- Pre-resume health checks (git status, executor availability)
- Conflict detection for external file modifications
"""

from __future__ import annotations

import shutil
from pathlib import Path

from aios.core.executions import (
    build_execution_resume,
    execution_log_path,
    find_best_historical_session,
    latest_execution_for_task,
    latest_open_execution_for_task,
    update_execution,
)
from aios.core.executors import (
    executor_runtime_status,
    executor_supports_session_resume,
    get_executor,
    resume_shell_preview,
)
from aios.core.git_utils import git_snapshot
from aios.core.paths import require_aios
from aios.core.terminal_resume import launch_command_in_terminal
from aios.utils.json_utils import read_json, write_json
from aios.utils.text import now_iso

# Snapshot version for compatibility checks
SNAPSHOT_VERSION = "1.0"


def snapshot_path(root: Path, execution_id: str) -> Path:
    """Get the snapshot file path for an execution."""
    return require_aios(root) / "snapshots" / f"{execution_id}.json"


def create_execution_snapshot(
    root: Path,
    task_id: str,
    *,
    note: str | None = None,
) -> dict:
    """Create a snapshot of the current execution state for a task.

    Captures:
    - Execution record state
    - Task state
    - Git state
    - Executor information
    - Recent output log excerpt

    Args:
        root: Project root.
        task_id: Task ID to snapshot.
        note: Optional snapshot description.

    Returns:
        Snapshot dict with all captured state.
    """
    from aios.core.tasks import get_task

    execution = latest_execution_for_task(root, task_id)
    if not execution:
        raise ValueError(f"No execution found for task {task_id}")

    task = get_task(root, task_id)
    git_state = git_snapshot(root)

    execution_id = execution.get("execution_id")
    log_excerpt = None
    if execution_id:
        log_path = execution_log_path(root, execution_id)
        if log_path.exists():
            log_content = log_path.read_text(encoding="utf-8")
            log_excerpt = log_content[-2000:] if len(log_content) > 2000 else log_content

    snapshot = {
        "version": SNAPSHOT_VERSION,
        "execution_id": execution_id,
        "task_id": task_id,
        "created_at": now_iso(),
        "note": note,
        "execution_state": {
            "status": execution.get("status"),
            "mode": execution.get("mode"),
            "planned_model": execution.get("planned_model"),
            "actual_model": execution.get("actual_model"),
            "executor_id": execution.get("executor_id"),
            "executor_label": execution.get("executor_label"),
            "executor_session_id": execution.get("executor_session_id"),
            "executor_session_name": execution.get("executor_session_name"),
            "executor_command": execution.get("executor_command"),
            "executor_exit_code": execution.get("executor_exit_code"),
            "pack_path": execution.get("pack_path"),
            "handoff_path": execution.get("handoff_path"),
            "test_command": execution.get("test_command"),
            "test_result": execution.get("test_result"),
            "completion_summary": execution.get("completion_summary"),
            "failure_category": execution.get("failure_category"),
            "failure_summary": execution.get("failure_summary"),
            "started_at": execution.get("started_at"),
            "finished_at": execution.get("finished_at"),
        },
        "task_state": {
            "status": task.get("status"),
            "type": task.get("type"),
            "priority": task.get("priority"),
            "recommended_model": task.get("recommended_model"),
            "acceptance_criteria": task.get("acceptance_criteria"),
        },
        "git_state": {
            "branch": git_state.get("branch"),
            "commit": git_state.get("commit"),
            "is_clean": git_state.get("is_clean"),
            "status_summary": _summarize_git_status(git_state.get("status_map", {})),
        },
        "log_excerpt": log_excerpt,
    }

    path = snapshot_path(root, execution_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, snapshot)

    # Update execution to reference snapshot
    update_execution(
        root,
        execution_id,
        {
            "session_snapshot_path": str(path.relative_to(root)),
            "session_snapshot_created_at": snapshot["created_at"],
            "updated_at": now_iso(),
        },
    )

    return snapshot


def load_execution_snapshot(root: Path, execution_id: str) -> dict | None:
    """Load a previously created execution snapshot."""
    path = snapshot_path(root, execution_id)
    if not path.exists():
        return None
    snapshot = read_json(path)
    if snapshot and snapshot.get("version") == SNAPSHOT_VERSION:
        return snapshot
    return None


def restore_execution_from_snapshot(
    root: Path,
    task_id: str,
    *,
    execution_id: str | None = None,
) -> dict:
    """Restore execution state from a snapshot.

    Performs pre-restore health checks and returns the best resume strategy.

    Args:
        root: Project root.
        task_id: Task ID to restore.
        execution_id: Specific execution to restore (uses latest if not given).

    Returns:
        Restore result with health checks and resume command.
    """
    from aios.core.tasks import get_task, update_task_fields

    # Find target execution
    if execution_id:
        execution = latest_execution_for_task(root, task_id)
        # Find the specific one
        from aios.core.executions import get_execution
        target = get_execution(root, execution_id)
        if target:
            execution = target
    else:
        execution = latest_execution_for_task(root, task_id)

    if not execution:
        raise ValueError(f"No execution found for {task_id}")

    execution_id_found = execution.get("execution_id")
    snapshot = load_execution_snapshot(root, execution_id_found)

    # Run health checks
    health = _run_restore_health_checks(root, execution)

    # Determine smart resume strategy
    strategy = _determine_resume_strategy(root, execution, health)

    # Build resume command
    resume_command = _build_smart_resume_command(root, task_id, execution, strategy)

    # Restore task state if snapshot available
    if snapshot:
        task_state = snapshot.get("task_state") or {}
        if task_state.get("status"):
            update_task_fields(
                root,
                task_id,
                {
                    "status": task_state["status"],
                    "updated_at": now_iso(),
                },
            )

    return {
        "task_id": task_id,
        "execution_id": execution_id_found,
        "snapshot_available": snapshot is not None,
        "snapshot": snapshot,
        "health_checks": health,
        "strategy": strategy,
        "resume_command": resume_command,
        "execution": execution,
        "task": get_task(root, task_id),
    }


def smart_resume(
    root: Path,
    task_id: str,
    *,
    open_terminal: bool = False,
    terminal_app: str = "Terminal",
) -> dict:
    """Smart resume: pick the best resume strategy and execute.

    Strategy priority:
    1. Session snapshot restore (if available and fresh)
    2. Continue latest session (if executor supports --continue)
    3. Resume specific session (if session ID is attached)
    4. Historical session fallback

    Args:
        root: Project root.
        task_id: Task ID to resume.
        open_terminal: Open resume command in a terminal.
        terminal_app: Terminal app name (macOS only).

    Returns:
        Resume result with selected strategy and command.
    """
    restore_result = restore_execution_from_snapshot(root, task_id)
    health = restore_result.get("health_checks") or {}

    if not health.get("overall_ok", False):
        return {
            **restore_result,
            "resumed": False,
            "reason": health.get("blockers", ["Health check failed."])[0],
        }

    if open_terminal and restore_result.get("resume_command"):
        launch_result = launch_command_in_terminal(
            restore_result["resume_command"],
            app=terminal_app,
        )
        restore_result["terminal"] = launch_result

    return {
        **restore_result,
        "resumed": True,
    }


def _run_restore_health_checks(root: Path, execution: dict) -> dict:
    """Run pre-restore health checks.

    Checks: git state, executor availability, snapshot freshness.
    """
    checks: list[dict] = []
    warnings: list[str] = []
    blockers: list[str] = []

    # 1. Git state check
    git_state = git_snapshot(root)
    if git_state.get("is_git_repo") and not git_state.get("is_clean"):
        warnings.append("Working directory has uncommitted changes. Restore may conflict with current state.")
    checks.append({
        "name": "git_clean",
        "status": "warning" if warnings else "ok",
        "message": warnings[-1] if warnings else "Working directory is clean.",
    })

    # 2. Executor availability
    executor_id = execution.get("executor_id")
    executor = None
    if executor_id:
        try:
            executor = get_executor(None, executor_id)
        except ValueError:
            blockers.append(f"Executor '{executor_id}' is not configured.")

    if executor:
        runtime = executor_runtime_status(executor)
        if not runtime.get("available"):
            blockers.append(f"Executor '{executor_id}' is not currently available: {runtime.get('reason')}")

        if not executor_supports_session_resume(executor):
            warnings.append(f"Executor '{executor_id}' does not support session resume. Only fresh execution is available.")

    checks.append({
        "name": "executor_available",
        "status": "critical" if blockers else ("warning" if warnings else "ok"),
        "message": blockers[-1] if blockers else (warnings[-1] if warnings else "Executor is available."),
    })

    # 3. Snapshot freshness
    execution_id = execution.get("execution_id")
    if execution_id:
        snapshot = load_execution_snapshot(root, execution_id)
        if snapshot:
            created = snapshot.get("created_at") or ""
            checks.append({
                "name": "snapshot_fresh",
                "status": "ok",
                "message": f"Snapshot available from {created}.",
            })
        else:
            checks.append({
                "name": "snapshot_fresh",
                "status": "warning",
                "message": "No snapshot available. Will resume from execution record only.",
            })

    return {
        "checks": checks,
        "warnings": warnings,
        "blockers": blockers,
        "overall_ok": len(blockers) == 0,
    }


def _determine_resume_strategy(
    root: Path,
    execution: dict,
    health: dict,
) -> dict:
    """Determine the best resume strategy based on available information."""
    executor_id = execution.get("executor_id") or ""

    # Check 1: Has attached session => direct session resume
    session_id = execution.get("executor_session_id")
    session_name = execution.get("executor_session_name")
    if session_id or session_name:
        session_ref = session_id or session_name
        return {
            "strategy": "resume_session",
            "session_ref": session_ref,
            "session_kind": "session_id" if session_id else "session_name",
            "reason": "Attached session found, resuming specific session.",
        }

    # Check 2: Executor supports --continue
    try:
        executor = get_executor(None, executor_id) if executor_id else None
    except ValueError:
        executor = None

    if executor and executor.get("continue_args"):
        return {
            "strategy": "continue_latest",
            "session_ref": None,
            "reason": "Executor supports continue-latest, resuming most recent session.",
        }

    # Check 3: Historical session fallback
    task_id = execution.get("task_id")
    if task_id:
        historical = find_best_historical_session(root, task_id, executor_id=executor_id)
        if historical:
            return {
                "strategy": "history_fallback",
                "session_ref": historical.get("session_ref"),
                "session_kind": historical.get("session_kind"),
                "reason": f"No attached session, using best historical candidate: {historical.get('session_ref')}",
            }

    return {
        "strategy": "fresh_execution",
        "session_ref": None,
        "reason": "No session to resume. A fresh execution will be started.",
    }


def _build_smart_resume_command(
    root: Path,
    task_id: str,
    execution: dict,
    strategy: dict,
) -> str | None:
    """Build the appropriate resume command based on strategy."""
    executor_id = execution.get("executor_id") or ""
    if not executor_id:
        return None

    try:
        executor = get_executor(None, executor_id)
    except ValueError:
        return None

    strategy_name = strategy.get("strategy")

    if strategy_name == "resume_session":
        session_ref = strategy.get("session_ref")
        if session_ref and executor.get("resume_args"):
            return resume_shell_preview(executor, root, session_ref=session_ref, latest=False)

    if strategy_name == "continue_latest":
        if executor.get("continue_args"):
            return resume_shell_preview(executor, root, latest=True)

    if strategy_name == "history_fallback":
        session_ref = strategy.get("session_ref")
        if session_ref and executor.get("resume_args"):
            return resume_shell_preview(executor, root, session_ref=session_ref, latest=False)

    return None


def _summarize_git_status(status_map: dict) -> str:
    """Create a human-readable summary of git status."""
    if not status_map:
        return "clean"
    parts: list[str] = []
    code_map = status_map or {}
    for code, count in sorted(code_map.items()):
        label = _git_status_label(code)
        if label:
            parts.append(f"{count} {label}")
    return ", ".join(parts) if parts else "clean"


def _git_status_label(code: str) -> str:
    """Map git status codes to labels."""
    labels = {
        "M": "modified",
        "A": "added",
        "D": "deleted",
        "R": "renamed",
        "C": "copied",
        "U": "unmerged",
        "?": "untracked",
        "!": "ignored",
        " ": "unmodified",
    }
    return labels.get(code.strip(), code)
