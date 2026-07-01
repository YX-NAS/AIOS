from __future__ import annotations

from pathlib import Path

from aios.core.context_builder import build_context_pack, safe_model_name
from aios.core.paths import require_aios
from aios.core.router import route_task
from aios.core.tasks import get_task
from aios.utils.text import now_iso


def build_handoff(root: Path, task_id: str, model: str | None = None, refresh_pack: bool = False) -> dict:
    task = get_task(root, task_id)
    route = route_task(task, root)
    selected_model = model or route["recommended_model"]
    pack_path = _resolve_pack(root, task, selected_model, refresh_pack)
    handoff_path = _write_handoff(root, task, route, selected_model, pack_path)
    return {
        "task": task,
        "route": route,
        "model": selected_model,
        "pack_path": str(pack_path.relative_to(root)),
        "handoff_path": str(handoff_path.relative_to(root)),
        "content": handoff_path.read_text(encoding="utf-8"),
    }


def _resolve_pack(root: Path, task: dict, model: str, refresh_pack: bool) -> Path:
    aios_dir = require_aios(root)
    candidate = aios_dir / "context-packs" / f"{task['id']}-{safe_model_name(model)}.md"
    if refresh_pack or not candidate.exists():
        result = build_context_pack(root, task, model)
        return result["path"]
    return candidate


def _write_handoff(root: Path, task: dict, route: dict, model: str, pack_path: Path) -> Path:
    aios_dir = require_aios(root)
    handoff_dir = aios_dir / "handoffs"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    content = build_handoff_content(root, task, route, model, pack_path)
    target = handoff_dir / f"{task['id']}-{safe_model_name(model)}-handoff.md"
    target.write_text(content, encoding="utf-8")
    return target


def build_handoff_content(root: Path, task: dict, route: dict, model: str, pack_path: Path) -> str:
    pack_content = pack_path.read_text(encoding="utf-8").strip()
    parts = [
        "# AIOS Task Handoff",
        "",
        f"- Generated at: {now_iso()}",
        f"- Project root: {root}",
        f"- Task ID: {task['id']}",
        f"- Task title: {task['title']}",
        f"- Task type: {task['type']}",
        f"- Priority: {task['priority']}",
        f"- Recommended model: {route['recommended_model']}",
        f"- Execution model: {model}",
        f"- Fallback models: {', '.join(route['fallback_models'])}",
        f"- Context pack path: {pack_path.relative_to(root)}",
        "",
        "## Manual execution steps",
        "",
        "1. Open cc-switch and switch to the execution model above.",
        "2. Open Codex or Claude Code with the target project directory.",
        "3. Paste the Context Pack below as the working context.",
        "4. Implement only the current task and run the necessary tests.",
        "5. Return the completion summary to AIOS after verification.",
        "",
        "## Acceptance criteria",
        "",
        *[f"- {item}" for item in task["acceptance_criteria"]],
        "",
        "## Routing reason",
        "",
        *[f"- {item}" for item in route["reason"]],
        "",
        "## Context Pack",
        "",
        pack_content,
        "",
    ]
    return "\n".join(parts)
