from __future__ import annotations

import threading
from pathlib import Path

from aios.core.executors import executor_summary
from aios.core.executions import execution_summary, latest_execution_for_task
from aios.core.instance_manager import DEFAULT_HOST, instance_status, project_id_for_root, state_dir
from aios.core.models import model_summary
from aios.core.paths import aios_path
from aios.core.runtime_policy import runtime_policy_summary
from aios.core.scheduler import scheduler_summary
from aios.core.takeover import pending_takeover_count, takeover_summary
from aios.core.tasks import load_tasks
from aios.utils.json_utils import read_json, write_json
from aios.utils.text import now_iso, today

PROJECTS_LOCK = threading.Lock()

PRODUCTION_PROJECTS = [
    {
        "key": "xiazhi-ai",
        "name": "夏栀 AI",
        "path_parts": ("SynologyDrive", "日常工作", "Github", "xiazhi-ai.git"),
        "role": "第一产品主线",
        "priority": "P0",
    },
    {
        "key": "aios",
        "name": "AIOS",
        "path_parts": ("SynologyDrive", "日常工作", "Github", "AIOS"),
        "role": "第一生产力与系统管理核心",
        "priority": "P0",
    },
    {
        "key": "codex-deepseek-lifeline",
        "name": "codex-deepseek-lifeline",
        "path_parts": ("SynologyDrive", "日常工作", "Github", "codex-deepseek-lifeline"),
        "role": "Codex 续航与模型切换工具",
        "priority": "P1",
    },
    {
        "key": "ecosystem-hub",
        "name": "ecosystem-hub",
        "path_parts": ("SynologyDrive", "日常工作", "Github", "ecosystem-hub"),
        "role": "系统资产与监控总账",
        "priority": "P1",
    },
    {
        "key": "api-router",
        "name": "API_Router",
        "path_parts": ("SynologyDrive", "日常工作", "Github", "API_Router"),
        "role": "API、模型和服务路由底座",
        "priority": "P1",
    },
    {
        "key": "wxautomation",
        "name": "wxautomation",
        "path_parts": ("SynologyDrive", "日常工作", "Github", "VR", "wxautomation"),
        "role": "内容与微信自动化生产线",
        "priority": "P2",
    },
]

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
HEALTH_ORDER = {"blocked": 0, "broken": 1, "attention": 2, "setup": 3, "active": 4, "healthy": 5}


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
            "available_executor_count": 0,
            "provider_ready_count": 0,
            "provider_handshake_ready_count": 0,
            "provider_handshake_failed_count": 0,
            "provider_api_verified_count": 0,
            "provider_api_failed_count": 0,
            "languages": [],
            "frameworks": [],
            "latest_task_title": None,
            "latest_goal": None,
            "last_task_updated_at": None,
            "execution_count": 0,
            "active_execution_count": 0,
            "latest_execution_status": None,
            "last_execution_updated_at": None,
            "latest_execution_duration_seconds": None,
            "total_prompt_token_estimate": 0,
            "total_output_token_estimate": 0,
            "total_token_estimate": 0,
            "total_estimated_cost": 0.0,
            "cost_currency": "USD",
            "average_duration_seconds": None,
            "ready_count": 0,
            "blocked_count": 0,
            "bridge_pending_count": 0,
            "review_pending_count": 0,
            "failed_count": 0,
            "scheduler_next_task_id": None,
            "scheduler_next_task_title": None,
            "scheduler_next_action": None,
            "runtime_policy_dispatch_strategy": "default",
            "runtime_policy_max_total_estimated_cost": None,
            "runtime_policy_max_single_execution_cost": None,
            "runtime_policy_block_on_unpriced_model": False,
            "remaining_total_budget": None,
            "today_open_tasks": 0,
            "pending_takeover_count": 0,
            "health_state": "setup",
            "health_label": "待接入",
            "health_reasons": ["项目尚未初始化 AIOS"],
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
    policy = runtime_policy_summary(root)
    models = model_summary(root)
    executors = executor_summary(root)
    takeover_count = pending_takeover_count(root)
    today_prefix = today()
    today_open_tasks = len(
        [
            task
            for task in tasks
            if task.get("status") != "done"
            and str(task.get("updated_at") or task.get("created_at") or "").startswith(today_prefix)
        ]
    )
    execution_data = execution_summary(root)
    health = project_health(
        {
            "root_exists": True,
            "initialized": True,
            "file_count": file_summary.get("file_count", 0),
            "open_tasks": len([task for task in tasks if task["status"] != "done"]),
            "active_execution_count": execution_data["active_execution_count"],
            "ready_count": schedule["ready_count"],
            "blocked_count": schedule["blocked_count"],
            "failed_count": schedule["failed_count"],
            "pending_takeover_count": takeover_count,
            "provider_ready_count": models["provider_ready_count"],
            "available_executor_count": executors["available_executor_count"],
        }
    )
    return {
        "task_count": len(tasks),
        "open_tasks": len([task for task in tasks if task["status"] != "done"]),
        "done_tasks": len([task for task in tasks if task["status"] == "done"]),
        "file_count": file_summary.get("file_count", 0),
        "enabled_model_count": models["enabled_model_count"],
        "provider_ready_count": models["provider_ready_count"],
        "provider_handshake_ready_count": models["provider_handshake_ready_count"],
        "provider_handshake_failed_count": models["provider_handshake_failed_count"],
        "provider_api_verified_count": models["provider_api_verified_count"],
        "provider_api_failed_count": models["provider_api_failed_count"],
        "available_executor_count": executors["available_executor_count"],
        "languages": file_summary.get("languages", []),
        "frameworks": file_summary.get("frameworks", []),
        "latest_task_title": latest_task.get("title") if latest_task else None,
        "latest_goal": latest_goal,
        "last_task_updated_at": latest_task.get("updated_at") if latest_task else None,
        **execution_data,
        "ready_count": schedule["ready_count"],
        "blocked_count": schedule["blocked_count"],
        "bridge_pending_count": schedule["bridge_pending_count"],
        "review_pending_count": schedule["review_pending_count"],
        "failed_count": schedule["failed_count"],
        "scheduler_next_task_id": schedule["next_task_id"],
        "scheduler_next_task_title": schedule["next_task_title"],
        "scheduler_next_action": schedule["next_action"],
        "runtime_policy_dispatch_strategy": policy["dispatch_strategy"],
        "runtime_policy_max_total_estimated_cost": policy["max_total_estimated_cost"],
        "runtime_policy_max_single_execution_cost": policy["max_single_execution_cost"],
        "runtime_policy_block_on_unpriced_model": policy["block_on_unpriced_model"],
        "remaining_total_budget": policy["remaining_total_budget"],
        "today_open_tasks": today_open_tasks,
        "pending_takeover_count": takeover_count,
        **health,
    }


