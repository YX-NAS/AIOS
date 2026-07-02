from __future__ import annotations

import json
import shutil
from pathlib import Path
from urllib.request import Request, urlopen

from aios.core.instance_manager import project_id_for_root, stop_project_instance
from aios.core.models import load_model_library
from aios.core.launcher import start_launcher_server
from aios.core.projects import load_projects, register_project
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


def test_project_registry_supports_same_named_directories(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    project_a = tmp_path / "group-a" / "demo"
    project_b = tmp_path / "group-b" / "demo"
    project_a.mkdir(parents=True)
    project_b.mkdir(parents=True)

    record_a = register_project(project_a)
    record_b = register_project(project_b)

    assert record_a["project_id"] != record_b["project_id"]
    projects = load_projects()
    assert len(projects) == 2
    assert {project["root"] for project in projects} == {str(project_a.resolve()), str(project_b.resolve())}


def test_launcher_api_manages_multiple_projects(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    project_a = tmp_path / "team-one" / "demo"
    project_b = tmp_path / "team-two" / "demo"
    project_a.mkdir(parents=True)
    project_b.mkdir(parents=True)

    handle = start_launcher_server(port=0)
    try:
        status_code, payload_a = request_json(
            handle.url,
            "/api/projects",
            method="POST",
            payload={"root": str(project_a)},
        )
        assert status_code == 201
        project_id_a = payload_a["project"]["project_id"]

        status_code, payload_b = request_json(
            handle.url,
            "/api/projects",
            method="POST",
            payload={"root": str(project_b)},
        )
        assert status_code == 201
        project_id_b = payload_b["project"]["project_id"]
        assert project_id_a != project_id_b

        status_code, list_payload = request_json(handle.url, "/api/projects")
        assert status_code == 200
        assert len(list_payload["projects"]) == 2

        status_code, open_a = request_json(
            handle.url,
            "/api/projects/open",
            method="POST",
            payload={"project_id": project_id_a},
        )
        assert status_code == 200
        assert open_a["project"]["status"] == "running"
        assert open_a["url"].startswith("http://127.0.0.1:")

        status_code, open_b = request_json(
            handle.url,
            "/api/projects/open",
            method="POST",
            payload={"project_id": project_id_b},
        )
        assert status_code == 200
        assert open_b["project"]["status"] == "running"
        assert open_b["url"].startswith("http://127.0.0.1:")
        assert open_a["url"] != open_b["url"]

        status_code, project_b_status = request_json(handle.url, f"/api/projects/{project_id_b}/status")
        assert status_code == 200
        assert project_b_status["project"]["running"] is True

        status_code, stop_payload = request_json(
            handle.url,
            "/api/projects/stop",
            method="POST",
            payload={"project_id": project_id_a},
        )
        assert status_code == 200
        assert stop_payload["project"]["status"] == "stopped"

        shutil.rmtree(project_b)
        status_code, missing_payload = request_json(handle.url, f"/api/projects/{project_id_b}/status")
        assert status_code == 200
        assert missing_payload["project"]["status"] == "missing"
    finally:
        stop_project_instance(project_id_for_root(project_a))
        stop_project_instance(project_id_for_root(project_b))
        handle.close()


def test_launcher_project_summary_reflects_project_data_and_scan(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    project = tmp_path / "workspace" / "alpha"
    project.mkdir(parents=True)
    main(["--root", str(project), "init", "--name", "alpha", "--type", "web-app"])
    (project / "main.py").write_text("print('alpha')\n", encoding="utf-8")
    main(["--root", str(project), "task", "create", "实现登录功能", "--priority", "high"])

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
        assert created_payload["project"]["task_count"] == 1
        assert created_payload["project"]["open_tasks"] == 1
        assert created_payload["project"]["latest_task_title"] == "实现登录功能"
        assert created_payload["project"]["enabled_model_count"] >= 1

        status_code, scan_payload = request_json(
            handle.url,
            "/api/projects/scan",
            method="POST",
            payload={"project_id": project_id},
        )
        assert status_code == 200
        assert scan_payload["project"]["file_count"] >= 1
        assert "python" in scan_payload["project"]["languages"]

        status_code, status_payload = request_json(handle.url, f"/api/projects/{project_id}/status")
        assert status_code == 200
        assert status_payload["project"]["name"] == "Alpha"
        assert status_payload["project"]["initialized"] is True
        assert status_payload["project"]["task_count"] == 1
    finally:
        stop_project_instance(project_id_for_root(project))
        handle.close()


def test_launcher_global_model_library_api(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))

    handle = start_launcher_server(port=0)
    try:
        status_code, models_payload = request_json(handle.url, "/api/models")
        assert status_code == 200
        assert models_payload["enabled_model_count"] >= 1
        assert any(model["id"] == "deepseek-v4-pro" for model in models_payload["models"])

        status_code, created_model_payload = request_json(
            handle.url,
            "/api/models/create",
            method="POST",
            payload={
                "model_id": "gpt-5.5-coder",
                "label": "GPT 5.5 Coder",
                "provider": "openai",
                "endpoint": "https://api.openai.com/v1",
                "config_url": "https://example.com/openai-config.json",
                "notes": "需要本地路由",
                "enabled": True,
                "rank": 2,
                "task_types": ["complex_coding", "bug_fix"],
            },
        )
        assert status_code == 201
        assert created_model_payload["model"]["id"] == "gpt-5.5-coder"
        assert created_model_payload["model"]["endpoint"] == "https://api.openai.com/v1"

        status_code, updated_model_payload = request_json(
            handle.url,
            "/api/models/update",
            method="POST",
            payload={
                "current_model_id": "claude",
                "model_id": "claude-sonnet",
                "label": "Claude Sonnet",
                "provider": "anthropic",
                "endpoint": "https://api.anthropic.com",
                "config_url": "https://example.com/claude.json",
                "notes": "需要登录态",
                "enabled": True,
                "rank": 1,
                "task_types": ["bug_fix"],
            },
        )
        assert status_code == 200
        assert updated_model_payload["model"]["id"] == "claude-sonnet"
        assert updated_model_payload["model"]["rank"] == 1

        models = load_model_library()
        claude = next(model for model in models if model["id"] == "claude-sonnet")
        assert claude["task_types"] == ["bug_fix"]
        assert claude["rank"] == 1
        assert claude["endpoint"] == "https://api.anthropic.com"
        assert claude["notes"] == "需要登录态"

        status_code, deleted_model_payload = request_json(
            handle.url,
            "/api/models/delete",
            method="POST",
            payload={"model_id": "gpt-5.5-coder"},
        )
        assert status_code == 200
        assert all(model["id"] != "gpt-5.5-coder" for model in deleted_model_payload["models"])

        status_code, reset_payload = request_json(handle.url, "/api/models/reset", method="POST", payload={})
        assert status_code == 200
        assert any(model["id"] == "claude" for model in reset_payload["models"])
        assert all(model["id"] != "claude-sonnet" for model in reset_payload["models"])
    finally:
        handle.close()
