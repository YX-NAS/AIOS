from __future__ import annotations

import argparse
from pathlib import Path

from aios.core.executions import execution_summary
from aios.core.models import model_summary
from aios.core.paths import require_aios
from aios.core.runtime_policy import runtime_policy_summary
from aios.core.tasks import load_tasks
from aios.utils.json_utils import read_json


def add_status_parser(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser("status", help="Show AIOS project status.")


def run_status(root: Path, args: argparse.Namespace) -> None:
    aios_dir = require_aios(root)
    tasks = load_tasks(root)
    file_index = read_json(aios_dir / "file-index.json", {})
    execution = execution_summary(root)
    policy = runtime_policy_summary(root)
    models = model_summary()
    done = len([task for task in tasks if task["status"] == "done"])
    todo = len([task for task in tasks if task["status"] != "done"])
    print(f"AIOS: {aios_dir}")
    print(f"Tasks: {len(tasks)} total, {todo} open, {done} done")
    print(
        "Executions: "
        f"{execution['execution_count']} total, "
        f"{execution['active_execution_count']} active, "
        f"latest={execution['latest_execution_status'] or '-'}"
    )
    print(
        "Usage: "
        f"prompt={execution['total_prompt_token_estimate']} tok, "
        f"output={execution['total_output_token_estimate']} tok, "
        f"cost~{execution['total_estimated_cost']} {execution['cost_currency']}"
    )
    if execution.get("average_duration_seconds") is not None:
        print(
            "Timing: "
            f"avg={execution['average_duration_seconds']}s, "
            f"latest={execution['latest_execution_duration_seconds'] or '-'}s"
        )
    print(
        "Policy: "
        f"strategy={policy['dispatch_strategy']}, "
        f"budget_total={policy['max_total_estimated_cost'] if policy['max_total_estimated_cost'] is not None else '-'}, "
        f"budget_single={policy['max_single_execution_cost'] if policy['max_single_execution_cost'] is not None else '-'}, "
        f"block_unpriced={'yes' if policy['block_on_unpriced_model'] else 'no'}"
    )
    if policy.get("remaining_total_budget") is not None:
        print(f"Budget remaining: {policy['remaining_total_budget']} {policy['cost_currency']}")
    print(
        "Providers: "
        f"{models['provider_ready_count']} ready / "
        f"{models['enabled_model_count']} enabled models"
    )
    print(
        "Handshake: "
        f"{models['provider_handshake_ready_count']} ok / "
        f"{models['provider_handshake_failed_count']} failed"
    )
    if file_index:
        print(f"Files indexed: {file_index.get('summary', {}).get('file_count', 0)}")
    else:
        print("Files indexed: 0 (run `aios scan`)")
