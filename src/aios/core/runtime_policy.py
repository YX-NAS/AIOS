from __future__ import annotations

from pathlib import Path

from aios.core.context_builder import preview_context_pack
from aios.core.executions import execution_summary
from aios.core.models import estimate_model_cost
from aios.core.paths import require_aios
from aios.utils.json_utils import read_json, write_json
from aios.utils.text import now_iso


DEFAULT_RUNTIME_POLICY = {
    "max_total_estimated_cost": None,
    "max_single_execution_cost": None,
    "block_on_unpriced_model": False,
    "dispatch_strategy": "default",
    "cost_currency": "USD",
    "updated_at": None,
}

DISPATCH_STRATEGIES = {"default", "cheapest_first"}
UNSET = object()


def runtime_policy_path(root: Path) -> Path:
    return require_aios(root) / "runtime-policy.json"


def load_runtime_policy(root: Path) -> dict:
    payload = read_json(runtime_policy_path(root), DEFAULT_RUNTIME_POLICY)
    return normalize_runtime_policy(payload)


def save_runtime_policy(root: Path, policy: dict) -> dict:
    normalized = normalize_runtime_policy(policy)
    normalized["updated_at"] = now_iso()
    write_json(runtime_policy_path(root), normalized)
    return normalized


def update_runtime_policy(
    root: Path,
    *,
    max_total_estimated_cost: float | None | object = UNSET,
    max_single_execution_cost: float | None | object = UNSET,
    block_on_unpriced_model: bool | None = None,
    dispatch_strategy: str | None = None,
    cost_currency: str | None = None,
) -> dict:
    current = load_runtime_policy(root)
    if max_total_estimated_cost is not UNSET:
        current["max_total_estimated_cost"] = _clean_optional_number(max_total_estimated_cost)
    if max_single_execution_cost is not UNSET:
        current["max_single_execution_cost"] = _clean_optional_number(max_single_execution_cost)
    if block_on_unpriced_model is not None:
        current["block_on_unpriced_model"] = bool(block_on_unpriced_model)
    if dispatch_strategy is not None:
        strategy = str(dispatch_strategy or "default").strip().lower() or "default"
        if strategy not in DISPATCH_STRATEGIES:
            raise ValueError(f"Unsupported dispatch strategy: {dispatch_strategy}")
        current["dispatch_strategy"] = strategy
    if cost_currency is not None:
        current["cost_currency"] = str(cost_currency or "USD").strip().upper() or "USD"
    return save_runtime_policy(root, current)


def normalize_runtime_policy(policy: dict | None) -> dict:
    payload = dict(DEFAULT_RUNTIME_POLICY)
    payload.update(policy or {})
    strategy = str(payload.get("dispatch_strategy") or "default").strip().lower() or "default"
    if strategy not in DISPATCH_STRATEGIES:
        strategy = "default"
    return {
        "max_total_estimated_cost": _clean_optional_number(payload.get("max_total_estimated_cost")),
        "max_single_execution_cost": _clean_optional_number(payload.get("max_single_execution_cost")),
        "block_on_unpriced_model": bool(payload.get("block_on_unpriced_model", False)),
        "dispatch_strategy": strategy,
        "cost_currency": str(payload.get("cost_currency") or "USD").strip().upper() or "USD",
        "updated_at": payload.get("updated_at"),
    }


def budget_guard_for_task(root: Path, task: dict, model: str) -> dict:
    policy = load_runtime_policy(root)
    preview = preview_context_pack(root, task, model)
    cost = estimate_model_cost(root, model, preview["token_estimate"], 0)
    usage = execution_summary(root)
    total_budget = policy.get("max_total_estimated_cost")
    single_budget = policy.get("max_single_execution_cost")
    spent = float(usage.get("total_estimated_cost") or 0.0)
    estimated_total = cost.get("estimated_total_cost")
    reasons: list[str] = []
    status = "ok"

    if estimated_total is None and policy.get("block_on_unpriced_model"):
        status = "blocked"
        reasons.append("当前模型未配置价格，预算策略要求先补齐定价后才能自动派发。")

    if single_budget is not None and estimated_total is not None and estimated_total > single_budget:
        status = "blocked"
        reasons.append(f"本次预计成本 {estimated_total} 已超过单次上限 {single_budget}。")

    if total_budget is not None:
        if spent >= total_budget:
            status = "blocked"
            reasons.append(f"项目累计预计成本 {spent} 已达到总预算上限 {total_budget}。")
        elif estimated_total is not None and spent + estimated_total > total_budget:
            status = "blocked"
            reasons.append(
                f"本次执行后预计累计成本 {round(spent + estimated_total, 6)} 将超过项目总预算 {total_budget}。"
            )

    remaining_budget = None
    if total_budget is not None:
        remaining_budget = round(total_budget - spent, 6)

    return {
        "status": status,
        "reason": "；".join(reasons) if reasons else "预算策略允许自动派发。",
        "policy": policy,
        "prompt_token_estimate": preview["token_estimate"],
        "estimated_total_cost": estimated_total,
        "estimated_input_cost": cost.get("estimated_input_cost"),
        "input_cost_per_1m": cost.get("input_cost_per_1m"),
        "output_cost_per_1m": cost.get("output_cost_per_1m"),
        "cost_currency": cost.get("cost_currency") or policy.get("cost_currency") or "USD",
        "spent_total_estimated_cost": round(spent, 6),
        "remaining_total_budget": remaining_budget,
        "context_window": preview["context_window"],
        "window_usage_pct": preview["window_usage_pct"],
    }


def runtime_policy_summary(root: Path) -> dict:
    policy = load_runtime_policy(root)
    usage = execution_summary(root)
    spent = round(float(usage.get("total_estimated_cost") or 0.0), 6)
    total_budget = policy.get("max_total_estimated_cost")
    return {
        **policy,
        "spent_total_estimated_cost": spent,
        "remaining_total_budget": round(total_budget - spent, 6) if total_budget is not None else None,
    }


def _clean_optional_number(value: object) -> float | None:
    if value in (None, ""):
        return None
    number = float(value)
    if number < 0:
        raise ValueError("Budget values must be non-negative.")
    return round(number, 6)
