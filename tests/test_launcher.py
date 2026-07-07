from __future__ import annotations

import json
import shutil
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import aios.core.models as models_core
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


def test_launcher_folder_picker_api_returns_selected_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    selected_root = tmp_path / "picked-project"
    selected_root.mkdir()
    monkeypatch.setattr("aios.core.launcher.pick_project_directory", lambda: str(selected_root))

    handle = start_launcher_server(port=0)
    try:
        status_code, payload = request_json(
            handle.url,
            "/api/projects/pick-folder",
            method="POST",
            payload={},
        )
        assert status_code == 200
        assert payload["root"] == str(selected_root)
    finally:
        handle.close()


def test_launcher_project_summary_reflects_project_data_and_scan(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
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
        assert created_payload["project"]["provider_ready_count"] >= 1

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
        assert status_payload["project"]["health_state"] in {"attention", "healthy"}
        assert status_payload["project"]["health_label"]
        assert status_payload["project"]["today_open_tasks"] == 1
    finally:
        stop_project_instance(project_id_for_root(project))
        handle.close()


def test_launcher_workbench_summary_and_production_project_checklist(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    production_root = fake_home / "SynologyDrive" / "日常工作" / "Github" / "AIOS"
    production_root.mkdir(parents=True)
    main(["--root", str(production_root), "init", "--name", "AIOS", "--type", "tool"])
    main(["--root", str(production_root), "task", "create", "完善今日工作台", "--priority", "high"])

    handle = start_launcher_server(port=0)
    try:
        status_code, created_payload = request_json(
            handle.url,
            "/api/projects",
            method="POST",
            payload={"root": str(production_root), "name": "AIOS"},
        )
        assert status_code == 201
        assert created_payload["project"]["health_label"]

        status_code, workbench_payload = request_json(handle.url, "/api/workbench")
        assert status_code == 200
        workbench = workbench_payload["workbench"]
        assert workbench["project_count"] == 1
        assert workbench["registered_production_count"] == 1
        assert workbench["production_candidate_count"] >= 5
        assert workbench["open_task_count"] == 1
        assert workbench["today_open_task_count"] == 1
        assert workbench["focus_projects"][0]["name"] == "AIOS"

        status_code, checklist_payload = request_json(handle.url, "/api/production-projects")
        assert status_code == 200
        aios_item = next(item for item in checklist_payload["projects"] if item["key"] == "aios")
        assert aios_item["exists"] is True
        assert aios_item["registered"] is True
        assert aios_item["initialized"] is True
        assert aios_item["open_tasks"] == 1
    finally:
        stop_project_instance(project_id_for_root(production_root))
        handle.close()


def test_launcher_global_model_library_api(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")

    handle = start_launcher_server(port=0)
    try:
        status_code, models_payload = request_json(handle.url, "/api/models")
        assert status_code == 200
        assert models_payload["enabled_model_count"] >= 1
        assert models_payload["provider_ready_count"] >= 1
        assert any(model["id"] == "deepseek-v4-pro" for model in models_payload["models"])
        gpt_model = next(model for model in models_payload["models"] if model["id"] == "gpt-5.5")
        assert gpt_model["runtime"]["auth_status"] == "ready"
        assert gpt_model["runtime"]["ready"] is True

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
                "auth_env_vars": ["OPENAI_API_KEY"],
                "input_cost_per_1m": 2.5,
                "output_cost_per_1m": 10.0,
                "cost_currency": "USD",
                "notes": "需要本地路由",
                "enabled": True,
                "rank": 2,
                "task_types": ["complex_coding", "bug_fix"],
            },
        )
        assert status_code == 201
        assert created_model_payload["model"]["id"] == "gpt-5.5-coder"
        assert created_model_payload["model"]["endpoint"] == "https://api.openai.com/v1"
        assert created_model_payload["model"]["auth_env_vars"] == ["OPENAI_API_KEY"]
        assert created_model_payload["model"]["input_cost_per_1m"] == 2.5

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
                "auth_env_vars": ["ANTHROPIC_API_KEY", "CLAUDE_CODE_TOKEN"],
                "input_cost_per_1m": 3.0,
                "output_cost_per_1m": 15.0,
                "cost_currency": "USD",
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
        assert claude["auth_env_vars"] == ["ANTHROPIC_API_KEY", "CLAUDE_CODE_TOKEN"]
        assert claude["input_cost_per_1m"] == 3.0
        assert claude["output_cost_per_1m"] == 15.0

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


def test_launcher_model_probe_api_updates_runtime_handshake(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")

    def fake_urlopen(request, timeout=3.0):
        raise URLError("connection refused")

    monkeypatch.setattr(models_core, "urlopen", fake_urlopen)

    handle = start_launcher_server(port=0)
    try:
        status_code, probe_payload = request_json(
            handle.url,
            "/api/models/probe",
            method="POST",
            payload={"model_id": "gpt-5.5", "timeout": 1.0},
        )
        assert status_code == 200
        result = probe_payload["results"][0]
        assert result["model_id"] == "gpt-5.5"
        assert result["status"] == "failed"
        model = next(item for item in probe_payload["models"] if item["id"] == "gpt-5.5")
        assert model["runtime"]["handshake_status"] == "failed"
        assert model["runtime"]["ready"] is False
    finally:
        handle.close()


def test_launcher_model_probe_api_surfaces_provider_auth_probe(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")

    class FakeResponse:
        def __init__(self, status: int):
            self.status = status

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(request, timeout=3.0):
        if request.full_url.endswith("/models"):
            return FakeResponse(200)
        return FakeResponse(401)

    monkeypatch.setattr(models_core, "urlopen", fake_urlopen)

    handle = start_launcher_server(port=0)
    try:
        status_code, probe_payload = request_json(
            handle.url,
            "/api/models/probe",
            method="POST",
            payload={"model_id": "gpt-5.5", "timeout": 1.0},
        )
        assert status_code == 200
        result = probe_payload["results"][0]
        assert result["auth_probe_status"] == "ok"
        assert result["auth_probe_http_status"] == 200
        assert probe_payload["provider_api_verified_count"] >= 1
        model = next(item for item in probe_payload["models"] if item["id"] == "gpt-5.5")
        assert model["runtime"]["auth_probe_status"] == "ok"
        assert model["runtime"]["ready"] is True
    finally:
        handle.close()
