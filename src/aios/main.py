from __future__ import annotations

import argparse
from pathlib import Path

from aios.commands.ccswitch import add_ccswitch_parser, run_ccswitch
from aios.commands.complete import add_complete_parser, run_complete
from aios.commands.executor import add_executor_parser, run_executor
from aios.commands.guard_cmd import add_guard_parser, run_guard
from aios.commands.goal import add_goal_parser, run_goal
from aios.commands.handoff import add_handoff_parser, run_handoff
from aios.commands.init import add_init_parser, run_init
from aios.commands.launcher import add_launcher_parser, run_launcher
from aios.commands.model import add_model_parser, run_model
from aios.commands.pack import add_pack_parser, run_pack
from aios.commands.repo import add_repo_parser, run_repo
from aios.commands.review_cmd import add_review_parser, run_review
from aios.commands.run import add_run_parser, run_run
from aios.commands.route import add_route_parser, run_route
from aios.commands.scan import add_scan_parser, run_scan
from aios.commands.session_cmd import add_session_parser, run_session
from aios.commands.status import add_status_parser, run_status
from aios.commands.task import add_task_parser, run_task
from aios.commands.web import add_web_parser, run_web


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aios", description="AIOS local AI development center")
    parser.add_argument("--root", default=".", help="Project root path. Defaults to current directory.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_init_parser(subparsers)
    add_scan_parser(subparsers)
    add_status_parser(subparsers)
    add_ccswitch_parser(subparsers)
    add_executor_parser(subparsers)
    add_guard_parser(subparsers)
    add_goal_parser(subparsers)
    add_model_parser(subparsers)
    add_repo_parser(subparsers)
    add_review_parser(subparsers)
    add_session_parser(subparsers)
    add_task_parser(subparsers)
    add_route_parser(subparsers)
    add_pack_parser(subparsers)
    add_run_parser(subparsers)
    add_handoff_parser(subparsers)
    add_complete_parser(subparsers)
    add_web_parser(subparsers)
    add_launcher_parser(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    runners = {
        "init": run_init,
        "scan": run_scan,
        "status": run_status,
        "ccswitch": run_ccswitch,
        "executor": run_executor,
        "guard": run_guard,
        "goal": run_goal,
        "model": run_model,
        "repo": run_repo,
        "review": run_review,
        "session": run_session,
        "task": run_task,
        "route": run_route,
        "pack": run_pack,
        "run": run_run,
        "handoff": run_handoff,
        "complete": run_complete,
        "web": run_web,
        "launcher": run_launcher,
    }
    try:
        runners[args.command](root, args)
        return 0
    except FileNotFoundError as exc:
        parser.exit(2, f"error: {exc}\n")
    except ValueError as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
