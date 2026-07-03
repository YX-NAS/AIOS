"""Cross-model review commands for AIOS CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from aios.core.review import (
    REVIEW_FOCUS_DEFINITIONS,
    REVIEW_RESULT_STATUSES,
    complete_review,
    create_review_task,
    get_review_for_task,
)


def add_review_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("review", help="Cross-model review workflow.")
    review_sub = parser.add_subparsers(dest="review_action", required=True)

    # review create
    create_parser = review_sub.add_parser("create", help="Create a review task for a completed task.")
    create_parser.add_argument("task_id", help="Task ID to review.")
    create_parser.add_argument("--focus", nargs="*", default=None,
                               choices=list(REVIEW_FOCUS_DEFINITIONS.keys()) + [[]],
                               help="Review focus areas.")
    create_parser.add_argument("--model", default=None, help="Reviewer model (default: auto-select).")

    # review complete
    complete_parser = review_sub.add_parser("complete", help="Complete a review task.")
    complete_parser.add_argument("review_task_id", help="Review task ID.")
    complete_parser.add_argument("--status", required=True,
                                 choices=REVIEW_RESULT_STATUSES,
                                 help="Review conclusion.")
    complete_parser.add_argument("--notes", default=None, help="Review notes.")
    complete_parser.add_argument("--issues", nargs="*", default=None,
                                 help="Issue descriptions (comma-separated severity:description).")

    # review show
    show_parser = review_sub.add_parser("show", help="Show review for a task.")
    show_parser.add_argument("task_id", help="Task ID to show review for.")

    # review list-focus
    review_sub.add_parser("list-focus", help="List available review focus areas.")


def run_review(root: Path, args: argparse.Namespace) -> None:
    if args.review_action == "create":
        result = create_review_task(
            root,
            args.task_id,
            focus_areas=args.focus,
            reviewer_model=args.model,
        )
        rt = result["review_task"]
        print(f"Review task created: {rt['id']}")
        print(f"  Title: {rt['title']}")
        print(f"  Reviewer model: {result['review_model']}")
        print(f"  Focus areas: {', '.join(rt.get('review_focus_areas', []))}")
        print(f"  Status: {rt['status']}")

    elif args.review_action == "complete":
        issues = None
        if args.issues:
            issues = []
            for item_str in args.issues:
                if ":" in item_str:
                    severity, desc = item_str.split(":", 1)
                    issues.append({"severity": severity.strip(), "description": desc.strip()})
                else:
                    issues.append({"severity": "info", "description": item_str.strip()})

        result = complete_review(
            root,
            args.review_task_id,
            args.status,
            issues=issues,
            notes=args.notes,
        )
        rr = result["review_record"]
        print(f"Review completed: {rr['status']}")
        if rr.get("result", {}).get("issues"):
            print(f"  Issues found: {len(rr['result']['issues'])}")
        st = result["source_task"]
        print(f"  Source task status: {st['status']} (review: {st.get('review_status')})")

    elif args.review_action == "show":
        review = get_review_for_task(root, args.task_id)
        if not review:
            print(f"No review found for task {args.task_id}.")
            return
        print(f"Review for {review.get('source_task_title')} ({review.get('source_task_id')})")
        print(f"  Status: {review.get('status')}")
        print(f"  Reviewer model: {review.get('reviewer_model')}")
        print(f"  Focus areas: {', '.join(review.get('focus_areas', []))}")
        if review.get("result"):
            result_info = review["result"]
            if result_info.get("issues"):
                print(f"  Issues ({len(result_info['issues'])}):")
                for issue in result_info["issues"]:
                    print(f"    [{issue.get('severity', 'info')}] {issue.get('description', '')}")
            if result_info.get("notes"):
                print(f"  Notes: {result_info['notes']}")

    elif args.review_action == "list-focus":
        print("Available review focus areas:")
        for key, defn in REVIEW_FOCUS_DEFINITIONS.items():
            print(f"  {key}: {defn['label']} — {defn['description']}")
