from __future__ import annotations

import argparse
from pathlib import Path

from aios.core.executions import execution_summary
from aios.core.models import model_summary
from aios.core.paths import require_aios
from aios.core.tasks import load_tasks
from aios.utils.json_utils import read_json


def add_status_parser(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser("status", help="Show AIOS project status.")


def run_status(root: Path, args: argparse.Namespace) -> None:
    aios_dir = require_aios(root)
    tasks = load_tasks(root)
    file_index = read_json(aios_dir / "file-index.json", {})
    execution = execution_summary(root)
    models = model_summary()
    done = len([task for task in tasks if task["status"] == "done"])
    todo = len([task for task in tasks if task["status"] != "done"])
    print(f"AIOS: {aios_dir}")
    print(f"Tasks: {len(tasks)} total, {todo} open, {done} done")
    print(
        "Executions: "
        f"{execution['execution_count']} total, "
        f"{execution['active_execution_count']} active, "
        f"latest={execution['latest_execution_status'] or '-'}"
    )
    print(
        "Providers: "
        f"{models['provider_ready_count']} ready / "
        f"{models['enabled_model_count']} enabled models"
    )
    if file_index:
        print(f"Files indexed: {file_index.get('summary', {}).get('file_count', 0)}")
    else:
        print("Files indexed: 0 (run `aios scan`)")
