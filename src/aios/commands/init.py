from __future__ import annotations

import argparse
from pathlib import Path

from aios.core.project import initialize_project


def add_init_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("init", help="Initialize .aios project metadata.")
    parser.add_argument("--name", default=None, help="Project name. Defaults to the folder name.")
    parser.add_argument("--type", default="software-project", help="Project type.")
    parser.add_argument("--force", action="store_true", help="Recreate missing/default files.")


def run_init(root: Path, args: argparse.Namespace) -> None:
    created = initialize_project(root, args.name or root.name, args.type, args.force)
    print("AIOS project initialized.")
    for path in created:
        print(f"Created {path.relative_to(root)}")

