from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen

from aios.core.executions import latest_execution_for_task, load_executions
from aios.core.instance_manager import project_id_for_root, stop_project_instance
from aios.core.launcher import start_launcher_server
from aios.core.webapp import start_web_server
from aios.main import main


def request_json(base_url: str, path: str, method: str = "GET", payload: dict | None = None) -> tuple[int, dict]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    with urlopen(request) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_run_manual_cli_creates_and_finishes_execution(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    (tmp_path / "main.py").write_text("print('demo')\n", encoding="utf-8")
    main(["--root", str(tmp_path), "scan"])
    main(["--root", str(tmp_path), "task", "create", "实现登录功能", "--priority", "high"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]

    assert main(["--root", str(tmp_path), "run", "--manual", task["id"], "--start"]) == 0

    execution = latest_execution_for_task(tmp_path, task["id"])
    assert execution is not None
    assert execution["status"] == "running"
    assert execution["planned_model"] == task["recommended_model"]

    assert main(
        [
            "--root",
            str(tmp_path),
            "run",
            "finish",
            task["id"],
            "--summary",
            "完成登录功能",
            "--actual-model",
            "gpt-5.5",
            "--test-command",
            "pytest -q",
            "--test-result",
            "passed",
            "--score",
            "4",
        ]
    ) == 0

    execution = latest_execution_for_task(tmp_path, task["id"])
    assert execution is not None
    assert execution["status"] == "finished"
    assert execution["actual_model"] == "gpt-5.5"
    assert execution["test_command"] == "pytest -q"
    updated_task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    assert updated_task["status"] == "done"


def test_run_manual_api_returns_latest_execution(tmp_path: Path) -> None:
    handle = start_web_server(tmp_path, port=0)
    try:
        request_json(handle.url, "/api/init", method="POST", payload={"name": "demo", "type": "web-app"})
        request_json(handle.url, "/api/tasks", method="POST", payload={"title": "修复登录报错", "priority": "high"})
        task_id = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]["id"]

        status_code, start_payload = request_json(
            handle.url,
            "/api/run/manual",
            method="POST",
            payload={"task_id": task_id, "start": True},
        )
        assert status_code == 201
        assert start_payload["execution"]["status"] == "running"
        assert start_payload["handoff"]["handoff_path"].endswith("-handoff.md")

        status_code, execution_payload = request_json(handle.url, f"/api/run/task/{task_id}")
        assert status_code == 200
        assert execution_payload["execution"]["task_id"] == task_id

        status_code, finish_payload = request_json(
            handle.url,
            "/api/run/finish",
            method="POST",
            payload={
                "task_id": task_id,
                "summary": "修复完成",
                "actual_model": "claude",
                "test_command": "pytest -q",
                "test_result": "all passed",
            },
        )
        assert status_code == 200
        assert finish_payload["task"]["status"] == "done"
        assert finish_payload["execution"]["status"] == "finished"
    finally:
        handle.close()


def test_execution_summary_is_visible_in_launcher_project_status(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    project = tmp_path / "workspace" / "alpha"
    project.mkdir(parents=True)
    main(["--root", str(project), "init", "--name", "alpha", "--type", "web-app"])
    main(["--root", str(project), "task", "create", "实现登录功能", "--priority", "high"])
    task_id = json.loads((project / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]["id"]
    main(["--root", str(project), "run", "--manual", task_id, "--start"])

    handle = start_launcher_server(port=0)
    try:
        status_code, created_payload = request_json(
            handle.url,
            "/api/projects",
            method="POST",
            payload={"root": str(project), "name": "Alpha"},
        )
        assert status_code == 201
        project_id = created_payload["project"]["project_id"]
        assert created_payload["project"]["active_execution_count"] == 1
        assert created_payload["project"]["latest_execution_status"] == "running"

        main(["--root", str(project), "run", "finish", task_id, "--summary", "完成登录功能"])

        status_code, status_payload = request_json(handle.url, f"/api/projects/{project_id}/status")
        assert status_code == 200
        assert status_payload["project"]["active_execution_count"] == 0
        assert status_payload["project"]["latest_execution_status"] == "finished"
    finally:
        stop_project_instance(project_id_for_root(project))
        handle.close()


def test_loading_executions_without_file_returns_empty_after_init(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    (tmp_path / ".aios" / "executions.json").unlink()
    assert load_executions(tmp_path) == []


def test_ccswitch_export_cli_writes_auditable_json(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    main(["--root", str(tmp_path), "task", "create", "实现登录功能", "--priority", "high"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    main(["--root", str(tmp_path), "run", "--manual", task["id"], "--start"])

    assert main(["--root", str(tmp_path), "ccswitch", "export", task["id"], "--model", "claude"]) == 0

    execution = latest_execution_for_task(tmp_path, task["id"])
    assert execution is not None
    assert execution["ccswitch_export_model"] == "claude"
    export_path = tmp_path / execution["ccswitch_export_path"]
    assert export_path.exists()
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert payload["task_id"] == task["id"]
    assert payload["execution_id"] == execution["execution_id"]
    assert payload["planned_model"] == task["recommended_model"]
    assert payload["export_model"] == "claude"


def test_ccswitch_export_cli_stdout_outputs_json(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    main(["--root", str(tmp_path), "task", "create", "实现登录功能", "--priority", "high"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    main(["--root", str(tmp_path), "run", "--manual", task["id"], "--start"])

    assert main(["--root", str(tmp_path), "ccswitch", "export", task["id"], "--stdout"]) == 0
    output = capsys.readouterr().out
    assert '"task_id"' in output
    assert '"export_model"' in output


def test_ccswitch_export_api_updates_execution_without_overwriting_planned_model(tmp_path: Path) -> None:
    handle = start_web_server(tmp_path, port=0)
    try:
        request_json(handle.url, "/api/init", method="POST", payload={"name": "demo", "type": "web-app"})
        request_json(handle.url, "/api/tasks", method="POST", payload={"title": "修复登录报错", "priority": "high"})
        task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
        request_json(handle.url, "/api/run/manual", method="POST", payload={"task_id": task["id"], "start": True})

        status_code, export_payload = request_json(
            handle.url,
            "/api/ccswitch/export",
            method="POST",
            payload={"task_id": task["id"], "model": "claude"},
        )
        assert status_code == 201
        assert export_payload["payload"]["export_model"] == "claude"
        assert export_payload["payload"]["planned_model"] == task["recommended_model"]
        assert export_payload["execution"]["planned_model"] == task["recommended_model"]
        assert export_payload["execution"]["ccswitch_export_model"] == "claude"
        assert (tmp_path / export_payload["export_path"]).exists()
    finally:
        handle.close()


def test_ccswitch_export_requires_execution_record(tmp_path: Path) -> None:
    handle = start_web_server(tmp_path, port=0)
    try:
        request_json(handle.url, "/api/init", method="POST", payload={"name": "demo", "type": "web-app"})
        request_json(handle.url, "/api/tasks", method="POST", payload={"title": "修复登录报错", "priority": "high"})
        task_id = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]["id"]

        request = Request(
            f"{handle.url}/api/ccswitch/export",
            data=json.dumps({"task_id": task_id}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urlopen(request)
            raise AssertionError("Expected export without execution to fail")
        except Exception as exc:  # noqa: BLE001
            assert "run --manual" in str(exc) or "HTTP Error 400" in str(exc)
    finally:
        handle.close()
