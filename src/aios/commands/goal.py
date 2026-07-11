from __future__ import annotations

import argparse

from aios.core.goals import activate_goal, get_goal, list_goals
from aios.core.progress import advance_goal_progress, create_goal_with_plan


def add_goal_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("goal", help="Manage one project's active delivery goal.")
    goal_subparsers = parser.add_subparsers(dest="goal_command", required=True)

    create = goal_subparsers.add_parser("create", help="Create a goal and split it into an executable task tree.")
    create.add_argument("title")
    create.add_argument("--priority", default="high", choices=["low", "medium", "high"])

    goal_subparsers.add_parser("list", help="List project goals.")

    show = goal_subparsers.add_parser("show", help="Show goal progress and current task.")
    show.add_argument("goal_id")

    activate = goal_subparsers.add_parser("activate", help="Activate an unfinished goal when no other goal is active.")
    activate.add_argument("goal_id")

    advance = goal_subparsers.add_parser("advance", help="Recalculate the current task and goal status.")
    advance.add_argument("goal_id", nargs="?")


def run_goal(root, args: argparse.Namespace) -> None:
    if args.goal_command == "create":
        result = create_goal_with_plan(root, args.title, priority=args.priority)
        goal = result["goal"]
        print(f"Created {goal['goal_id']}: {goal['title']}")
        print(f"Tasks: {len(result['tasks'])}")
        _print_progress(result["progress"])
        return
    if args.goal_command == "list":
        goals = list_goals(root)
        if not goals:
            print("No goals.")
            return
        for goal in goals:
            print(f"{goal['goal_id']} [{goal['status']}] {goal['title']}")
        return
    if args.goal_command == "show":
        get_goal(root, args.goal_id)
        _print_progress(advance_goal_progress(root, args.goal_id))
        return
    if args.goal_command == "activate":
        goal = activate_goal(root, args.goal_id)
        print(f"Activated {goal['goal_id']}: {goal['title']}")
        _print_progress(advance_goal_progress(root, args.goal_id))
        return
    if args.goal_command == "advance":
        _print_progress(advance_goal_progress(root, args.goal_id))


def _print_progress(progress: dict) -> None:
    goal = progress.get("goal")
    if not goal:
        print("No active goal.")
        return
    current_task = progress.get("current_task") or {}
    print(f"Status: {goal.get('status')}")
    print(f"Progress: {progress.get('done_count', 0)}/{progress.get('task_count', 0)} ({progress.get('progress_percent', 0)}%)")
    print(f"Current task: {current_task.get('id') or '-'} {current_task.get('title') or '-'}")
    print(f"Next action: {progress.get('next_action') or '-'}")
