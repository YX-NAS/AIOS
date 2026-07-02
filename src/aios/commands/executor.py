from __future__ import annotations

import argparse
import json
from pathlib import Path

from aios.core.executors import (
    create_executor,
    delete_executor,
    executor_summary,
    get_executor,
    reset_executor_library,
    update_executor,
)


def add_executor_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("executor", help="Manage AIOS executors.")
    executor_subparsers = parser.add_subparsers(dest="executor_command", required=True)

    executor_subparsers.add_parser("list", help="List executors.")

    show = executor_subparsers.add_parser("show", help="Show one executor.")
    show.add_argument("executor_id")

    create = executor_subparsers.add_parser("create", help="Create one executor.")
    _add_mutation_arguments(create, create_mode=True)

    update = executor_subparsers.add_parser("update", help="Update one executor.")
    update.add_argument("current_executor_id")
    _add_mutation_arguments(update, create_mode=False)

    delete = executor_subparsers.add_parser("delete", help="Delete one executor.")
    delete.add_argument("executor_id")

    executor_subparsers.add_parser("reset", help="Reset executor library to defaults.")


def run_executor(root: Path, args: argparse.Namespace) -> None:
    if args.executor_command == "list":
        summary = executor_summary()
        for executor in summary["executors"]:
            status = "enabled" if executor["enabled"] else "disabled"
            print(f"{executor['id']} [{executor['kind']}] {status} rank={executor['rank']} label={executor['label']}")
        return

    if args.executor_command == "show":
        print(json.dumps(get_executor(None, args.executor_id), ensure_ascii=False, indent=2))
        return

    if args.executor_command == "create":
        env = _parse_env_pairs(args.env or [])
        executor = create_executor(
            None,
            args.executor_id,
            label=args.label,
            kind=args.kind,
            enabled=not args.disabled,
            rank=args.rank,
            binary=args.binary,
            args=args.arg or [],
            timeout_seconds=args.timeout,
            pass_model_as_flag=args.pass_model_as_flag,
            env=env,
            resume_args=args.resume_arg or [],
            continue_args=args.continue_arg or [],
            resume_in_project_root=not args.no_resume_project_root,
            session_ref_label=args.session_ref_label,
        )
        print(f"Created executor: {executor['id']}")
        return

    if args.executor_command == "update":
        env = _parse_env_pairs(args.env or [])
        executor = update_executor(
            None,
            args.current_executor_id,
            args.executor_id,
            label=args.label,
            kind=args.kind,
            enabled=not args.disabled,
            rank=args.rank,
            binary=args.binary,
            args=args.arg or [],
            timeout_seconds=args.timeout,
            pass_model_as_flag=args.pass_model_as_flag,
            env=env,
            resume_args=args.resume_arg or [],
            continue_args=args.continue_arg or [],
            resume_in_project_root=not args.no_resume_project_root,
            session_ref_label=args.session_ref_label,
        )
        print(f"Updated executor: {executor['id']}")
        return

    if args.executor_command == "delete":
        delete_executor(None, args.executor_id)
        print(f"Deleted executor: {args.executor_id}")
        return

    if args.executor_command == "reset":
        executors = reset_executor_library()
        print(f"Reset executor library with {len(executors)} executors.")
        return


def _add_mutation_arguments(parser: argparse.ArgumentParser, create_mode: bool) -> None:
    if create_mode:
        parser.add_argument("executor_id")
    else:
        parser.add_argument("executor_id")
    parser.add_argument("--label", default=None)
    parser.add_argument("--kind", default="command", choices=["manual", "command"])
    parser.add_argument("--disabled", action="store_true")
    parser.add_argument("--rank", type=int, default=1)
    parser.add_argument("--binary", default=None)
    parser.add_argument("--arg", action="append", default=[], help="Repeatable command argument.")
    parser.add_argument("--timeout", type=int, default=None, help="Optional timeout in seconds.")
    parser.add_argument("--pass-model-as-flag", action="store_true")
    parser.add_argument("--env", action="append", default=[], help="Repeatable KEY=VALUE pair.")
    parser.add_argument("--resume-arg", action="append", default=[], help="Repeatable resume command argument template.")
    parser.add_argument("--continue-arg", action="append", default=[], help="Repeatable continue-latest command argument template.")
    parser.add_argument("--no-resume-project-root", action="store_true", help="Do not wrap resume commands with project root cd.")
    parser.add_argument("--session-ref-label", default=None, help="Human label for attached session reference.")


def _parse_env_pairs(pairs: list[str]) -> dict[str, str]:
    env: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"Invalid env pair: {pair}")
        key, value = pair.split("=", 1)
        env[key.strip()] = value
    return env
