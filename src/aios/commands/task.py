from __future__ import annotations

import argparse
import json
from pathlib import Path

from aios.core.tasks import (
    confirm_plan_draft,
    create_plan_draft,
    create_task,
    delete_plan_draft,
    get_plan_draft,
    get_task,
    list_plan_drafts,
    load_tasks,
    plan_goal,
)


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
    plan.add_argument("--draft", action="store_true", help="Persist one plan draft for later confirmation.")

    draft = task_subparsers.add_parser("draft", help="Manage plan drafts.")
    draft_subparsers = draft.add_subparsers(dest="draft_command", required=True)
    draft_subparsers.add_parser("list", help="List plan drafts.")
    draft_show = draft_subparsers.add_parser("show", help="Show one plan draft.")
    draft_show.add_argument("draft_id")
    draft_confirm = draft_subparsers.add_parser("confirm", help="Confirm one plan draft into tasks.")
    draft_confirm.add_argument("draft_id")
    draft_delete = draft_subparsers.add_parser("delete", help="Delete one plan draft.")
    draft_delete.add_argument("draft_id")


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
        print(f"Parent task: {task.get('parent_task_id') or '-'}")
        print(f"Depends on: {', '.join(task.get('depends_on_task_ids') or []) or '-'}")
        print("Acceptance:")
        for item in task["acceptance_criteria"]:
            print(f"- {item}")
        return

    if args.task_command == "plan":
        if args.preview and args.draft:
            raise ValueError("Use either `--preview` or `--draft`, not both.")
        if args.draft:
            draft = create_plan_draft(root, args.goal, args.priority)
            print(f"Created draft {draft['draft_id']} for goal: {args.goal}")
            for task in draft["tasks"]:
                print(f"{task['id']} {task['title']}")
                print(f"Type: {task['type']}")
                print(f"Recommended model: {task['recommended_model']}")
                print(f"Depends on: {', '.join(task.get('depends_on_task_ids') or []) or '-'}")
            return
        planned = plan_goal(root, args.goal, args.priority, create=not args.preview)
        action = "Previewed" if args.preview else "Created"
        print(f"{action} {len(planned)} tasks for goal: {args.goal}")
        for task in planned:
            print(f"{task['id']} {task['title']}")
            print(f"Type: {task['type']}")
            print(f"Recommended model: {task['recommended_model']}")
            print(f"Priority: {task['priority']}")
            print(f"Parent task: {task.get('parent_task_id') or '-'}")
            print(f"Depends on: {', '.join(task.get('depends_on_task_ids') or []) or '-'}")
        return

    if args.task_command == "draft":
        if args.draft_command == "list":
            drafts = list_plan_drafts(root)
            if not drafts:
                print("No plan drafts.")
                return
            for draft in drafts:
                print(f"{draft['draft_id']} [{draft['status']}] {draft['goal']}")
            return
        if args.draft_command == "show":
            draft = get_plan_draft(root, args.draft_id)
            print(json.dumps(draft, ensure_ascii=False, indent=2))
            return
        if args.draft_command == "confirm":
            tasks = confirm_plan_draft(root, args.draft_id)
            print(f"Confirmed {args.draft_id} into {len(tasks)} tasks.")
            for task in tasks:
                print(f"{task['id']} {task['title']}")
            return
        if args.draft_command == "delete":
            delete_plan_draft(root, args.draft_id)
            print(f"Deleted draft {args.draft_id}.")
