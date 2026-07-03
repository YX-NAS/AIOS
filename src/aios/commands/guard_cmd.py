"""Execution guard commands for AIOS CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from aios.core.guard import (
    check_heartbeat,
    guard_summary,
    load_guard_config,
    send_heartbeat,
    start_heartbeat,
    stop_heartbeat,
)
from aios.core.executions import latest_execution_for_task


def add_guard_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("guard", help="Execution guard — safety monitoring for automated runs.")
    guard_sub = parser.add_subparsers(dest="guard_action", required=True)

    # guard status
    status_parser = guard_sub.add_parser("status", help="Show guard status for an execution.")
    status_parser.add_argument("task_id", help="Task ID or execution ID to check.")

    # guard heartbeat
    heartbeat_parser = guard_sub.add_parser("heartbeat", help="Send or check execution heartbeats.")
    hb_sub = heartbeat_parser.add_subparsers(dest="heartbeat_action", required=True)
    hb_start = hb_sub.add_parser("start", help="Start heartbeat for an execution.")
    hb_start.add_argument("execution_id", help="Execution ID.")
    hb_send = hb_sub.add_parser("send", help="Send a heartbeat pulse.")
    hb_send.add_argument("execution_id", help="Execution ID.")
    hb_stop = hb_sub.add_parser("stop", help="Stop heartbeat for an execution.")
    hb_stop.add_argument("execution_id", help="Execution ID.")
    hb_stop.add_argument("--status", default="completed", choices=["completed", "failed", "cancelled"])
    hb_check = hb_sub.add_parser("check", help="Check heartbeat liveness.")
    hb_check.add_argument("execution_id", help="Execution ID.")

    # guard config
    guard_sub.add_parser("config", help="Show current guard configuration.")


def run_guard(root: Path, args: argparse.Namespace) -> None:
    if args.guard_action == "status":
        execution = latest_execution_for_task(root, args.task_id)
        if not execution:
            print(f"No execution found for '{args.task_id}'.")
            return
        exec_id = execution.get("execution_id")
        summary = guard_summary(root, exec_id)
        print(f"Guard status for {exec_id}: {summary['status']}")
        if summary.get("issues"):
            for issue in summary["issues"]:
                print(f"  ⚠ {issue}")

        hb = summary.get("heartbeat", {})
        print(f"  Heartbeat: {hb.get('status')} (age: {hb.get('last_beat_age_seconds', 'N/A')}s)")

        stuck = summary.get("stuck_detection", {})
        if stuck.get("stuck"):
            print(f"  Stuck: YES — {stuck.get('stuck_reason')}")
        if stuck.get("doom_loop"):
            print(f"  Doom loop: YES — pattern: {stuck.get('doom_loop_pattern')}")

    elif args.guard_action == "heartbeat":
        if args.heartbeat_action == "start":
            path = start_heartbeat(root, args.execution_id)
            print(f"Heartbeat started for {args.execution_id}.")
        elif args.heartbeat_action == "send":
            send_heartbeat(root, args.execution_id)
            hb = check_heartbeat(root, args.execution_id)
            print(f"Heartbeat sent. Beat count updated, alive={hb['alive']}.")
        elif args.heartbeat_action == "stop":
            stop_heartbeat(root, args.execution_id, status=args.status)
            print(f"Heartbeat stopped with status: {args.status}.")
        elif args.heartbeat_action == "check":
            hb = check_heartbeat(root, args.execution_id)
            if hb["alive"]:
                print(f"Execution {args.execution_id} is alive (last beat: {hb['last_beat_age_seconds']}s ago).")
            else:
                print(f"Execution {args.execution_id} is NOT alive: {hb.get('reason')}")

    elif args.guard_action == "config":
        config = load_guard_config(root)
        print("Execution Guard Configuration:")
        print(f"  Enabled: {config.enabled}")
        print(f"  Stuck timeout: {config.stuck_timeout_seconds}s")
        print(f"  Doom loop threshold: {config.doom_loop_threshold} repeats")
        print(f"  Heartbeat interval: {config.heartbeat_interval_seconds}s")
        print(f"  Heartbeat timeout: {config.heartbeat_timeout_seconds}s")
