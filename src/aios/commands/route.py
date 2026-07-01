from __future__ import annotations

import argparse
from pathlib import Path

from aios.core.router import log_routing, route_task
from aios.core.tasks import get_task


def add_route_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("route", help="Recommend a model for a task.")
    parser.add_argument("task_id")


def run_route(root: Path, args: argparse.Namespace) -> None:
    route = route_task(get_task(root, args.task_id), root)
    log_routing(root, route)
    print(f"Task: {route['title']}")
    print(f"Type: {route['type']}")
    print(f"Complexity: {route['complexity']}")
    print(f"Recommended model: {route['recommended_model']}")
    print(f"Fallback models: {', '.join(route['fallback_models'])}")
    print("Reason:")
    for item in route["reason"]:
        print(f"- {item}")