def project_summary(project: dict, host: str = DEFAULT_HOST) -> dict:
    root = Path(project["root"])
    runtime = instance_status(root, project["project_id"], host)
    initialized = aios_path(root).exists() if root.exists() else False
    runtime_data = project_runtime_data(root) if root.exists() else project_runtime_data(Path("/__missing__"))
    if not root.exists():
        runtime_data.update(
            project_health(
                {
                    "root_exists": False,
                    "initialized": False,
                    "file_count": 0,
                    "open_tasks": 0,
                    "active_execution_count": 0,
                    "ready_count": 0,
                    "blocked_count": 0,
                    "failed_count": 0,
                    "pending_takeover_count": 0,
                    "provider_ready_count": 0,
                    "available_executor_count": 0,
                }
            )
        )
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


def project_health(data: dict) -> dict:
    reasons: list[str] = []
    state = "healthy"
    label = "可生产"
    if not data.get("root_exists", True):
        return {
            "health_state": "broken",
            "health_label": "路径失效",
            "health_reasons": ["项目目录不存在"],
        }
    if not data.get("initialized"):
        state = "setup"
        label = "待初始化"
        reasons.append("尚未初始化 .aios")
    if data.get("pending_takeover_count", 0) > 0:
        state = "blocked"
        label = "需接管"
        reasons.append(f"{data['pending_takeover_count']} 个接管项")
    elif data.get("failed_count", 0) > 0:
        state = "blocked"
        label = "有失败"
        reasons.append(f"{data['failed_count']} 个失败任务")
    elif data.get("blocked_count", 0) > 0:
        state = "attention"
        label = "有阻塞"
        reasons.append(f"{data['blocked_count']} 个阻塞任务")
    if data.get("active_execution_count", 0) > 0:
        if state == "healthy":
            state = "active"
            label = "执行中"
        reasons.append(f"{data['active_execution_count']} 个执行中")
    if data.get("file_count", 0) == 0 and data.get("initialized"):
        if state == "healthy":
            state = "attention"
            label = "需扫描"
        reasons.append("尚无扫描索引")
    if data.get("open_tasks", 0) == 0 and data.get("initialized"):
        reasons.append("暂无未完成任务")
    if data.get("provider_ready_count", 0) == 0 and data.get("initialized"):
        if state in {"healthy", "active"}:
            state = "attention"
            label = "模型待检"
        reasons.append("暂无就绪模型")
    if data.get("available_executor_count", 0) == 0 and data.get("initialized"):
        if state in {"healthy", "active"}:
            state = "attention"
            label = "执行器待检"
        reasons.append("暂无可用执行器")
    return {
        "health_state": state,
        "health_label": label,
        "health_reasons": reasons[:4] or ["状态正常"],
    }


