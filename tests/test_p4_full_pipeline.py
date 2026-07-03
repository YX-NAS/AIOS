"""P4-2 / P4-3 tests: full pipeline + takeover queue."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock as unit_mock

from aios.main import main
from aios.core.pipeline import run_full_pipeline
from aios.core.takeover import (
    enqueue_takeover,
    load_takeover_queue,
    resolve_takeover,
    should_takeover,
    pending_takeover_count,
    takeover_suggested_action,
    takeover_summary,
)
from aios.core.executors import create_executor
from aios.core.models import create_model
from aios.core.scheduler import scheduler_summary
from aios.core.webapp import start_web_server
from tests.test_error_handling import request_json


# ── takeover queue ────────────────────────────────────────────────

def test_enqueue_and_resolve_takeover(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    (tmp_path / ".aios" / "context.md").write_text("# Context\n\nTest.\n", encoding="utf-8")
    (tmp_path / ".aios" / "architecture.md").write_text("# Arch\n\nTest.\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("print('ok')\n", encoding="utf-8")
    main(["--root", str(tmp_path), "scan"])
    main(["--root", str(tmp_path), "task", "create", "Fix critical bug", "--priority", "high"])

    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]

    entry = enqueue_takeover(tmp_path, task["id"], "Provider auth failed", failure_category="provider_auth_blocked")
    assert entry["status"] == "pending"
    assert entry["failure_category"] == "provider_auth_blocked"
    assert pending_takeover_count(tmp_path) == 1

    resolved = resolve_takeover(tmp_path, entry["takeover_id"], "Updated API key")
    assert resolved is not None
    assert resolved["status"] == "resolved"
    assert pending_takeover_count(tmp_path) == 0


def test_takeover_summary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    (tmp_path / ".aios" / "context.md").write_text("# Context\n\nTest.\n", encoding="utf-8")
    (tmp_path / ".aios" / "architecture.md").write_text("# Arch\n\nTest.\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("print('ok')\n", encoding="utf-8")
    main(["--root", str(tmp_path), "scan"])
    main(["--root", str(tmp_path), "task", "create", "Task A", "--priority", "high"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]

    enqueue_takeover(tmp_path, task["id"], "Network timeout", failure_category="network_timeout")
    enqueue_takeover(tmp_path, task["id"], "Missing binary", failure_category="missing_binary")

    summary = takeover_summary(tmp_path)
    assert summary["pending"] == 2
    assert summary["total"] == 2
    assert len(summary["latest_pending"]) == 2


def test_should_takeover_categories() -> None:
    assert should_takeover("provider_auth_blocked", 0, 3) is True
    assert should_takeover("missing_binary", 0, 3) is True
    assert should_takeover("permission_denied", 0, 3) is True
    assert should_takeover("verification_failed", 0, 3) is False
    assert should_takeover("verification_failed", 3, 3) is True
    assert should_takeover(None, 3, 3) is True


def test_takeover_suggested_action() -> None:
    assert "API 密钥" in takeover_suggested_action("provider_auth_blocked")
    assert "CLI" in takeover_suggested_action("missing_binary")
    assert "权限" in takeover_suggested_action("permission_denied")
    assert "人工" in takeover_suggested_action("unknown")


def test_takeover_web_api(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    handle = start_web_server(tmp_path, port=0)
    try:
        request_json(handle.url, "/api/init", method="POST", payload={"name": "demo", "type": "web-app"})
        (tmp_path / ".aios" / "context.md").write_text("# Context\n\nTest.\n", encoding="utf-8")
        (tmp_path / ".aios" / "architecture.md").write_text("# Arch\n\nTest.\n", encoding="utf-8")
        (tmp_path / "main.py").write_text("print('ok')\n", encoding="utf-8")
        request_json(handle.url, "/api/scan", method="POST")
        request_json(handle.url, "/api/tasks", method="POST", payload={"title": "API test", "priority": "high"})
        task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]

        # Enqueue a takeover
        entry = enqueue_takeover(tmp_path, task["id"], "Test failure", failure_category="network_timeout")

        # Read takeover queue via API
        status_code, payload = request_json(handle.url, "/api/run/takeover")
        assert status_code == 200
        assert payload["takeover"]["pending"] >= 1

        # Resolve takeover via API
        status_code, payload = request_json(
            handle.url,
            f"/api/run/takeover/{entry['takeover_id']}/resolve",
            method="POST",
            payload={"note": "Fixed connection"},
        )
        assert status_code == 200
        assert payload["entry"]["status"] == "resolved"
    finally:
        handle.close()


# ── full pipeline ──────────────────────────────────────────────────

def test_full_pipeline_idle_when_no_tasks(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    result = run_full_pipeline(tmp_path, auto_switch=False, max_tasks=5)
    assert result["total_tasks"] == 0
    assert result["pipeline_completed"] is True


def test_full_pipeline_runs_multiple_tasks(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    (tmp_path / ".aios" / "context.md").write_text("# Context\n\nTest.\n", encoding="utf-8")
    (tmp_path / ".aios" / "architecture.md").write_text("# Arch\n\nTest.\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("print('ok')\n", encoding="utf-8")
    main(["--root", str(tmp_path), "scan"])
    main(["--root", str(tmp_path), "task", "create", "Fix A", "--priority", "high"])
    main(["--root", str(tmp_path), "task", "create", "Fix B", "--priority", "high"])

    create_executor(
        None, "fp-echo",
        label="FP Echo",
        kind="command",
        enabled=True,
        rank=1,
        binary="echo",
        args=["done", "{model}"],
        timeout_seconds=5,
        pass_model_as_flag=False,
        env={},
    )

    tasks = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"]
    for task in tasks:
        main(["--root", str(tmp_path), "run", task["id"], "--manual", "--model", "gpt-5.5"])

    monkeypatch.setattr("aios.core.auto_switch.subprocess", unit_mock.MagicMock())
    result = run_full_pipeline(
        tmp_path,
        executor_id="fp-echo",
        model="gpt-5.5",
        auto_switch=False,
        max_tasks=10,
        step_delay_seconds=0,
    )
    assert result["total_tasks"] >= 1


def test_full_pipeline_web_api(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    handle = start_web_server(tmp_path, port=0)
    try:
        request_json(handle.url, "/api/init", method="POST", payload={"name": "demo", "type": "web-app"})
        (tmp_path / ".aios" / "context.md").write_text("# Context\n\nTest.\n", encoding="utf-8")
        (tmp_path / ".aios" / "architecture.md").write_text("# Arch\n\nTest.\n", encoding="utf-8")
        (tmp_path / "main.py").write_text("print('ok')\n", encoding="utf-8")
        request_json(handle.url, "/api/scan", method="POST")
        request_json(handle.url, "/api/tasks", method="POST", payload={"title": "API pipeline test", "priority": "high"})

        task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
        request_json(handle.url, "/api/run/manual", method="POST", payload={"task_id": task["id"], "model": "gpt-5.5", "start": True})

        monkeypatch.setattr("aios.core.auto_switch.subprocess", unit_mock.MagicMock())
        status_code, payload = request_json(
            handle.url, "/api/run/full-pipeline", method="POST",
            payload={"auto_switch": False, "max_tasks": 5, "step_delay": 0},
        )
        assert status_code == 201
        assert "pipeline_completed" in payload
        assert "task_results" in payload
    finally:
        handle.close()
