"""P1 feature tests: task filtering, routing log, model persistence."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from aios.core.webapp import start_web_server
from aios.main import main


def request_json(base_url: str, path: str, method: str = "GET", payload: dict | None = None) -> tuple[int, dict]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = json.loads(exc.read().decode("utf-8"))
        return exc.code, body


# ---- P1-2: Task status filter (API returns tasks with status field) ----


def test_api_tasks_return_status_field(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    handle = start_web_server(tmp_path, port=0)
    try:
        request_json(handle.url, "/api/tasks", method="POST", payload={"title": "task A", "priority": "high"})
        request_json(handle.url, "/api/tasks", method="POST", payload={"title": "task B", "priority": "medium"})
        status, payload = request_json(handle.url, "/api/tasks")
        assert status == 200
        tasks = payload["tasks"]
        assert len(tasks) == 2
        assert tasks[0]["status"] == "todo"
        assert tasks[1]["status"] == "todo"
    finally:
        handle.close()


def test_api_tasks_mixed_statuses(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    handle = start_web_server(tmp_path, port=0)
    try:
        _, created_a = request_json(handle.url, "/api/tasks", method="POST", payload={"title": "task A"})
        _, created_b = request_json(handle.url, "/api/tasks", method="POST", payload={"title": "task B"})
        task_a_id = created_a["task"]["id"]

        request_json(handle.url, "/api/complete", method="POST", payload={"task_id": task_a_id, "summary": "done"})

        _, payload = request_json(handle.url, "/api/tasks")
        tasks = payload["tasks"]
        done_tasks = [t for t in tasks if t["status"] == "done"]
        todo_tasks = [t for t in tasks if t["status"] == "todo"]
        assert len(done_tasks) == 1
        assert len(todo_tasks) == 1
        assert done_tasks[0]["id"] == task_a_id
    finally:
        handle.close()


# ---- P1-3: Routing log ----


def test_route_writes_routing_log(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    main(["--root", str(tmp_path), "task", "create", "实现登录功能", "--priority", "high"])
    tasks = json.loads((tmp_path / ".aios" / "tasks.json").read_text())["tasks"]
    task_id = tasks[0]["id"]

    exit_code = main(["--root", str(tmp_path), "route", task_id])
    assert exit_code == 0

    log_path = tmp_path / ".aios" / "routing-log.json"
    assert log_path.exists(), "routing-log.json should be created after route command"

    log = json.loads(log_path.read_text())
    assert isinstance(log, list)
    assert len(log) >= 1
    entry = log[-1]
    assert entry["task_id"] == task_id
    assert entry["recommended_model"]
    assert "reason" in entry
    assert "routed_at" in entry


def test_route_appends_to_routing_log(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    main(["--root", str(tmp_path), "task", "create", "task one", "--priority", "high"])
    main(["--root", str(tmp_path), "task", "create", "task two", "--priority", "medium"])
    tasks = json.loads((tmp_path / ".aios" / "tasks.json").read_text())["tasks"]

    main(["--root", str(tmp_path), "route", tasks[0]["id"]])
    main(["--root", str(tmp_path), "route", tasks[1]["id"]])

    log = json.loads((tmp_path / ".aios" / "routing-log.json").read_text())
    assert len(log) == 2
    assert log[0]["task_id"] != log[1]["task_id"]


def test_api_route_also_writes_routing_log(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    handle = start_web_server(tmp_path, port=0)
    try:
        _, task_payload = request_json(handle.url, "/api/tasks", method="POST", payload={"title": "test route log"})
        task_id = task_payload["task"]["id"]

        request_json(handle.url, f"/api/route/{task_id}")

        log_path = tmp_path / ".aios" / "routing-log.json"
        assert log_path.exists()
        log = json.loads(log_path.read_text())
        assert any(entry["task_id"] == task_id for entry in log)
    finally:
        handle.close()


# ---- P1-4: Plan preview + confirm ----


def test_api_plan_default_is_preview(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    handle = start_web_server(tmp_path, port=0)
    try:
        # Plan without confirm -> preview only, tasks not created
        status, payload = request_json(
            handle.url,
            "/api/tasks/plan",
            method="POST",
            payload={"goal": "实现登录功能", "priority": "high"},
        )
        assert status == 201
        assert len(payload["tasks"]) >= 2

        # Tasks should NOT be in the task list yet
        _, tasks_payload = request_json(handle.url, "/api/tasks")
        assert len(tasks_payload["tasks"]) == 0
    finally:
        handle.close()


def test_api_plan_with_confirm_creates_tasks(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    handle = start_web_server(tmp_path, port=0)
    try:
        # Plan with confirm -> tasks created
        status, payload = request_json(
            handle.url,
            "/api/tasks/plan",
            method="POST",
            payload={"goal": "实现登录功能", "priority": "high", "confirm": True},
        )
        assert status == 201
        assert len(payload["tasks"]) >= 2

        # Tasks should now be in the task list
        _, tasks_payload = request_json(handle.url, "/api/tasks")
        assert len(tasks_payload["tasks"]) >= 2
    finally:
        handle.close()


def test_api_plan_preview_then_confirm(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    handle = start_web_server(tmp_path, port=0)
    try:
        # Step 1: preview
        _, preview = request_json(
            handle.url,
            "/api/tasks/plan",
            method="POST",
            payload={"goal": "实现登录功能", "priority": "high"},
        )
        assert len(preview["tasks"]) >= 2

        # Still no tasks
        _, tasks_payload = request_json(handle.url, "/api/tasks")
        assert len(tasks_payload["tasks"]) == 0

        # Step 2: confirm with same params
        _, confirmed = request_json(
            handle.url,
            "/api/tasks/plan",
            method="POST",
            payload={"goal": "实现登录功能", "priority": "high", "confirm": True},
        )
        assert len(confirmed["tasks"]) >= 2

        # Now tasks exist
        _, tasks_payload = request_json(handle.url, "/api/tasks")
        assert len(tasks_payload["tasks"]) >= 2
    finally:
        handle.close()
