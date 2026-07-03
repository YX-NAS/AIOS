from __future__ import annotations

import argparse

from aios.core.models import get_model, model_runtime_status, model_summary, probe_models


def add_model_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("model", help="Inspect AIOS global model readiness.")
    model_subparsers = parser.add_subparsers(dest="model_command", required=True)

    model_subparsers.add_parser("list", help="List models with readiness summary.")
    doctor = model_subparsers.add_parser("doctor", help="Check one model or every model.")
    doctor.add_argument("model_id", nargs="?", default=None)
    probe = model_subparsers.add_parser("probe", help="Actively probe one model provider or all configured providers.")
    probe.add_argument("model_id", nargs="?", default=None)
    probe.add_argument("--timeout", type=float, default=3.0, help="HTTP timeout in seconds. Defaults to 3.0.")


def run_model(root, args: argparse.Namespace) -> None:
    if args.model_command == "list":
        summary = model_summary()
        for model in summary["models"]:
            runtime = model.get("runtime") or {}
            readiness = "ready" if runtime.get("ready") else "not-ready"
            status = "enabled" if model.get("enabled") else "disabled"
            pricing = f" cost_in={model.get('input_cost_per_1m') or '-'} cost_out={model.get('output_cost_per_1m') or '-'} {model.get('cost_currency') or 'USD'}"
            print(f"{model['id']} [{model['provider']}] {status} {readiness} rank={model['rank']} label={model['label']}{pricing}")
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
            print(f"  input_cost_per_1m: {model.get('input_cost_per_1m') if model.get('input_cost_per_1m') is not None else '-'}")
            print(f"  output_cost_per_1m: {model.get('output_cost_per_1m') if model.get('output_cost_per_1m') is not None else '-'}")
            print(f"  cost_currency: {model.get('cost_currency') or 'USD'}")
            print(f"  provider_config: {runtime.get('provider_config_status') or '-'}")
            print(f"  handshake_status: {runtime.get('handshake_status') or '-'}")
            print(f"  handshake_http_status: {runtime.get('handshake_http_status') if runtime.get('handshake_http_status') is not None else '-'}")
            print(f"  handshake_checked_at: {runtime.get('handshake_checked_at') or '-'}")
            print(f"  handshake_target_url: {runtime.get('handshake_target_url') or '-'}")
            print(f"  auth_probe_status: {runtime.get('auth_probe_status') or '-'}")
            print(f"  auth_probe_http_status: {runtime.get('auth_probe_http_status') if runtime.get('auth_probe_http_status') is not None else '-'}")
            print(f"  auth_probe_checked_at: {runtime.get('auth_probe_checked_at') or '-'}")
            print(f"  auth_probe_target_url: {runtime.get('auth_probe_target_url') or '-'}")
            print(f"  reason: {runtime.get('reason') or '-'}")
        return

    if args.model_command == "probe":
        results = probe_models(None, args.model_id, timeout_seconds=args.timeout)
        for result in results:
            print(
                f"{result['model_id']}: {result['status']} "
                f"url={result.get('target_url') or '-'} "
                f"http={result.get('http_status') if result.get('http_status') is not None else '-'} "
                f"latency_ms={result.get('latency_ms') if result.get('latency_ms') is not None else '-'}"
            )
            print(f"  checked_at: {result.get('checked_at') or '-'}")
            print(
                "  auth_probe: "
                f"{result.get('auth_probe_status') or '-'} "
                f"http={result.get('auth_probe_http_status') if result.get('auth_probe_http_status') is not None else '-'} "
                f"url={result.get('auth_probe_target_url') or '-'}"
            )
            print(f"  reason: {result.get('reason') or '-'}")
        return
