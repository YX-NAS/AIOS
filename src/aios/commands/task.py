from __future__ import annotations

import argparse
from pathlib import Path

from aios.core.tasks import create_task, get_task, load_tasks, plan_goal


def add_task_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("task", help="Manage AIOS tasks.")
    task_subparsers = parser.add_subparsers(dest="task_command", required=True)

    create = task_subparsers.add_parser("create", help="Create a task.")
    create.add_argument("title")
    create.add_argument("--priority", default="medium", choices=["low", "medium", "high"])
    create.add_argument("--acceptance", action="append", default=[], help="Acceptance criterion. Repeatable.")

    task_subparsers.add_parser("list", help="List tasks.")

    show = task_subparsers.add_parser("show", help="Show one task.")
    show.add_argument("task_id")

    plan = task_subparsers.add_parser("plan", help="Split one goal into multiple executable tasks.")
    plan.add_argument("goal")
    plan.add_argument("--priority", default="high", choices=["low", "medium", "high"])
    plan.add_argument("--preview", action="store_true", help="Only preview the split result without saving tasks.")


def run_task(root: Path, args: argparse.Namespace) -> None:
    if args.task_command == "create":
        task = create_task(root, args.title, args.priority, args.acceptance or None)
        print(f"Created {task['id']}: {task['title']}")
        print(f"Type: {task['type']}")
        print(f"Recommended model: {task['recommended_model']}")
        return

    if args.task_command == "list":
        tasks = load_tasks(root)
        if not tasks:
            print("No tasks.")
            return
        for task in tasks:
            print(f"{task['id']} [{task['status']}] {task['title']} ({task['recommended_model']})")
        return

    if args.task_command == "show":
        task = get_task(root, args.task_id)
        print(f"Task: {task['id']}")
        print(f"Title: {task['title']}")
        print(f"Type: {task['type']}")
        print(f"Status: {task['status']}")
        print(f"Priority: {task['priority']}")
        print(f"Recommended model: {task['recommended_model']}")
        print("Acceptance:")
        for item in task["acceptance_criteria"]:
            print(f"- {item}")
        return

    if args.task_command == "plan":
        planned = plan_goal(root, args.goal, args.priority, create=not args.preview)
        action = "Previewed" if args.preview else "Created"
        print(f"{action} {len(planned)} tasks for goal: {args.goal}")
        for task in planned:
            print(f"{task['id']} {task['title']}")
            print(f"Type: {task['type']}")
            print(f"Recommended model: {task['recommended_model']}")
            print(f"Priority: {task['priority']}")
