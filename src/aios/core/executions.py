from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from aios.core.executors import build_executor_command, get_executor, shell_preview
from aios.core.git_commit import auto_commit_task_changes, git_snapshot
from aios.core.git_push import auto_push_commit
from aios.core.handoff import build_handoff
from aios.core.paths import require_aios
from aios.core.router import route_task
from aios.core.scoring import save_score
from aios.core.tasks import get_task, set_task_status
from aios.core.workflow import finalize_task
from aios.utils.json_utils import read_json, write_json
from aios.utils.text import now_iso, today


ACTIVE_STATUSES = {"prepared", "running"}
OPEN_STATUSES = {"prepared", "running", "review_pending"}


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


def latest_open_execution_for_task(root: Path, task_id: str) -> dict | None:
    matches = [
        item
        for item in load_executions(root)
        if item.get("task_id") == task_id and item.get("status") in OPEN_STATUSES
    ]
    if not matches:
        return None
    return max(matches, key=lambda item: item.get("updated_at") or item.get("started_at") or "")


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
    return {
        "task": get_task(root, task_id),
        "route": route,
        "handoff": handoff,
        "execution": execution,
    }


def run_executor_execution(
    root: Path,
    task_id: str,
    executor_id: str,
    model: str | None = None,
    refresh_pack: bool = False,
    note: str | None = None,
) -> dict:
    executor = get_executor(None, executor_id)
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
    timestamp = now_iso()

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
                "finished_at": timestamp,
                "updated_at": timestamp,
                "executor_command": preview,
                "executor_exit_code": completed.returncode,
                "executor_log_path": str(log_path.relative_to(root)),
                "executor_stdout_excerpt": _truncate_output(completed.stdout),
                "executor_stderr_excerpt": _truncate_output(completed.stderr),
            },
        )
    except FileNotFoundError as exc:
        update_execution(
            root,
            execution["execution_id"],
            {
                "status": "failed",
                "finished_at": timestamp,
                "updated_at": timestamp,
                "executor_command": preview,
                "executor_exit_code": None,
                "executor_log_path": str(log_path.relative_to(root)),
                "executor_stderr_excerpt": str(exc),
            },
        )
        raise ValueError(f"Executor binary not found: {executor.get('binary')}") from exc
    except subprocess.TimeoutExpired as exc:
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
                "finished_at": timestamp,
                "updated_at": timestamp,
                "executor_command": preview,
                "executor_exit_code": None,
                "executor_log_path": str(log_path.relative_to(root)),
                "executor_stdout_excerpt": _truncate_output(exc.stdout or ""),
                "executor_stderr_excerpt": _truncate_output(exc.stderr or f"Execution timed out after {timeout_seconds} seconds."),
            },
        )
        raise ValueError(f"Executor timed out after {timeout_seconds} seconds.") from exc

    return {
        "task": get_task(root, task_id),
        "route": route,
        "handoff": handoff,
        "execution": latest_execution_for_task(root, task_id),
        "executor": executor,
    }


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

    return {
        "task": task,
        "execution": execution or latest_execution_for_task(root, task_id),
        "git_commit": commit_result,
        "git_push": push_result,
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
) -> dict:
    if not summary:
        raise ValueError("Use `--summary` when enabling auto finish.")
    execution = latest_execution_for_task(root, task_id)
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
    )
    return {
        "finished": True,
        "reason": None,
        **result,
        "verification": verification,
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
            item["mode"] = mode
            item["status"] = status
            item["planned_model"] = handoff["model"]
            item["fallback_models"] = route["fallback_models"]
            item["pack_path"] = handoff["pack_path"]
            item["handoff_path"] = handoff["handoff_path"]
            item["operator_note"] = note
            item["executor_id"] = executor.get("id") if executor else None
            item["executor_label"] = executor.get("label") if executor else None
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
        "executor_id": executor.get("id") if executor else None,
        "executor_label": executor.get("label") if executor else None,
        "executor_command": None,
        "executor_exit_code": None,
        "executor_log_path": None,
        "executor_stdout_excerpt": None,
        "executor_stderr_excerpt": None,
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
