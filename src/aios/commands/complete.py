from __future__ import annotations

import argparse
from pathlib import Path

from aios.core.executions import finish_manual_execution


def add_complete_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("complete", help="Mark a task as complete and write project memory.")
    parser.add_argument("task_id")
    parser.add_argument("--summary", required=True, help="Completion summary.")
    parser.add_argument("--score", type=int, default=None, choices=[1, 2, 3, 4, 5], help="Model effectiveness score (1-5).")
    parser.add_argument("--score-note", default=None, help="Optional note about the score.")


def run_complete(root: Path, args: argparse.Namespace) -> None:
    result = finish_manual_execution(root, args.task_id, args.summary, score=args.score, score_note=args.score_note)
    task = result["task"]
    if args.score is not None:
        print(f"Completed {task['id']}: {task['title']} (model score: {args.score}/5)")
    else:
        print(f"Completed {task['id']}: {task['title']}")
