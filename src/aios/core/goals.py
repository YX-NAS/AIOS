from __future__ import annotations

from pathlib import Path

from aios.core.paths import require_aios
from aios.utils.json_utils import read_json, write_json
from aios.utils.text import now_iso, today


GOAL_STATUSES = {"active", "blocked", "done"}


def goals_path(root: Path) -> Path:
    return require_aios(root) / "goals.json"


def load_goals(root: Path) -> list[dict]:
    """Load goals without requiring old projects to be migrated first."""
    payload = read_json(goals_path(root), {"goals": []})
    goals = payload.get("goals")
    return goals if isinstance(goals, list) else []


def save_goals(root: Path, goals: list[dict]) -> None:
    write_json(goals_path(root), {"goals": goals})


def list_goals(root: Path) -> list[dict]:
    return sorted(
        load_goals(root),
        key=lambda item: (item.get("updated_at") or item.get("created_at") or "", item.get("goal_id") or ""),
        reverse=True,
    )


def get_goal(root: Path, goal_id: str) -> dict:
    for goal in load_goals(root):
        if goal.get("goal_id") == goal_id:
            return goal
    raise ValueError(f"Goal not found: {goal_id}")


def get_active_goal(root: Path) -> dict | None:
    candidates = [goal for goal in load_goals(root) if goal.get("status") in {"active", "blocked"}]
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item.get("updated_at") or item.get("created_at") or "", item.get("goal_id") or ""))


def create_goal(root: Path, title: str, priority: str = "high", summary: str | None = None) -> dict:
    title = str(title or "").strip()
    if not title:
        raise ValueError("Goal title is required.")
    active = get_active_goal(root)
    if active:
        raise ValueError(f"An active goal already exists: {active['goal_id']} {active['title']}")

    goals = load_goals(root)
    timestamp = now_iso()
    goal = {
        "goal_id": next_goal_id(goals),
        "title": title,
        "summary": str(summary or title).strip() or title,
        "status": "active",
        "priority": priority,
        "current_task_id": None,
        "root_task_ids": [],
        "created_from": "aios",
        "created_at": timestamp,
        "updated_at": timestamp,
        "finished_at": None,
        "blocked_reason": None,
    }
    goals.append(goal)
    save_goals(root, goals)
    return goal


def update_goal(root: Path, goal_id: str, updates: dict) -> dict:
    goals = load_goals(root)
    for goal in goals:
        if goal.get("goal_id") != goal_id:
            continue
        goal.update(updates)
        goal["updated_at"] = now_iso()
        if goal.get("status") == "done" and not goal.get("finished_at"):
            goal["finished_at"] = goal["updated_at"]
        if goal.get("status") != "done":
            goal["finished_at"] = None
        save_goals(root, goals)
        return goal
    raise ValueError(f"Goal not found: {goal_id}")


def update_goal_status(root: Path, goal_id: str, status: str, blocked_reason: str | None = None) -> dict:
    if status not in GOAL_STATUSES:
        raise ValueError(f"Unsupported goal status: {status}")
    updates = {"status": status, "blocked_reason": blocked_reason if status == "blocked" else None}
    return update_goal(root, goal_id, updates)


def activate_goal(root: Path, goal_id: str) -> dict:
    active = get_active_goal(root)
    if active and active.get("goal_id") != goal_id:
        raise ValueError(f"An active goal already exists: {active['goal_id']} {active['title']}")
    goal = get_goal(root, goal_id)
    if goal.get("status") == "done":
        raise ValueError("A completed goal cannot be reactivated.")
    return update_goal_status(root, goal_id, "active")


def next_goal_id(goals: list[dict]) -> str:
    prefix = f"GOAL-{today().replace('-', '')}-"
    existing_numbers = []
    for goal in goals:
        goal_id = str(goal.get("goal_id") or "")
        if not goal_id.startswith(prefix):
            continue
        try:
            existing_numbers.append(int(goal_id.rsplit("-", 1)[-1]))
        except ValueError:
            continue
    return f"{prefix}{max(existing_numbers, default=0) + 1:03d}"