def production_project_candidates() -> list[dict]:
    registered_by_root = {project["root"]: project for project in load_projects()}
    candidates = []
    for item in PRODUCTION_PROJECTS:
        root = Path.home().joinpath(*item["path_parts"]).resolve()
        registered = registered_by_root.get(str(root))
        summary = project_summary(registered) if registered else None
        candidates.append(
            {
                **item,
                "root": str(root),
                "exists": root.exists(),
                "registered": registered is not None,
                "initialized": bool(summary["initialized"]) if summary else aios_path(root).exists(),
                "project_id": registered["project_id"] if registered else None,
                "health_state": summary["health_state"] if summary else ("setup" if root.exists() else "missing"),
                "health_label": summary["health_label"] if summary else ("待登记" if root.exists() else "未找到"),
                "open_tasks": summary["open_tasks"] if summary else 0,
                "ready_count": summary["ready_count"] if summary else 0,
            }
        )
    return candidates


def launcher_workbench_summary(host: str = DEFAULT_HOST) -> dict:
    projects = list_project_summaries(host)
    candidates = production_project_candidates()
    health_counts: dict[str, int] = {}
    actionable_ready: list[dict] = []
    pending_takeovers: list[dict] = []
    review_queue: list[dict] = []
    active_runs: list[dict] = []
    recent_activity: list[dict] = []
    for project in projects:
        key = project.get("health_state") or "unknown"
        health_counts[key] = health_counts.get(key, 0) + 1
        detail = project_workbench_detail(project)
        actionable_ready.extend(detail["actionable_ready"])
        pending_takeovers.extend(detail["pending_takeovers"])
        review_queue.extend(detail["review_queue"])
        active_runs.extend(detail["active_runs"])
        recent_activity.extend(detail["recent_activity"])
    focus_projects = sorted(
        projects,
        key=lambda project: (
            -(project.get("pending_takeover_count") or 0),
            -(project.get("failed_count") or 0),
            -(project.get("blocked_count") or 0),
            -(project.get("active_execution_count") or 0),
            -(project.get("ready_count") or 0),
            -(project.get("today_open_tasks") or 0),
        ),
    )[:5]
    actionable_ready = sorted(
        actionable_ready,
        key=lambda item: (
            PRIORITY_ORDER.get(str(item.get("priority") or "").lower(), 9),
            HEALTH_ORDER.get(str(item.get("project_health_state") or "").lower(), 9),
            -(item.get("estimated_total_cost") is not None),
            item.get("estimated_total_cost") or 0.0,
            item.get("updated_at") or "",
        ),
    )[:8]
    pending_takeovers = sorted(
        pending_takeovers,
        key=lambda item: (
            HEALTH_ORDER.get(str(item.get("project_health_state") or "").lower(), 9),
            item.get("created_at") or "",
        ),
        reverse=True,
    )[:8]
    review_queue = sorted(
        review_queue,
        key=lambda item: (
            PRIORITY_ORDER.get(str(item.get("priority") or "").lower(), 9),
            item.get("updated_at") or "",
        ),
        reverse=True,
    )[:8]
    active_runs = sorted(
        active_runs,
        key=lambda item: item.get("updated_at") or "",
        reverse=True,
    )[:8]
    recent_activity = sorted(
        recent_activity,
        key=lambda item: item.get("happened_at") or "",
        reverse=True,
    )[:10]
    infra_summary = build_infra_summary(projects)
    return {
        "generated_at": now_iso(),
        "project_count": len(projects),
        "registered_production_count": len([item for item in candidates if item["registered"]]),
        "production_candidate_count": len(candidates),
        "initialized_project_count": len([project for project in projects if project.get("initialized")]),
        "running_project_count": len([project for project in projects if project.get("running")]),
        "open_task_count": sum(int(project.get("open_tasks") or 0) for project in projects),
        "today_open_task_count": sum(int(project.get("today_open_tasks") or 0) for project in projects),
        "ready_task_count": sum(int(project.get("ready_count") or 0) for project in projects),
        "blocked_task_count": sum(int(project.get("blocked_count") or 0) for project in projects),
        "failed_task_count": sum(int(project.get("failed_count") or 0) for project in projects),
        "active_execution_count": sum(int(project.get("active_execution_count") or 0) for project in projects),
        "pending_takeover_count": sum(int(project.get("pending_takeover_count") or 0) for project in projects),
        "health_counts": health_counts,
        "focus_projects": focus_projects,
        "actionable_ready": actionable_ready,
        "pending_takeovers": pending_takeovers,
        "review_queue": review_queue,
        "active_runs": active_runs,
        "infra_summary": infra_summary,
        "recent_activity": recent_activity,
        "production_projects": candidates,
    }


