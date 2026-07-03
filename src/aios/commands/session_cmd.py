"""Session management commands for AIOS CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from aios.core.session_persist import (
    create_execution_snapshot,
    restore_execution_from_snapshot,
    smart_resume,
)
from aios.core.executions import (
    attach_execution_session,
    build_execution_resume,
    find_best_historical_session,
    latest_execution_for_task,
    open_execution_resume_in_terminal,
    list_execution_sessions,
)


def add_session_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("session", help="Execution session management and smart resume.")
    session_sub = parser.add_subparsers(dest="session_action", required=True)

    # session snapshot
    snapshot_parser = session_sub.add_parser("snapshot", help="Create an execution state snapshot.")
    snapshot_parser.add_argument("task_id", help="Task ID to snapshot.")
    snapshot_parser.add_argument("--note", default=None, help="Snapshot description.")

    # session restore
    restore_parser = session_sub.add_parser("restore", help="Restore execution from snapshot.")
    restore_parser.add_argument("task_id", help="Task ID to restore.")
    restore_parser.add_argument("--execution-id", default=None, help="Specific execution to restore.")

    # session resume
    resume_parser = session_sub.add_parser("resume", help="Smart resume — pick the best strategy automatically.")
    resume_parser.add_argument("task_id", help="Task ID to resume.")
    resume_parser.add_argument("--open-terminal", action="store_true", help="Open resume command in terminal.")
    resume_parser.add_argument("--terminal-app", default="Terminal", help="Terminal app (macOS).")

    # session health
    health_parser = session_sub.add_parser("health", help="Check session health for a task.")
    health_parser.add_argument("task_id", help="Task ID to check.")

    # session candidates
    candidates_parser = session_sub.add_parser("candidates", help="List historical session candidates.")
    candidates_parser.add_argument("task_id", help="Task ID to search candidates for.")
    candidates_parser.add_argument("--executor", default=None, help="Filter by executor ID.")
    candidates_parser.add_argument("--limit", type=int, default=5, help="Maximum results.")


def run_session(root: Path, args: argparse.Namespace) -> None:
    if args.session_action == "snapshot":
        result = create_execution_snapshot(root, args.task_id, note=args.note)
        print(f"Snapshot created for {args.task_id}")
        print(f"  Execution: {result['execution_id']}")
        print(f"  Created at: {result['created_at']}")
        print(f"  Task status: {result['task_state'].get('status')}")
        if args.note:
            print(f"  Note: {args.note}")

    elif args.session_action == "restore":
        result = restore_execution_from_snapshot(
            root,
            args.task_id,
            execution_id=args.execution_id,
        )
        health = result.get("health_checks", {})
        print(f"Restore assessment for {args.task_id}")
        print(f"  Snapshot available: {result['snapshot_available']}")
        print(f"  Strategy: {result['strategy'].get('strategy')}")
        print(f"  Reason: {result['strategy'].get('reason')}")
        if not health.get("overall_ok", False):
            for blocker in health.get("blockers", []):
                print(f"  ✗ BLOCKER: {blocker}")
        for warning in health.get("warnings", []):
            print(f"  ⚠ {warning}")
        if result.get("resume_command"):
            print(f"  Resume command: {result['resume_command']}")

    elif args.session_action == "resume":
        result = smart_resume(
            root,
            args.task_id,
            open_terminal=args.open_terminal,
            terminal_app=args.terminal_app,
        )
        if result.get("resumed"):
            print(f"Resume initiated for {args.task_id}")
            print(f"  Strategy: {result.get('strategy', {}).get('strategy')}")
            if result.get("resume_command"):
                print(f"  Command: {result['resume_command']}")
            if result.get("terminal"):
                print(f"  Terminal: opened in {result['terminal'].get('app')}")
        else:
            print(f"Resume blocked: {result.get('reason')}")
            health = result.get("health_checks", {})
            for blocker in health.get("blockers", []):
                print(f"  ✗ {blocker}")

    elif args.session_action == "health":
        from aios.core.session_persist import _run_restore_health_checks
        execution = latest_execution_for_task(root, args.task_id)
        if not execution:
            print(f"No execution found for {args.task_id}.")
            return
        health = _run_restore_health_checks(root, execution)
        print(f"Session health for {args.task_id}: {'OK' if health['overall_ok'] else 'BLOCKED'}")
        for check in health.get("checks", []):
            icon = "✓" if check["status"] == "ok" else ("⚠" if check["status"] == "warning" else "✗")
            print(f"  {icon} {check['name']}: {check['message']}")

    elif args.session_action == "candidates":
        sessions = list_execution_sessions(
            root,
            task_id=args.task_id,
            executor_id=args.executor,
            limit=args.limit,
        )
        if not sessions:
            print(f"No session candidates found for {args.task_id}.")
            return
        print(f"Found {len(sessions)} session candidate(s):")
        for s in sessions:
            print(f"  [{s.get('match_score')}] {s.get('task_id')}: {s.get('session_ref')}")
            print(f"    Source: {s.get('session_source')}, Kind: {s.get('session_kind')}")
            print(f"    Task: {s.get('task_title')}, Model: {s.get('model')}")
