from __future__ import annotations

import argparse
from pathlib import Path

from aios.core.dispatch import auto_progress_next_step
from aios.core.executions import (
    attach_execution_session,
    auto_finish_execution,
    build_execution_resume,
    finish_manual_execution,
    latest_execution_for_task,
    open_execution_resume_in_terminal,
    prepare_manual_execution,
    run_executor_execution,
    run_executor_with_auto_finish,
)


def add_run_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("run", help="Manage semi-automatic task execution.")
    parser.add_argument("run_target", nargs="?", help="Task ID for manual mode, or `auto` / `approve` / `status` / `finish` / `attach` / `resume`.")
    parser.add_argument("task_id", nargs="?", help="Task ID for status / finish / attach / resume mode.")
    parser.add_argument("--manual", action="store_true", help="Prepare one manual execution.")
    parser.add_argument("--executor", default=None, help="Run one configured executor.")
    parser.add_argument("--model", default=None, help="Execution model. Defaults to the task recommendation.")
    parser.add_argument("--refresh-pack", action="store_true", help="Rebuild the task context pack before preparing.")
    parser.add_argument("--start", action="store_true", help="Mark the execution as started immediately.")
    parser.add_argument("--note", default=None, help="Optional operator note.")
    parser.add_argument("--summary", default=None, help="Completion summary for finish mode.")
    parser.add_argument("--actual-model", default=None, help="Actual execution model used by the operator.")
    parser.add_argument("--test-command", default=None, help="Test command used for verification.")
    parser.add_argument("--test-result", default=None, help="Test result summary.")
    parser.add_argument("--score", type=int, default=None, choices=[1, 2, 3, 4, 5], help="Model effectiveness score (1-5).")
    parser.add_argument("--score-note", default=None, help="Optional note about the score.")
    parser.add_argument("--auto-finish", action="store_true", help="Automatically finish one review_pending execution when possible.")
    parser.add_argument("--verify-command", default=None, help="Verification command to run before auto finish.")
    parser.add_argument("--auto-commit", action="store_true", help="Automatically commit git changes after finish when the repo was clean before execution.")
    parser.add_argument("--auto-push", action="store_true", help="Automatically push the current branch after one auto commit.")
    parser.add_argument("--push-remote", default="origin", help="Git remote used for auto push. Defaults to origin.")
    parser.add_argument("--allow-protected-push", action="store_true", help="Allow auto push on protected branches like main/master.")
    parser.add_argument("--auto-pr", action="store_true", help="Automatically create a draft PR after successful auto push.")
    parser.add_argument("--pr-base-branch", default="main", help="Base branch used for auto PR draft creation. Defaults to main.")
    parser.add_argument("--session-id", default=None, help="External session id used for attach/resume.")
    parser.add_argument("--session-name", default=None, help="External session name used for attach/resume.")
    parser.add_argument("--session-note", default=None, help="Optional note recorded with one attached session.")
    parser.add_argument("--latest-session", action="store_true", help="Use the executor's continue-latest command for resume.")
    parser.add_argument("--open-terminal", action="store_true", help="Open the generated resume command in Terminal on macOS.")
    parser.add_argument("--terminal-app", default="Terminal", help="Terminal app used by --open-terminal. Defaults to Terminal.")


