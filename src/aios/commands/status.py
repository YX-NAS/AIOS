from __future__ import annotations

import argparse
from pathlib import Path

from aios.core.paths import require_aios
from aios.core.tasks import load_tasks
from aios.utils.json_utils import read_json


def add_status_parser(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser("status", help="Show AIOS project status.")


def run_status(root: Path, args: argparse.Namespace) -> None:
    aios_dir = require_aios(root)
    tasks = load_tasks(root)
    file_index = read_json(aios_dir / "file-index.json", {})
    done = len([task for task in tasks if task["status"] == "done"])
    todo = len([task for task in tasks if task["status"] != "done"])
    print(f"AIOS: {aios_dir}")
    print(f"Tasks: {len(tasks)} total, {todo} open, {done} done")
    if file_index:
        print(f"Files indexed: {file_index.get('summary', {}).get('file_count', 0)}")
    else:
        print("Files indexed: 0 (run `aios scan`)")

