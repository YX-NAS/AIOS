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
    result = build_context_pack(root, task, model)
    pack_path = result["path"]
    print(f"Created {pack_path.relative_to(root)}")
    print(f"Token estimate: {result['token_estimate']} ({result['window_usage_pct']}% of {result['context_window']})")
    print(f"Quality: {result['quality']}")
    if result.get("relevant_files"):
        print(f"Relevant files: {len(result['relevant_files'])}")
    if result["warning"]:
        print(f"WARNING: {result['warning']}", file=__import__('sys').stderr)