def project_workbench_detail(project: dict) -> dict:
    root = Path(project["root"])
    if not root.exists() or not aios_path(root).exists():
        return {
            "actionable_ready": [],
            "pending_takeovers": [],
            "review_queue": [],
            "active_runs": [],
            "recent_activity": [],
        }

    tasks = {task["id"]: task for task in load_tasks(root)}
    schedule = scheduler_summary(root)
    takeover = takeover_summary(root)
    actionable_ready: list[dict] = []
    review_queue: list[dict] = []
    active_runs: list[dict] = []
    recent_activity: list[dict] = []

    for item in schedule.get("items", []):
        task = tasks.get(item["task_id"], {})
        execution = latest_execution_for_task(root, item["task_id"]) or {}
        entry = build_workbench_task_entry(project, task, item, execution)
        if item.get("scheduler_state") == "ready":
            actionable_ready.append(entry)
        elif item.get("scheduler_state") == "review_pending":
            review_queue.append(entry)
        elif item.get("scheduler_state") == "active":
            active_runs.append(entry)

    pending_takeovers = sorted(
        [
            {
                "project_id": project["project_id"],
                "project_name": project["name"],
                "project_root": project["root"],
                "project_url": project.get("url"),
                "project_health_state": project.get("health_state"),
                "project_health_label": project.get("health_label"),
                "takeover_id": entry.get("takeover_id"),
                "task_id": entry.get("task_id"),
                "task_title": entry.get("task_title"),
                "failure_category": entry.get("failure_category"),
                "reason": entry.get("reason"),
                "suggested_action": entry.get("suggested_action"),
                "created_at": entry.get("created_at"),
                "execution_id": entry.get("execution_id"),
            }
            for entry in takeover.get("latest_pending", [])
        ],
        key=lambda item: item.get("created_at") or "",
        reverse=True,
    )

    if project.get("last_execution_updated_at"):
        recent_activity.append(
            {
                "project_id": project["project_id"],
                "project_name": project["name"],
                "kind": "execution",
                "title": project.get("latest_task_title") or "最近执行更新",
                "detail": f"执行状态：{project.get('latest_execution_status') or '-'}",
                "happened_at": project["last_execution_updated_at"],
            }
        )
    if project.get("last_task_updated_at"):
        recent_activity.append(
            {
                "project_id": project["project_id"],
                "project_name": project["name"],
                "kind": "task",
                "title": project.get("latest_task_title") or "最近任务更新",
                "detail": f"下一步：{project.get('scheduler_next_action') or '-'}",
                "happened_at": project["last_task_updated_at"],
            }
        )
    if pending_takeovers:
        latest_takeover = pending_takeovers[0]
        recent_activity.append(
            {
                "project_id": project["project_id"],
                "project_name": project["name"],
                "kind": "takeover",
                "title": latest_takeover.get("task_title") or latest_takeover.get("task_id") or "待接管任务",
                "detail": latest_takeover.get("reason") or latest_takeover.get("suggested_action") or "需要人工接管",
                "happened_at": latest_takeover.get("created_at"),
            }
        )

    return {
        "actionable_ready": actionable_ready,
        "pending_takeovers": pending_takeovers,
        "review_queue": review_queue,
        "active_runs": active_runs,
        "recent_activity": recent_activity,
    }


