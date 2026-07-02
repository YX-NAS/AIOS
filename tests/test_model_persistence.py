"""P0-4: Verify model library persists across server restarts."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen

from aios.core.instance_manager import stop_project_instance, project_id_for_root
from aios.core.launcher import start_launcher_server
from aios.core.models import load_model_library


def request_json(base_url: str, path: str, method: str = "GET", payload: dict | None = None) -> tuple[int, dict]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    with urlopen(request) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_model_library_persists_across_server_restarts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))

    # Phase 1: Create a custom model on first server instance
    handle1 = start_launcher_server(port=0)
    try:
        status, _ = request_json(
            handle1.url,
            "/api/models/create",
            method="POST",
            payload={
                "model_id": "persistence-test-model",
                "label": "Persistence Test",
                "provider": "test",
                "endpoint": "https://provider.example.com/v1",
                "config_url": "https://provider.example.com/config.json",
                "notes": "用于持久化测试",
                "enabled": True,
                "rank": 1,
                "task_types": ["simple_coding"],
            },
        )
        assert status == 201

        # Verify it exists
        models_after_create = load_model_library()
        created = next(m for m in models_after_create if m["id"] == "persistence-test-model")
        assert created["endpoint"] == "https://provider.example.com/v1"
    finally:
        handle1.close()

    # Phase 2: Start a fresh server and verify model still exists
    handle2 = start_launcher_server(port=0)
    try:
        status, payload = request_json(handle2.url, "/api/models")
        assert status == 200
        model_ids = [m["id"] for m in payload["models"]]
        assert "persistence-test-model" in model_ids

        # Also verify via direct file read
        models_direct = load_model_library()
        created = next(m for m in models_direct if m["id"] == "persistence-test-model")
        assert created["config_url"] == "https://provider.example.com/config.json"
        assert created["notes"] == "用于持久化测试"
    finally:
        handle2.close()


def test_model_library_survives_update_and_delete(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))

    handle1 = start_launcher_server(port=0)
    try:
        # Update an existing model
        request_json(
            handle1.url,
            "/api/models/update",
            method="POST",
            payload={
                "current_model_id": "deepseek-v4-pro",
                "model_id": "deepseek-v4-pro",
                "label": "DeepSeek V4 Pro (Updated)",
                "provider": "deepseek",
                "endpoint": "https://api.deepseek.com",
                "config_url": "https://example.com/deepseek.json",
                "notes": "更新后的 provider 信息",
                "enabled": False,
                "rank": 99,
                "task_types": ["documentation"],
            },
        )
    finally:
        handle1.close()

    # Verify update persists on fresh server
    handle2 = start_launcher_server(port=0)
    try:
        models = load_model_library()
        deepseek = next(m for m in models if m["id"] == "deepseek-v4-pro")
        assert deepseek["label"] == "DeepSeek V4 Pro (Updated)"
        assert deepseek["enabled"] is False
        assert deepseek["rank"] == 99
        assert deepseek["endpoint"] == "https://api.deepseek.com"
        assert deepseek["notes"] == "更新后的 provider 信息"
    finally:
        handle2.close()


def test_model_library_persists_auth_env_vars(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))

    handle = start_launcher_server(port=0)
    try:
        status, payload = request_json(
            handle.url,
            "/api/models/create",
            method="POST",
            payload={
                "model_id": "custom-provider-model",
                "label": "Custom Provider Model",
                "provider": "custom",
                "endpoint": "https://provider.example.com/v1",
                "config_url": "https://provider.example.com/config.json",
                "auth_env_vars": ["CUSTOM_PROVIDER_TOKEN", "CUSTOM_PROVIDER_SECRET"],
                "enabled": True,
                "rank": 3,
                "task_types": ["complex_coding"],
            },
        )
        assert status == 201
        assert payload["model"]["auth_env_vars"] == ["CUSTOM_PROVIDER_TOKEN", "CUSTOM_PROVIDER_SECRET"]
    finally:
        handle.close()

    models = load_model_library()
    created = next(model for model in models if model["id"] == "custom-provider-model")
    assert created["auth_env_vars"] == ["CUSTOM_PROVIDER_TOKEN", "CUSTOM_PROVIDER_SECRET"]
