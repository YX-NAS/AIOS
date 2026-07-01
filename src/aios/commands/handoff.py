from __future__ import annotations

import argparse
from pathlib import Path

from aios.core.handoff import build_handoff


def add_handoff_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("handoff", help="Create a manual execution handoff for one task.")
    parser.add_argument("task_id")
    parser.add_argument("--model", default=None, help="Execution model. Defaults to the task recommendation.")
    parser.add_argument(
        "--refresh-pack",
        action="store_true",
        help="Rebuild the task context pack before generating the handoff.",
    )


def run_handoff(root: Path, args: argparse.Namespace) -> None:
    handoff = build_handoff(root, args.task_id, args.model, args.refresh_pack)
    print(f"Created {handoff['handoff_path']}")
    print(f"Model: {handoff['model']}")
    print(f"Context pack: {handoff['pack_path']}")
