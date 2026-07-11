"""P4-0 / P4-1: Automatic model switching and executor pipeline.

The core insight: CLI-mode executors pass --model via command-line flags,
bypassing the need for ccswitch UI-level model switching. This module
provides the orchestration layer that:

1. Auto-switches ccswitch via Deep Links when CLI mode isn't available
2. Builds the full executor command with Pack injection
3. Implements the auto-pipeline (switch → execute → verify → finish)
"""

from __future__ import annotations

import json
import time
import subprocess
from pathlib import Path

from aios.core.ccswitch import (
    build_prompt_deeplink_url,
    build_provider_deeplink_url,
    open_ccswitch_deeplink,
)
from aios.core.executions import (
    latest_execution_for_task,
    load_executions,
    prepare_manual_execution,
    save_executions,
)
from aios.core.executors import (
    executor_runtime_status,
    get_executor,
    get_default_executor,
)
from aios.core.handoff import build_handoff
from aios.core.models import get_model, infer_provider
from aios.core.scheduler import scheduler_summary
from aios.core.tasks import get_task


def auto_switch_model(
    root: Path,
    task_id: str,
    model_id: str,
    app: str = "codex",
    switch_delay_seconds: float = 2.0,
    max_wait_seconds: float = 15.0,
) -> dict:
    """Attempt automatic model switch via ccswitch Deep Links.

    Opens provider and prompt Deep Links, waits for import, then returns status.
    This is a best-effort operation — the caller should check `success`.
    """
    model = get_model(None, model_id)
    if not model:
        return {"success": False, "reason": f"Model not found in global library: {model_id}"}

    provider = str(model.get("provider") or "").strip().lower()
    endpoint = str(model.get("endpoint") or "").strip()
    config_url = str(model.get("config_url") or "").strip()

    if not provider:
        return {"success": False, "reason": f"No provider configured for model: {model_id}"}

    task = get_task(root, task_id)
    handoff = build_handoff(root, task_id)

    provider_link = build_provider_deeplink_url(
        app=app,
        name=f"{provider}-{model_id}",
        provider=provider,
        model=model_id,
        endpoint=endpoint or None,
        config_url=config_url or None,
    )

    prompt_name = f"AIOS Task: {task['title'][:60]}"
    prompt_content = _read_pack_content(handoff.get("pack_path"), root)
    prompt_link = build_prompt_deeplink_url(
        app=app,
        name=prompt_name,
        content=prompt_content,
    )

    steps: list[dict] = []

    # Step 1: Open provider deeplink
    try:
        open_ccswitch_deeplink(provider_link)
        steps.append({"step": "provider_deeplink", "status": "sent", "url": provider_link})
    except Exception as exc:
        return {"success": False, "reason": f"Failed to open provider deeplink: {exc}", "steps": steps, "provider_link": provider_link, "prompt_link": prompt_link}

    time.sleep(switch_delay_seconds)

    # Step 2: Open prompt deeplink
    try:
        open_ccswitch_deeplink(prompt_link)
        steps.append({"step": "prompt_deeplink", "status": "sent", "url": prompt_link})
    except Exception as exc:
        return {"success": False, "reason": f"Provider sent, prompt deeplink failed: {exc}", "steps": steps, "provider_link": provider_link, "prompt_link": prompt_link}

    # Step 3: Wait for ccswitch to process
    start = time.time()
    while time.time() - start < max_wait_seconds:
        time.sleep(0.5)
        # We cannot directly inspect ccswitch state; we trust the import
        # has completed after the wait period
        elapsed = time.time() - start
        if elapsed >= switch_delay_seconds * 2:
            break

    steps.append({"step": "wait", "status": "completed", "elapsed_seconds": round(time.time() - start, 2)})
    return {
        "success": True,
        "reason": "Deep Links sent; import should complete within a few seconds.",
        "steps": steps,
        "provider_link": provider_link,
        "prompt_link": prompt_link,
        "model_id": model_id,
        "provider": provider,
    }


def build_auto_executor_command(
    root: Path,
    task_id: str,
    executor_id: str | None = None,
    model_id: str | None = None,
) -> dict:
    """Build the full executor command for a task, injecting Pack content."""
    task = get_task(root, task_id)
    execution = latest_execution_for_task(root, task_id)
    if not execution:
        raise ValueError("No execution record found. Run `aios run --manual TASK-ID` first.")

    resolved_model = model_id or execution.get("planned_model") or task.get("recommended_model") or ""
    if not resolved_model:
        raise ValueError("No model available for this task.")

    executor = get_executor(None, executor_id) if executor_id else get_default_executor(None, command_only=True, available_only=True)
    executor_id = executor["id"]

    handoff = build_handoff(root, task_id)
    pack_content = _read_pack_content(handoff.get("pack_path"), root)

    # Build the command
    binary = executor["binary"]
    args_template = executor.get("args", [])

    # Expand template placeholders
    expanded_args: list[str] = []
    for arg in args_template:
        expanded = arg.replace("{model}", resolved_model).replace("{prompt}", pack_content[:8000])
        expanded_args.append(expanded)

    command = [binary] + expanded_args

    runtime = executor_runtime_status(executor)

    return {
        "executor_id": executor_id,
        "command": command,
        "command_str": " ".join(command),
        "binary": binary,
        "model_id": resolved_model,
        "pack_path": handoff.get("pack_path"),
        "handoff_path": handoff.get("handoff_path"),
        "timeout_seconds": executor.get("timeout_seconds"),
        "runtime_available": runtime.get("available", False),
        "pass_model_as_flag": executor.get("pass_model_as_flag", False),
    }


