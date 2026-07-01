from __future__ import annotations

import argparse
from pathlib import Path

from aios.core.executions import finish_manual_execution, latest_execution_for_task, prepare_manual_execution


def add_run_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("run", help="Manage semi-automatic task execution.")
    parser.add_argument("run_target", nargs="?", help="Task ID for manual mode, or `status` / `finish`.")
    parser.add_argument("task_id", nargs="?", help="Task ID for status / finish mode.")
    parser.add_argument("--manual", action="store_true", help="Prepare one manual execution.")
    parser.add_argument("--model", default=None, help="Execution model. Defaults to the task recommendation.")
    parser.add_argument("--refresh-pack", action="store_true", help="Rebuild the task context pack before preparing.")
    parser.add_argument("--start", action="store_true", help="Mark the execution as started immediately.")
    parser.add_argument("--note", default=None, help="Optional operator note.")
    parser.add_argument("--summary", default=None, help="Completion summary for finish mode.")
    parser.add_argument("--actual-model", default=None, help="Actual execution model used by the operator.")
    parser.add_argument("--test-command", default=None, help="Test command used for verification.")
    parser.add_argument("--test-result", default=None, help="Test result summary.")
    parser.add_argument("--score", type=int, default=None, choices=[1, 2, 3, 4, 5], help="Model effectiveness score (1-5).")
    parser.add_argument("--score-note", default=None, help="Optional note about the score.")


def run_run(root: Path, args: argparse.Namespace) -> None:
    if args.run_target == "status":
        if not args.task_id:
            raise ValueError("Task ID is required for `aios run status`.")
        execution = latest_execution_for_task(root, args.task_id)
        if not execution:
            print(f"No execution record for {args.task_id}.")
            return
        _print_execution(execution)
        return

    if args.run_target == "finish":
        if not args.task_id:
            raise ValueError("Task ID is required for `aios run finish`.")
        if not args.summary:
            raise ValueError("Use `--summary` to finish one task execution.")
        result = finish_manual_execution(
            root,
            args.task_id,
            args.summary,
            actual_model=args.actual_model,
            test_command=args.test_command,
            test_result=args.test_result,
            score=args.score,
            score_note=args.score_note,
        )
        print(f"Finished {result['task']['id']}: {result['task']['title']}")
        if result["execution"]:
            print(f"Execution: {result['execution']['execution_id']} [{result['execution']['status']}]")
        return

    task_id = args.run_target
    if not args.manual or not task_id:
        raise ValueError("Use `aios run --manual TASK-ID` or `aios run status|finish ...`.")

    result = prepare_manual_execution(
        root,
        task_id,
        model=args.model,
        refresh_pack=args.refresh_pack,
        start=args.start,
        note=args.note,
    )
    execution = result["execution"]
    route = result["route"]
    handoff = result["handoff"]
    print(f"Task: {result['task']['id']}")
    print(f"Execution: {execution['execution_id']}")
    print(f"Status: {execution['status']}")
    print(f"Planned model: {execution['planned_model']}")
    print(f"Fallback models: {', '.join(route['fallback_models']) or '-'}")
    print(f"Context pack: {handoff['pack_path']}")
    print(f"Handoff: {handoff['handoff_path']}")
    print("Next: switch ccswitch manually, run the task in Codex or Claude Code, then use `aios run finish`.")


def _print_execution(execution: dict) -> None:
    print(f"Execution: {execution['execution_id']}")
    print(f"Task: {execution['task_id']} {execution['task_title']}")
    print(f"Mode: {execution['mode']}")
    print(f"Status: {execution['status']}")
    print(f"Planned model: {execution['planned_model']}")
    print(f"Actual model: {execution.get('actual_model') or '-'}")
    print(f"Context pack: {execution['pack_path']}")
    print(f"Handoff: {execution['handoff_path']}")
    print(f"Started at: {execution.get('started_at') or '-'}")
    print(f"Finished at: {execution.get('finished_at') or '-'}")
    print(f"Test command: {execution.get('test_command') or '-'}")
    print(f"Test result: {execution.get('test_result') or '-'}")
