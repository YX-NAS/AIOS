"""P4 auto-pipeline tests: auto-switch + executor command build + pipeline step."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock as unit_mock

from aios.main import main
from aios.core.auto_switch import (
    auto_switch_model,
    build_auto_executor_command,
    run_auto_pipeline_step,
)
from aios.core.executions import latest_execution_for_task
from aios.core.models import create_model, load_model_library
from aios.core.executors import create_executor, load_executor_library
from aios.core.webapp import start_web_server
from tests.test_error_handling import request_json


# ── auto_switch_model ──────────────────────────────────────────────

def test_auto_switch_model_opens_deep_links(tmp_path: Path, monkeypatch) -> None:
    """auto_switch_model sends provider and prompt deep links."""
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    (tmp_path / ".aios" / "context.md").write_text("# Context\n\nTest.\n", encoding="utf-8")
    (tmp_path / ".aios" / "architecture.md").write_text("# Arch\n\nTest.\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("print('ok')\n", encoding="utf-8")
    main(["--root", str(tmp_path), "scan"])
    main(["--root", str(tmp_path), "task", "create", "Add feature X", "--priority", "high"])

    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    main(["--root", str(tmp_path), "run", task["id"], "--manual", "--model", "gpt-5.5", "--start"])

    opened_urls: list[str] = []
    monkeypatch.setattr("aios.core.auto_switch.open_ccswitch_deeplink", lambda url: opened_urls.append(url))

    result = auto_switch_model(tmp_path, task["id"], "gpt-5.5", switch_delay_seconds=0, max_wait_seconds=1)
    assert result["success"] is True
    assert len(opened_urls) >= 2
    assert "ccswitch://" in opened_urls[0]
    assert "resource" in opened_urls[0]
    assert "resource=prompt" in opened_urls[1]


def test_auto_switch_model_unknown_model(tmp_path: Path, monkeypatch) -> None:
    """auto_switch_model fails when the model is not in the library."""
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    (tmp_path / ".aios" / "context.md").write_text("# Context\n\nTest.\n", encoding="utf-8")
    (tmp_path / ".aios" / "architecture.md").write_text("# Arch\n\nTest.\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("print('ok')\n", encoding="utf-8")
    main(["--root", str(tmp_path), "scan"])
    main(["--root", str(tmp_path), "task", "create", "Add feature Y", "--priority", "high"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    main(["--root", str(tmp_path), "run", task["id"], "--manual", "--model", "gpt-5.5", "--start"])

    result = auto_switch_model(tmp_path, task["id"], "nonexistent-model-xyz")
    assert result["success"] is False
    assert "not found" in result["reason"].lower()


# ── build_auto_executor_command ─────────────────────────────────────

def test_build_auto_executor_command_for_codex_cli(tmp_path: Path, monkeypatch) -> None:
    """build_auto_executor_command generates a valid codex CLI command."""
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    (tmp_path / ".aios" / "context.md").write_text("# Context\n\nTest.\n", encoding="utf-8")
    (tmp_path / ".aios" / "architecture.md").write_text("# Arch\n\nTest.\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("print('ok')\n", encoding="utf-8")
    main(["--root", str(tmp_path), "scan"])
    main(["--root", str(tmp_path), "task", "create", "Fix login bug", "--priority", "high"])

    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    main(["--root", str(tmp_path), "run", task["id"], "--manual", "--model", "gpt-5.5", "--start"])

    monkeypatch.setattr("aios.core.auto_switch.executor_runtime_status", lambda ex: {"available": True})
    cmd = build_auto_executor_command(tmp_path, task["id"], executor_id="codex-cli", model_id="gpt-5.5")
    assert cmd["executor_id"] == "codex-cli"
    assert "gpt-5.5" in cmd["command_str"]
    assert cmd["pass_model_as_flag"] is True


def test_build_auto_executor_command_no_execution(tmp_path: Path, monkeypatch) -> None:
    """build_auto_executor_command raises if no execution record exists."""
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    (tmp_path / ".aios" / "context.md").write_text("# Context\n\nTest.\n", encoding="utf-8")
    (tmp_path / ".aios" / "architecture.md").write_text("# Arch\n\nTest.\n", encoding="utf-8")
    main(["--root", str(tmp_path), "scan"])
    main(["--root", str(tmp_path), "task", "create", "Add feature", "--priority", "high"])

    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    import pytest
    with pytest.raises(ValueError, match="No execution record"):
        build_auto_executor_command(tmp_path, task["id"], executor_id="codex-cli", model_id="gpt-5.5")


# ── run_auto_pipeline_step ──────────────────────────────────────────

def test_pipeline_step_no_dispatchable_task(tmp_path: Path, monkeypatch) -> None:
    """Pipeline step returns idle when no tasks are ready."""
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    result = run_auto_pipeline_step(tmp_path, auto_switch=False)
    assert result["pipeline_status"] == "idle"


def test_pipeline_step_without_switch(tmp_path: Path, monkeypatch) -> None:
    """Pipeline step runs executor without auto-switch."""
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    (tmp_path / ".aios" / "context.md").write_text("# Context\n\nTest.\n", encoding="utf-8")
    (tmp_path / ".aios" / "architecture.md").write_text("# Arch\n\nTest.\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("print('ok')\n", encoding="utf-8")
    main(["--root", str(tmp_path), "scan"])
    main(["--root", str(tmp_path), "task", "create", "Fix bug", "--priority", "high"])

    # Create executor first
    create_executor(
        None, "echo-test",
        label="Echo Test",
        kind="command",
        enabled=True,
        rank=1,
        binary="echo",
        args=["hello", "{model}", "{prompt}"],
        timeout_seconds=10,
        pass_model_as_flag=False,
        env={},
    )

    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    main(["--root", str(tmp_path), "run", task["id"], "--manual", "--model", "gpt-5.5", "--start"])

    monkeypatch.setattr("aios.core.auto_switch.subprocess", unit_mock.MagicMock())
    result = run_auto_pipeline_step(
        tmp_path, executor_id="echo-test", model="gpt-5.5", auto_switch=False
    )
    assert result["pipeline_status"] in ("completed", "executor_unavailable", "blocked")


def test_pipeline_cli_integration(tmp_path: Path, monkeypatch) -> None:
    """`aios run pipeline` CLI subcommand works."""
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    (tmp_path / ".aios" / "context.md").write_text("# Context\n\nTest.\n", encoding="utf-8")
    (tmp_path / ".aios" / "architecture.md").write_text("# Arch\n\nTest.\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("print('ok')\n", encoding="utf-8")
    main(["--root", str(tmp_path), "scan"])
    main(["--root", str(tmp_path), "task", "create", "Fix test bug", "--priority", "high"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]

    monkeypatch.setattr("aios.core.auto_switch.subprocess", unit_mock.MagicMock())
    # This should not raise
    main(["--root", str(tmp_path), "run", "pipeline", "--auto-switch", "--switch-delay", "0"])
    assert latest_execution_for_task(tmp_path, task["id"]) is not None


def test_pipeline_web_api(tmp_path: Path, monkeypatch) -> None:
    """POST /api/run/pipeline endpoint works."""
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    handle = start_web_server(tmp_path, port=0)
    try:
        request_json(handle.url, "/api/init", method="POST", payload={"name": "demo", "type": "web-app"})
        (tmp_path / ".aios" / "context.md").write_text("# Context\n\nTest.\n", encoding="utf-8")
        (tmp_path / ".aios" / "architecture.md").write_text("# Arch\n\nTest.\n", encoding="utf-8")
        (tmp_path / "main.py").write_text("print('ok')\n", encoding="utf-8")
        request_json(handle.url, "/api/scan", method="POST")
        request_json(handle.url, "/api/tasks", method="POST", payload={"title": "Test endpoint", "priority": "high"})

        task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
        request_json(handle.url, "/api/run/manual", method="POST", payload={"task_id": task["id"], "model": "gpt-5.5", "start": True})

        monkeypatch.setattr("aios.core.auto_switch.subprocess", unit_mock.MagicMock())
        status_code, payload = request_json(
            handle.url, "/api/run/pipeline", method="POST",
            payload={"auto_switch": False, "auto_finish": False},
        )
        assert status_code == 201
        assert "pipeline_status" in payload
    finally:
        handle.close()
