from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen

from aios.core.goals import get_goal
from aios.core.progress import create_goal_with_plan, select_current_task
from aios.core.executions import finish_manual_execution
from aios.core.projects import project_runtime_data
from aios.core.webapp import start_web_server
from aios.core.launcher import start_launcher_server
from aios.main import main


def request_json(base_url: str, path: str, method: str = "GET", payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    with urlopen(Request(f"{base_url}{path}", data=data, headers=headers, method=method)) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_goal_creates_bound_task_tree_and_advances_after_completion(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    main(["--root", str(tmp_path), "init", "--name", "demo"])

    created = create_goal_with_plan(tmp_path, "开发会员积分系统")
    goal = created["goal"]
    tasks = created["tasks"]
    assert goal["status"] == "active"
    assert len(tasks) >= 4
    assert all(task["goal_id"] == goal["goal_id"] for task in tasks)
    assert created["progress"]["current_task"]["id"] == tasks[0]["id"]

    finish_manual_execution(tmp_path, tasks[0]["id"], "范围已经确认")
    advanced_goal = get_goal(tmp_path, goal["goal_id"])
    assert advanced_goal["current_task_id"] == tasks[1]["id"]
    assert advanced_goal["status"] == "active"


def test_current_task_selector_prioritizes_active_review_then_ready() -> None:
    tasks = [
        {"id": "ready", "priority": "high", "sequence_order": 1},
        {"id": "review", "priority": "low", "sequence_order": 3},
        {"id": "active", "priority": "low", "sequence_order": 4},
    ]
    items = {
        "ready": {"task_id": "ready", "scheduler_state": "ready"},
        "review": {"task_id": "review", "scheduler_state": "review_pending"},
        "active": {"task_id": "active", "scheduler_state": "active"},
    }
    assert select_current_task(tasks, items)["task_id"] == "active"
    del items["active"]
    assert select_current_task(tasks, items)["task_id"] == "review"
    del items["review"]
    assert select_current_task(tasks, items)["task_id"] == "ready"


def test_goal_and_progress_api_return_current_action(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    handle = start_web_server(tmp_path, port=0)
    try:
        request_json(handle.url, "/api/init", method="POST", payload={"name": "demo"})
        status, created = request_json(
            handle.url,
            "/api/goals",
            method="POST",
            payload={"goal": "开发会员积分系统", "priority": "high"},
        )
        assert status == 201
        assert created["goal"]["goal_id"].startswith("GOAL-")
        assert created["progress"]["current_task"] is not None

        status, progress = request_json(handle.url, "/api/progress/current")
        assert status == 200
        assert progress["goal"]["goal_id"] == created["goal"]["goal_id"]
        assert progress["current_task"]["goal_id"] == created["goal"]["goal_id"]
        assert progress["next_action"] == "run_executor"

        status, goals = request_json(handle.url, "/api/goals")
        assert status == 200
        assert goals["goals"][0]["goal_id"] == created["goal"]["goal_id"]
    finally:
        handle.close()


def test_project_summary_contains_goal_progress(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    created = create_goal_with_plan(tmp_path, "开发会员积分系统")

    summary = project_runtime_data(tmp_path)
    assert summary["current_goal_title"] == "开发会员积分系统"
    assert summary["current_task_id"] == created["progress"]["current_task"]["id"]
    assert summary["progress_percent"] == 0


def test_goal_becomes_done_when_all_bound_tasks_finish(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    created = create_goal_with_plan(tmp_path, "开发会员积分系统")

    for task in created["tasks"]:
        finish_manual_execution(tmp_path, task["id"], f"完成 {task['id']}")

    goal = get_goal(tmp_path, created["goal"]["goal_id"])
    assert goal["status"] == "done"
    assert goal["current_task_id"] is None


def test_launcher_api_exposes_project_goal_progress(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    project = tmp_path / "project"
    project.mkdir()
    main(["--root", str(project), "init", "--name", "demo"])
    create_goal_with_plan(project, "开发会员积分系统")
    launcher = start_launcher_server(port=0)
    try:
        status, registered = request_json(
            launcher.url,
            "/api/projects",
            method="POST",
            payload={"root": str(project), "name": "Demo"},
        )
        assert status == 201
        project_summary = registered["project"]
        assert project_summary["current_goal_title"] == "开发会员积分系统"
        assert project_summary["current_task_title"]
        assert project_summary["progress_percent"] == 0
        assert project_summary["progress_next_action"] == "run_executor"
    finally:
        launcher.close()