def run_run(root: Path, args: argparse.Namespace) -> None:
    if args.run_target == "auto":
        result = auto_progress_next_step(
            root,
            executor_id=args.executor,
            model=args.model,
            refresh_pack=args.refresh_pack,
            note=args.note,
            auto_finish=args.auto_finish,
            summary=args.summary,
            actual_model=args.actual_model,
            verify_command=args.verify_command,
            score=args.score,
            score_note=args.score_note,
            auto_commit=args.auto_commit,
            auto_push=args.auto_push,
            push_remote=args.push_remote,
            allow_protected_push=args.allow_protected_push,
            auto_pr=args.auto_pr,
            pr_base_branch=args.pr_base_branch,
        )
        if not result["progressed"]:
            print(f"Auto dispatch skipped: {result['reason']}")
            if result["executor"]:
                print(f"Default executor: {result['executor']['id']}")
            next_task = result["scheduler_before"].get("next_task_id")
            next_action = result["scheduler_before"].get("next_action")
            if next_task or next_action:
                print(f"Scheduler next: {next_task or '-'} [{next_action or '-'}]")
            return
        if result["auto_finished"] and not result["dispatched"]:
            print(f"Auto finished task: {result['task']['id']} {result['task']['title']}")
            print(f"Execution: {result['execution']['execution_id']} [{result['execution']['status']}]")
            if result.get("verification"):
                print(f"Verification: {result['verification']['summary']}")
            _print_git_commit(result.get("git_commit"))
            _print_git_push(result.get("git_push"))
            _print_git_pr(result.get("git_pr"))
            return
        execution = result["execution"]
        route = result["route"]
        handoff = result["handoff"]
        scheduler_item = result["scheduler_item"]
        print(f"Dispatched task: {result['task']['id']} {result['task']['title']}")
        print(f"Execution: {execution['execution_id']}")
        print(f"Executor: {result['executor']['id']}")
        print(f"Status: {execution['status']}")
        print(f"Planned model: {execution['planned_model']}")
        print(f"Fallback models: {', '.join(route['fallback_models']) or '-'}")
        print(f"Context pack: {handoff['pack_path']}")
        print(f"Handoff: {handoff['handoff_path']}")
        print(f"Scheduler reason: {scheduler_item['reason']}")
        if execution.get("executor_command"):
            print(f"Command: {execution['executor_command']}")
        if execution.get("executor_log_path"):
            print(f"Log: {execution['executor_log_path']}")
        if result.get("verification"):
            print(f"Verification: {result['verification']['summary']}")
        _print_git_commit(result.get("git_commit"))
        _print_git_push(result.get("git_push"))
        _print_git_pr(result.get("git_pr"))
        if result["auto_finished"]:
            print("Next: task has been auto-finished and written back to AIOS.")
        elif execution["status"] == "review_pending":
            print("Next: review the generated changes and use `aios run finish` to accept the task.")
        elif execution["status"] == "failed":
            print("Next: inspect the execution log, then retry manually or dispatch another ready task later.")
        return

    if args.run_target == "approve":
        if not args.task_id:
            raise ValueError("Task ID is required for `aios run approve`.")
        result = auto_finish_execution(
            root,
            args.task_id,
            summary=args.summary,
            actual_model=args.actual_model,
            verify_command=args.verify_command,
            score=args.score,
            score_note=args.score_note,
            auto_commit=args.auto_commit,
            auto_push=args.auto_push,
            push_remote=args.push_remote,
            allow_protected_push=args.allow_protected_push,
            auto_pr=args.auto_pr,
            pr_base_branch=args.pr_base_branch,
        )
        if not result["finished"]:
            print(f"Auto finish skipped: {result['reason']}")
            if result.get("verification"):
                print(f"Verification: {result['verification']['summary']}")
            return
        print(f"Auto finished {result['task']['id']}: {result['task']['title']}")
        if result.get("verification"):
            print(f"Verification: {result['verification']['summary']}")
        _print_git_commit(result.get("git_commit"))
        _print_git_push(result.get("git_push"))
        _print_git_pr(result.get("git_pr"))
        print(f"Execution: {result['execution']['execution_id']} [{result['execution']['status']}]")
        return

    if args.run_target == "status":
        if not args.task_id:
            raise ValueError("Task ID is required for `aios run status`.")
        execution = latest_execution_for_task(root, args.task_id)
        if not execution:
            print(f"No execution record for {args.task_id}.")
            return
        _print_execution(execution)
        return

    if args.run_target == "finish":
        if not args.task_id:
            raise ValueError("Task ID is required for `aios run finish`.")
        if not args.summary:
            raise ValueError("Use `--summary` to finish one task execution.")
        result = finish_manual_execution(
            root,
            args.task_id,
            args.summary,
            actual_model=args.actual_model,
            test_command=args.test_command,
            test_result=args.test_result,
            score=args.score,
            score_note=args.score_note,
            auto_commit=args.auto_commit,
            auto_push=args.auto_push,
            push_remote=args.push_remote,
            allow_protected_push=args.allow_protected_push,
            auto_pr=args.auto_pr,
            pr_base_branch=args.pr_base_branch,
        )
        print(f"Finished {result['task']['id']}: {result['task']['title']}")
        if result["execution"]:
            print(f"Execution: {result['execution']['execution_id']} [{result['execution']['status']}]")
        _print_git_commit(result.get("git_commit"))
        _print_git_push(result.get("git_push"))
        _print_git_pr(result.get("git_pr"))
        return

    if args.run_target == "attach":
        if not args.task_id:
            raise ValueError("Task ID is required for `aios run attach`.")
        result = attach_execution_session(
            root,
            args.task_id,
            executor_id=args.executor,
            session_id=args.session_id,
            session_name=args.session_name,
            session_note=args.session_note,
        )
        print(f"Attached session for {result['task']['id']}: {result['task']['title']}")
        print(f"Execution: {result['execution']['execution_id']}")
        print(f"Executor: {result['executor']['id']}")
        print(f"Session ref: {result['session_ref']}")
        print(f"Resume command: {result['execution'].get('executor_resume_command') or '-'}")
        if result['execution'].get("executor_continue_command"):
            print(f"Continue latest: {result['execution']['executor_continue_command']}")
        return

    if args.run_target == "resume":
        if not args.task_id:
            raise ValueError("Task ID is required for `aios run resume`.")
        if args.open_terminal:
            result = open_execution_resume_in_terminal(
                root,
                args.task_id,
                latest=bool(args.latest_session),
                terminal_app=args.terminal_app,
            )
            print(f"Resume opened for {result['task']['id']}: {result['task']['title']}")
            print(f"Execution: {result['execution']['execution_id']}")
            print(f"Executor: {result['executor']['id']}")
            print(f"Mode: {result['mode']}")
            print(f"Session ref: {result.get('session_ref') or '-'}")
            print(f"Terminal: {result['terminal']['app']}")
            print(f"Command: {result['command']}")
            return
        result = build_execution_resume(root, args.task_id, latest=bool(args.latest_session))
        print(f"Resume ready for {result['task']['id']}: {result['task']['title']}")
        print(f"Execution: {result['execution']['execution_id']}")
        print(f"Executor: {result['executor']['id']}")
        print(f"Mode: {result['mode']}")
        print(f"Session ref: {result.get('session_ref') or '-'}")
        print(f"Command: {result['command']}")
        return

    task_id = args.run_target
    if not task_id:
        raise ValueError("Task ID is required.")

    if args.executor:
        result = run_executor_with_auto_finish(
            root,
            task_id,
            args.executor,
            model=args.model,
            refresh_pack=args.refresh_pack,
            note=args.note,
            auto_finish=args.auto_finish,
            summary=args.summary,
            actual_model=args.actual_model,
            verify_command=args.verify_command,
            score=args.score,
            score_note=args.score_note,
            auto_commit=args.auto_commit,
            auto_push=args.auto_push,
            push_remote=args.push_remote,
            allow_protected_push=args.allow_protected_push,
            auto_pr=args.auto_pr,
            pr_base_branch=args.pr_base_branch,
        )
        execution = result["execution"]
        route = result["route"]
        handoff = result["handoff"]
        print(f"Task: {result['task']['id']}")
        print(f"Execution: {execution['execution_id']}")
        print(f"Executor: {result['executor']['id']}")
        print(f"Status: {execution['status']}")
        print(f"Planned model: {execution['planned_model']}")
        print(f"Fallback models: {', '.join(route['fallback_models']) or '-'}")
        print(f"Context pack: {handoff['pack_path']}")
        print(f"Handoff: {handoff['handoff_path']}")
        if execution.get("executor_command"):
            print(f"Command: {execution['executor_command']}")
        if execution.get("executor_log_path"):
            print(f"Log: {execution['executor_log_path']}")
        if result.get("verification"):
            print(f"Verification: {result['verification']['summary']}")
        _print_git_commit(result.get("git_commit"))
        _print_git_push(result.get("git_push"))
        _print_git_pr(result.get("git_pr"))
        if result["auto_finished"]:
            print("Next: task has been auto-finished and written back to AIOS.")
        elif execution["status"] == "review_pending":
            print("Next: review the generated changes and use `aios run finish` to accept the task.")
        elif execution["status"] == "failed":
            print("Next: inspect the execution log, then retry or fall back to `aios run --manual`.")
        return

    if not args.manual:
        raise ValueError("Use `aios run auto [--executor ...]`, `aios run approve TASK-ID --summary ...`, `aios run attach TASK-ID`, `aios run resume TASK-ID`, `aios run --manual TASK-ID`, `aios run TASK-ID --executor EXECUTOR`, or `aios run status|finish ...`.")

    result = prepare_manual_execution(
        root,
        task_id,
        model=args.model,
        refresh_pack=args.refresh_pack,
        start=args.start,
        note=args.note,
    )
    execution = result["execution"]
    route = result["route"]
    handoff = result["handoff"]
    print(f"Task: {result['task']['id']}")
    print(f"Execution: {execution['execution_id']}")
    print(f"Status: {execution['status']}")
    print(f"Planned model: {execution['planned_model']}")
    print(f"Fallback models: {', '.join(route['fallback_models']) or '-'}")
    print(f"Context pack: {handoff['pack_path']}")
    print(f"Handoff: {handoff['handoff_path']}")
    print("Next: switch ccswitch manually, run the task in Codex or Claude Code, then use `aios run finish`.")


