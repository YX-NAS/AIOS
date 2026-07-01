from __future__ import annotations

import argparse
from pathlib import Path

from aios.core.workflow import finalize_task


def add_complete_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("complete", help="Mark a task as complete and write project memory.")
    parser.add_argument("task_id")
    parser.add_argument("--summary", required=True, help="Completion summary.")


def run_complete(root: Path, args: argparse.Namespace) -> None:
    task = finalize_task(root, args.task_id, args.summary)
    print(f"Completed {task['id']}: {task['title']}")