def build_workbench_task_entry(project: dict, task: dict, scheduler_item: dict, execution: dict) -> dict:
    budget = scheduler_item.get("budget") or {}
    return {
        "project_id": project["project_id"],
        "project_name": project["name"],
        "project_root": project["root"],
        "project_url": project.get("url"),
        "project_health_state": project.get("health_state"),
        "project_health_label": project.get("health_label"),
        "task_id": scheduler_item.get("task_id"),
        "task_title": scheduler_item.get("task_title") or task.get("title"),
        "task_status": scheduler_item.get("task_status") or task.get("status"),
        "priority": task.get("priority") or "medium",
        "recommended_model": task.get("recommended_model"),
        "scheduler_state": scheduler_item.get("scheduler_state"),
        "next_action": scheduler_item.get("next_action"),
        "reason": scheduler_item.get("reason"),
        "updated_at": execution.get("updated_at") or task.get("updated_at") or task.get("created_at"),
        "created_at": task.get("created_at"),
        "execution_id": execution.get("execution_id"),
        "execution_status": execution.get("status"),
        "planned_model": execution.get("planned_model"),
        "actual_model": execution.get("actual_model"),
        "failure_category": execution.get("failure_category"),
        "failure_summary": execution.get("failure_summary"),
        "estimated_total_cost": budget.get("estimated_total_cost"),
        "cost_currency": budget.get("cost_currency") or execution.get("cost_currency") or "USD",
    }


def build_infra_summary(projects: list[dict]) -> dict:
    initialized_projects = [project for project in projects if project.get("initialized")]
    alerts = [
        {
            "key": "missing_roots",
            "label": "路径失效",
            "value": len([project for project in projects if not project.get("root_exists", True)]),
            "level": "danger",
            "detail": "目录被移动或删除，需重新定位。",
        },
        {
            "key": "waiting_setup",
            "label": "待初始化",
            "value": len([project for project in projects if project.get("health_state") == "setup"]),
            "level": "warning",
            "detail": "尚未建立 .aios 工作区。",
        },
        {
            "key": "missing_index",
            "label": "待扫描",
            "value": len([project for project in initialized_projects if int(project.get("file_count") or 0) == 0]),
            "level": "warning",
            "detail": "项目没有索引，无法形成可靠上下文。",
        },
        {
            "key": "model_not_ready",
            "label": "模型未就绪项目",
            "value": len([project for project in initialized_projects if int(project.get("provider_ready_count") or 0) == 0]),
            "level": "warning",
            "detail": "推荐模型缺少可用 provider 或鉴权。",
        },
        {
            "key": "executor_not_ready",
            "label": "执行器未就绪项目",
            "value": len([project for project in initialized_projects if int(project.get("available_executor_count") or 0) == 0]),
            "level": "warning",
            "detail": "本机没有可执行命令行执行器。",
        },
        {
            "key": "provider_handshake_failed",
            "label": "Provider 握手失败",
            "value": sum(int(project.get("provider_handshake_failed_count") or 0) for project in initialized_projects),
            "level": "danger",
            "detail": "网络可达性或 provider 地址配置异常。",
        },
        {
            "key": "provider_api_failed",
            "label": "API 权限失败",
            "value": sum(int(project.get("provider_api_failed_count") or 0) for project in initialized_projects),
            "level": "danger",
            "detail": "鉴权变量或账户权限不可用。",
        },
    ]
    return {
        "alerts": alerts,
        "running_projects": len([project for project in projects if project.get("running")]),
        "healthy_projects": len([project for project in projects if project.get("health_state") in {"healthy", "active"}]),
        "attention_projects": len([project for project in projects if project.get("health_state") in {"attention", "blocked", "broken", "setup"}]),
    }