def _print_execution(execution: dict) -> None:
    print(f"Execution: {execution['execution_id']}")
    print(f"Task: {execution['task_id']} {execution['task_title']}")
    print(f"Mode: {execution['mode']}")
    print(f"Status: {execution['status']}")
    print(f"Planned model: {execution['planned_model']}")
    print(f"Actual model: {execution.get('actual_model') or '-'}")
    print(f"Context pack: {execution['pack_path']}")
    print(f"Handoff: {execution['handoff_path']}")
    print(f"Started at: {execution.get('started_at') or '-'}")
    print(f"Finished at: {execution.get('finished_at') or '-'}")
    print(f"Executor: {execution.get('executor_id') or '-'}")
    print(f"Command: {execution.get('executor_command') or '-'}")
    print(f"Exit code: {execution.get('executor_exit_code') if execution.get('executor_exit_code') is not None else '-'}")
    print(f"Log: {execution.get('executor_log_path') or '-'}")
    print(f"Session ref: {execution.get('executor_session_id') or execution.get('executor_session_name') or '-'}")
    print(f"Session captured: {'auto' if execution.get('executor_session_auto_captured') else ('manual' if execution.get('executor_session_attached_at') else '-')}")
    print(f"Resume command: {execution.get('executor_resume_command') or '-'}")
    print(f"Continue latest: {execution.get('executor_continue_command') or '-'}")
    print(f"Terminal launch: {execution.get('executor_terminal_launch_status') or '-'}")
    print(f"Terminal app: {execution.get('executor_terminal_launch_app') or '-'}")
    print(f"Terminal launch at: {execution.get('executor_terminal_launch_at') or '-'}")
    print(f"Test command: {execution.get('test_command') or '-'}")
    print(f"Test result: {execution.get('test_result') or '-'}")
    print(f"Git clean before: {execution.get('git_is_clean_before')}")
    print(f"Auto commit: {execution.get('auto_commit_status') or '-'}")
    print(f"Git commit after: {execution.get('git_commit_after') or '-'}")
    print(f"Auto push: {execution.get('auto_push_status') or '-'}")
    print(f"Push remote: {execution.get('auto_push_remote') or '-'}")
    print(f"Push branch: {execution.get('auto_push_branch') or '-'}")
    print(f"Auto PR: {execution.get('auto_pr_status') or '-'}")
    print(f"PR URL: {execution.get('auto_pr_url') or '-'}")


def _print_git_commit(commit: dict | None) -> None:
    if not commit:
        return
    if commit.get("committed"):
        print(f"Git commit: {commit.get('commit')} on {commit.get('branch')}")
        return
    if commit.get("reason"):
        print(f"Git commit skipped: {commit['reason']}")


def _print_git_push(push: dict | None) -> None:
    if not push:
        return
    if push.get("pushed"):
        print(f"Git push: {push.get('remote')}/{push.get('branch')} @ {push.get('commit')}")
        return
    if push.get("reason"):
        print(f"Git push skipped: {push['reason']}")


def _print_git_pr(pr: dict | None) -> None:
    if not pr:
        return
    if pr.get("created"):
        print(f"Draft PR: {pr.get('url')} #{pr.get('number')}")
        return
    if pr.get("reason"):
        print(f"Draft PR skipped: {pr['reason']}")
