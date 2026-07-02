from __future__ import annotations

import threading
from pathlib import Path

from aios.core.executions import execution_summary
from aios.core.instance_manager import DEFAULT_HOST, instance_status, project_id_for_root, state_dir
from aios.core.models import model_summary
from aios.core.paths import aios_path
from aios.core.scheduler import scheduler_summary
from aios.utils.json_utils import read_json, write_json
from aios.utils.text import now_iso

PROJECTS_LOCK = threading.Lock()


def projects_registry_path() -> Path:
    return state_dir() / "projects.json"


def load_projects() -> list[dict]:
    payload = read_json(projects_registry_path(), {"projects": []})
    return payload["projects"]


def save_projects(projects: list[dict]) -> None:
    write_json(projects_registry_path(), {"projects": projects})


def register_project(root: Path, name: str | None = None) -> dict:
    root = root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Project root does not exist: {root}")
    project_id = project_id_for_root(root)
    initialized = aios_path(root).exists()
    with PROJECTS_LOCK:
        projects = load_projects()
        existing = next((project for project in projects if project["project_id"] == project_id), None)
        if existing:
            existing["name"] = name or existing["name"]
            existing["root"] = str(root)
            existing["initialized"] = initialized
            save_projects(projects)
            return existing
        record = {
            "project_id": project_id,
            "name": name or root.name,
            "root": str(root),
            "added_at": now_iso(),
            "last_opened_at": None,
            "last_port": None,
            "status": "stopped",
            "initialized": initialized,
        }
        projects.append(record)
        save_projects(projects)
        return record


def get_project(project_id: str) -> dict:
    for project in load_projects():
        if project["project_id"] == project_id:
            return project
    raise ValueError(f"Project not found: {project_id}")


def update_project(project_id: str, **changes: object) -> dict:
    with PROJECTS_LOCK:
        projects = load_projects()
        for project in projects:
            if project["project_id"] == project_id:
                project.update(changes)
                save_projects(projects)
                return project
    raise ValueError(f"Project not found: {project_id}")


def project_runtime_data(root: Path) -> dict:
    aios_dir = aios_path(root)
    if not aios_dir.exists():
        return {
            "task_count": 0,
            "open_tasks": 0,
            "done_tasks": 0,
            "file_count": 0,
            "enabled_model_count": 0,
            "languages": [],
            "frameworks": [],
            "latest_task_title": None,
            "latest_goal": None,
            "last_task_updated_at": None,
            "execution_count": 0,
            "active_execution_count": 0,
            "latest_execution_status": None,
            "last_execution_updated_at": None,
            "ready_count": 0,
            "blocked_count": 0,
            "review_pending_count": 0,
            "failed_count": 0,
            "scheduler_next_task_id": None,
            "scheduler_next_task_title": None,
            "scheduler_next_action": None,
        }
    tasks_payload = read_json(aios_dir / "tasks.json", {"tasks": []})
    tasks = tasks_payload["tasks"]
    file_index = read_json(aios_dir / "file-index.json", {"summary": {}})
    file_summary = file_index.get("summary", {})
    latest_task = max(tasks, key=lambda item: item.get("updated_at", ""), default=None)
    latest_goal = None
    if latest_task and latest_task.get("source_goal"):
        latest_goal = latest_task["source_goal"]
    else:
        goals = [task.get("source_goal") for task in reversed(tasks) if task.get("source_goal")]
        latest_goal = goals[0] if goals else None
    schedule = scheduler_summary(root)
    return {
        "task_count": len(tasks),
        "open_tasks": len([task for task in tasks if task["status"] != "done"]),
        "done_tasks": len([task for task in tasks if task["status"] == "done"]),
        "file_count": file_summary.get("file_count", 0),
        "enabled_model_count": model_summary(root)["enabled_model_count"],
        "languages": file_summary.get("languages", []),
        "frameworks": file_summary.get("frameworks", []),
        "latest_task_title": latest_task.get("title") if latest_task else None,
        "latest_goal": latest_goal,
        "last_task_updated_at": latest_task.get("updated_at") if latest_task else None,
        **execution_summary(root),
        "ready_count": schedule["ready_count"],
        "blocked_count": schedule["blocked_count"],
        "review_pending_count": schedule["review_pending_count"],
        "failed_count": schedule["failed_count"],
        "scheduler_next_task_id": schedule["next_task_id"],
        "scheduler_next_task_title": schedule["next_task_title"],
        "scheduler_next_action": schedule["next_action"],
    }


def project_summary(project: dict, host: str = DEFAULT_HOST) -> dict:
    root = Path(project["root"])
    runtime = instance_status(root, project["project_id"], host)
    initialized = aios_path(root).exists() if root.exists() else False
    runtime_data = project_runtime_data(root) if root.exists() else project_runtime_data(Path("/__missing__"))
    summary = {
        **project,
        "initialized": initialized,
        "status": runtime["status"],
        "url": runtime["url"],
        "port": runtime["port"],
        "running": runtime["running"],
        "log_path": runtime["log_path"],
        "root_exists": root.exists(),
        **runtime_data,
    }
    return summary


def list_project_summaries(host: str = DEFAULT_HOST) -> list[dict]:
    return [project_summary(project, host) for project in load_projects()]
