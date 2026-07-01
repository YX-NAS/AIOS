from __future__ import annotations

import argparse
from pathlib import Path

from aios.core.context_builder import build_context_pack
from aios.core.tasks import get_task


def add_pack_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("pack", help="Build a model-specific context pack.")
    parser.add_argument("task_id")
    parser.add_argument("--model", default=None, help="Target model. Defaults to the task recommendation.")


def run_pack(root: Path, args: argparse.Namespace) -> None:
    task = get_task(root, args.task_id)
    model = args.model or task["recommended_model"]
    target = build_context_pack(root, task, model)
    print(f"Created {target.relative_to(root)}")