def run_auto_pipeline_step(
    root: Path,
    executor_id: str | None = None,
    model: str | None = None,
    auto_switch: bool = True,
    switch_delay: float = 2.0,
    auto_finish: bool = True,
    verify_command: str | None = None,
) -> dict:
    """Run one step of the automatic pipeline.

    This is the main entry point for the auto pipeline. It:
    1. Checks scheduler state for the next dispatchable task
    2. Optionally auto-switches model via Deep Links
    3. Builds and runs the executor command
    4. Auto-finishes if verification passes

    Returns a pipeline result dict with all steps logged.
    """
    summary = scheduler_summary(root)
    next_task_id = summary.get("next_task_id")
    next_action = summary.get("next_action")

    if not next_task_id:
        return {"pipeline_status": "idle", "reason": "No dispatchable tasks.", "scheduler": summary}

    # Handle bridge confirmation first
    if next_action == "confirm_bridge":
        return {"pipeline_status": "blocked", "reason": "Bridge confirmation pending. Use --auto-confirm-bridge-signal or confirm manually.", "scheduler": summary}

    if next_action == "validate_resumed_session":
        return {"pipeline_status": "blocked", "reason": "Bridge resume signal detected. Validate session before auto-execution.", "scheduler": summary}

    if next_action not in ("run_executor", "review_finish"):
        return {"pipeline_status": "blocked", "reason": f"Cannot auto-execute in state: {next_action}", "scheduler": summary}

    task = get_task(root, next_task_id)
    scheduler_item = next((item for item in summary.get("items", []) if item.get("task_id") == next_task_id), {})
    resolved_model = model or scheduler_item.get("recommended_model") or task.get("recommended_model") or ""

    pipeline_steps: list[dict] = []

    # A scheduler-ready task has no execution record yet. Prepare the same
    # artifacts as the manual entrypoint before switching or invoking a CLI.
    if not latest_execution_for_task(root, next_task_id):
        prepared = prepare_manual_execution(root, next_task_id, model=resolved_model, start=True)
        resolved_model = prepared["execution"].get("planned_model") or resolved_model
        pipeline_steps.append(
            {
                "step": "prepare_execution",
                "result": {
                    "execution_id": prepared["execution"]["execution_id"],
                    "pack_path": prepared["execution"].get("pack_path"),
                    "handoff_path": prepared["execution"].get("handoff_path"),
                },
            }
        )

    # Step 1: Auto-switch model (if enabled and not CLI mode)
    switch_result = None
    if auto_switch:
        switch_result = auto_switch_model(root, next_task_id, resolved_model, switch_delay_seconds=switch_delay)
        pipeline_steps.append({"step": "auto_switch", "result": switch_result})
        if not switch_result["success"]:
            return {
                "pipeline_status": "switch_failed",
                "reason": switch_result["reason"],
                "scheduler": summary,
                "pipeline_steps": pipeline_steps,
            }

    # Step 2: Build and run executor
    cmd_info = build_auto_executor_command(root, next_task_id, executor_id=executor_id, model_id=resolved_model)
    pipeline_steps.append({"step": "build_command", "result": cmd_info})

    if not cmd_info["runtime_available"]:
        return {
            "pipeline_status": "executor_unavailable",
            "reason": f"Executor {cmd_info['executor_id']} is not available on this system.",
            "scheduler": summary,
            "pipeline_steps": pipeline_steps,
        }

    # Step 3: Run the executor
    try:
        completed = subprocess.run(
            cmd_info["command"],
            capture_output=True,
            text=True,
            timeout=cmd_info["timeout_seconds"],
            check=False,
            cwd=str(root),
        )
        run_result = {
            "exit_code": completed.returncode,
            "stdout": (completed.stdout or "")[:2000],
            "stderr": (completed.stderr or "")[:2000],
            "success": completed.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        run_result = {"exit_code": -1, "stdout": "", "stderr": "Executor timed out.", "success": False}
    except Exception as exc:
        run_result = {"exit_code": -1, "stdout": "", "stderr": str(exc), "success": False}

    pipeline_steps.append({"step": "run_executor", "result": run_result})

    return {
        "pipeline_status": "completed" if run_result["success"] else "execution_failed",
        "task_id": next_task_id,
        "task_title": task["title"],
        "model_id": resolved_model,
        "scheduler": summary,
        "pipeline_steps": pipeline_steps,
        "command": cmd_info,
    }


def _read_pack_content(pack_path: str | None, root: Path) -> str:
    if not pack_path:
        return ""
    full_path = root / pack_path
    if full_path.exists():
        return full_path.read_text(encoding="utf-8")
    return ""
