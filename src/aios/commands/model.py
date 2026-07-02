from __future__ import annotations

import argparse

from aios.core.models import get_model, model_runtime_status, model_summary


def add_model_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("model", help="Inspect AIOS global model readiness.")
    model_subparsers = parser.add_subparsers(dest="model_command", required=True)

    model_subparsers.add_parser("list", help="List models with readiness summary.")
    doctor = model_subparsers.add_parser("doctor", help="Check one model or every model.")
    doctor.add_argument("model_id", nargs="?", default=None)


def run_model(root, args: argparse.Namespace) -> None:
    if args.model_command == "list":
        summary = model_summary()
        for model in summary["models"]:
            runtime = model.get("runtime") or {}
            readiness = "ready" if runtime.get("ready") else "not-ready"
            status = "enabled" if model.get("enabled") else "disabled"
            print(f"{model['id']} [{model['provider']}] {status} {readiness} rank={model['rank']} label={model['label']}")
        return

    if args.model_command == "doctor":
        models = model_summary()["models"]
        if args.model_id:
            model = get_model(None, args.model_id)
            if not model:
                raise ValueError(f"Model not found: {args.model_id}")
            models = [{**model, "runtime": model_runtime_status(model)}]
        for model in models:
            runtime = model.get("runtime") or model_runtime_status(model)
            print(f"{model['id']}: {'ready' if runtime.get('ready') else 'not-ready'}")
            print(f"  provider: {model.get('provider') or '-'}")
            print(f"  endpoint: {runtime.get('endpoint') or '-'}")
            print(f"  config_url: {runtime.get('config_url') or '-'}")
            print(f"  auth_status: {runtime.get('auth_status') or '-'}")
            print(f"  auth_env_vars: {', '.join(runtime.get('auth_env_vars') or []) or '-'}")
            print(f"  present_env_vars: {', '.join(runtime.get('present_auth_env_vars') or []) or '-'}")
            print(f"  missing_env_vars: {', '.join(runtime.get('missing_auth_env_vars') or []) or '-'}")
            print(f"  provider_config: {runtime.get('provider_config_status') or '-'}")
            print(f"  reason: {runtime.get('reason') or '-'}")
        return
