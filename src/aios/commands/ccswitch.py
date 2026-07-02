from __future__ import annotations

import argparse
from pathlib import Path

from aios.core.ccswitch import (
    build_ccswitch_deeplink,
    build_ccswitch_provider_deeplink,
    export_ccswitch_payload,
    export_ccswitch_session_handoff,
    export_payload_as_text,
)


def add_ccswitch_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("ccswitch", help="Export ccswitch adapter payloads.")
    ccswitch_subparsers = parser.add_subparsers(dest="ccswitch_command", required=True)

    export = ccswitch_subparsers.add_parser("export", help="Export one task as ccswitch JSON.")
    export.add_argument("task_id")
    export.add_argument("--model", default=None, help="Optional export model override.")
    export.add_argument("--stdout", action="store_true", help="Also print the JSON payload to stdout.")

    deeplink = ccswitch_subparsers.add_parser("deeplink", help="Generate one ccswitch prompt deeplink.")
    deeplink.add_argument("task_id")
    deeplink.add_argument("--app", default="codex", help="Target app for ccswitch deeplink. Defaults to codex.")
    deeplink.add_argument("--model", default=None, help="Optional model override used in the handoff description.")
    deeplink.add_argument("--open", action="store_true", help="Open the deeplink with the local OS.")
    deeplink.add_argument("--stdout", action="store_true", help="Also print the deeplink URL to stdout.")

    provider = ccswitch_subparsers.add_parser("provider", help="Generate one ccswitch provider deeplink.")
    provider.add_argument("task_id")
    provider.add_argument("--app", default="codex", help="Target app for ccswitch deeplink. Defaults to codex.")
    provider.add_argument("--model", default=None, help="Optional model override used in the provider payload.")
    provider.add_argument("--open", action="store_true", help="Open the deeplink with the local OS.")
    provider.add_argument("--stdout", action="store_true", help="Also print the deeplink URL to stdout.")

    session = ccswitch_subparsers.add_parser("session", help="Export one ccswitch session handoff JSON.")
    session.add_argument("task_id")
    session.add_argument("--app", default="codex", help="Target app for the handoff package. Defaults to codex.")
    session.add_argument("--model", default=None, help="Optional model override used in the handoff package.")
    session.add_argument("--stdout", action="store_true", help="Also print the handoff JSON payload to stdout.")


def run_ccswitch(root: Path, args: argparse.Namespace) -> None:
    if args.ccswitch_command == "export":
        result = export_ccswitch_payload(root, args.task_id, model=args.model)
        print(f"Exported {result['export_path']}")
        print(f"Task: {result['task']['id']} {result['task']['title']}")
        print(f"Planned model: {result['payload']['planned_model']}")
        print(f"Export model: {result['payload']['export_model']}")
        if args.stdout:
            print(export_payload_as_text(result["payload"]).rstrip())
        return

    if args.ccswitch_command == "deeplink":
        result = build_ccswitch_deeplink(root, args.task_id, app=args.app, model=args.model, open_link=bool(args.open))
        print(f"Generated deeplink for {result['app']}")
        print(f"Task: {result['task']['id']} {result['task']['title']}")
        if result["opened"]:
            print(f"Opened at: {result['opened_at']}")
        if args.stdout:
            print(result["deeplink"])
        return

    if args.ccswitch_command == "provider":
        result = build_ccswitch_provider_deeplink(
            root,
            args.task_id,
            app=args.app,
            model=args.model,
            open_link=bool(args.open),
        )
        print(f"Generated provider deeplink for {result['app']}")
        print(f"Task: {result['task']['id']} {result['task']['title']}")
        print(f"Provider: {result['provider']}")
        print(f"Model: {result['model']}")
        if result["opened"]:
            print(f"Opened at: {result['opened_at']}")
        if args.stdout:
            print(result["deeplink"])
        return

    if args.ccswitch_command == "session":
        result = export_ccswitch_session_handoff(root, args.task_id, app=args.app, model=args.model)
        print(f"Exported {result['handoff_path']}")
        print(f"Task: {result['task']['id']} {result['task']['title']}")
        print(f"App: {result['handoff']['app']}")
        print(f"Model: {result['handoff']['model']}")
        if args.stdout:
            print(export_payload_as_text(result["handoff"]).rstrip())
        return

    raise ValueError("Unsupported ccswitch command.")
