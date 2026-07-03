from __future__ import annotations

import json
from pathlib import Path

from aios.core.paths import aios_path
from aios.core.templates import (
    ARCHITECTURE_MD,
    CHANGELOG_MD,
    DECISIONS_MD,
    DEFAULT_ROUTING,
    MEMORY_MD,
    RULES_MD,
    context_md,
    project_yaml,
)
from aios.utils.json_utils import write_json


def initialize_project(root: Path, name: str, project_type: str, force: bool = False) -> list[Path]:
    root.mkdir(parents=True, exist_ok=True)
    path = aios_path(root)
    if path.exists() and any(path.iterdir()) and not force:
        raise ValueError(".aios already exists. Use --force to recreate missing defaults.")

    created: list[Path] = []
    path.mkdir(exist_ok=True)
    (path / "context-packs").mkdir(exist_ok=True)
    (path / "handoffs").mkdir(exist_ok=True)
    (path / "logs").mkdir(exist_ok=True)
    (path / "reports").mkdir(exist_ok=True)

    files = {
        "project.yaml": project_yaml(name, project_type),
        "context.md": context_md(name),
        "architecture.md": ARCHITECTURE_MD,
        "decisions.md": DECISIONS_MD,
        "rules.md": RULES_MD,
        "memory.md": MEMORY_MD,
        "changelog.md": CHANGELOG_MD,
        "tasks.md": "# 任务列表\n\n暂无任务。\n",
    }
    for relative, content in files.items():
        target = path / relative
        if force or not target.exists():
            target.write_text(content, encoding="utf-8")
            created.append(target)

    tasks_json = path / "tasks.json"
    if force or not tasks_json.exists():
        write_json(tasks_json, {"tasks": []})
        created.append(tasks_json)

    task_plans_json = path / "task-plans.json"
    if force or not task_plans_json.exists():
        write_json(task_plans_json, {"drafts": []})
        created.append(task_plans_json)

    executions_json = path / "executions.json"
    if force or not executions_json.exists():
        write_json(executions_json, {"executions": []})
        created.append(executions_json)

    runtime_policy_json = path / "runtime-policy.json"
    if force or not runtime_policy_json.exists():
        write_json(
            runtime_policy_json,
            {
                "max_total_estimated_cost": None,
                "max_single_execution_cost": None,
                "block_on_unpriced_model": False,
                "dispatch_strategy": "default",
                "cost_currency": "USD",
                "updated_at": None,
            },
        )
        created.append(runtime_policy_json)

    routing_json = path / "model-routing.json"
    if force or not routing_json.exists():
        write_json(routing_json, {"routing_rules": DEFAULT_ROUTING})
        created.append(routing_json)

    routing_yaml = path / "model-routing.yaml"
    if force or not routing_yaml.exists():
        routing_yaml.write_text(_routing_yaml(), encoding="utf-8")
        created.append(routing_yaml)

    return created


def _routing_yaml() -> str:
    lines = ["routing_rules:"]
    for task_type, rule in DEFAULT_ROUTING.items():
        lines.append(f"  {task_type}:")
        for key in ("preferred_models", "fallback_models", "max_cost_level"):
            value = rule[key]
            if isinstance(value, list):
                lines.append(f"    {key}:")
                lines.extend(f"      - {item}" for item in value)
            else:
                lines.append(f"    {key}: {json.dumps(value, ensure_ascii=False)}")
    return "\n".join(lines) + "\n"
