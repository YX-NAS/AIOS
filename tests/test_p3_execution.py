from __future__ import annotations

import json
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

import aios.core.ccswitch as ccswitch_core
import aios.core.executors as executors_core
import aios.core.executions as executions_core
import aios.core.models as models_core
import aios.core.terminal_resume as terminal_resume
from aios.core.executors import create_executor, load_executor_library
from aios.core.executions import build_execution_resume, latest_execution_for_task, load_executions, run_executor_execution
from aios.core.instance_manager import project_id_for_root, stop_project_instance
from aios.core.launcher import start_launcher_server
from aios.core.models import create_model, update_model
from aios.core.tasks import update_task_fields
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


def init_git_repo(root: Path) -> None:
    import subprocess

    subprocess.run(["git", "init"], cwd=str(root), capture_output=True, check=False, timeout=10)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(root), capture_output=True, check=False, timeout=5)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(root), capture_output=True, check=False, timeout=5)


def git_commit_all(root: Path, message: str) -> None:
    import subprocess

    subprocess.run(["git", "add", "."], cwd=str(root), capture_output=True, check=False, timeout=10)
    subprocess.run(["git", "commit", "-m", message], cwd=str(root), capture_output=True, check=False, timeout=10)


def git_checkout_new_branch(root: Path, branch: str) -> None:
    import subprocess

    subprocess.run(["git", "checkout", "-b", branch], cwd=str(root), capture_output=True, check=False, timeout=10)


def git_add_remote(root: Path, remote: str, target: Path) -> None:
    import subprocess

    subprocess.run(["git", "remote", "add", remote, str(target)], cwd=str(root), capture_output=True, check=False, timeout=10)


def init_bare_remote(root: Path) -> Path:
    import subprocess

    remote = root.parent / f"{root.name}-remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], capture_output=True, check=False, timeout=10)
    return remote


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
        assert "ready_count" in created_payload["project"]
        assert "scheduler_next_action" in created_payload["project"]

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


def test_executor_library_defaults_include_resume_templates() -> None:
    assert main(["executor", "reset"]) == 0
    executors = load_executor_library()
    codex = next(item for item in executors if item["id"] == "codex-cli")
    claude = next(item for item in executors if item["id"] == "claude-code-cli")
    assert codex["resume_args"] == ["resume", "{session_ref}"]
    assert codex["continue_args"] == ["resume", "--last"]
    assert claude["resume_args"] == ["--resume", "{session_ref}"]


def test_executor_summary_reports_runtime_availability(monkeypatch) -> None:
    monkeypatch.setattr(executors_core.shutil, "which", lambda binary: f"/usr/local/bin/{binary}" if binary == "codex" else None)

    def fake_run(command, capture_output, text, timeout, check):
        class Result:
            returncode = 0
            stdout = "codex 1.2.3"
            stderr = ""
        return Result()

    monkeypatch.setattr(executors_core.subprocess, "run", fake_run)
    summary = executors_core.executor_summary()
    codex = next(item for item in summary["executors"] if item["id"] == "codex-cli")
    claude = next(item for item in summary["executors"] if item["id"] == "claude-code-cli")
    assert codex["runtime"]["available"] is True
    assert codex["runtime"]["healthcheck_status"] == "ok"
    assert claude["runtime"]["available"] is False
    assert summary["available_executor_count"] >= 1
    assert claude["continue_args"] == ["--continue"]


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


def test_run_attach_and_resume_cli_builds_session_commands(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    main(["--root", str(tmp_path), "task", "create", "实现登录功能", "--priority", "high"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    main(["--root", str(tmp_path), "run", "--manual", task["id"], "--start"])

    assert main(
        [
            "--root",
            str(tmp_path),
            "run",
            "attach",
            task["id"],
            "--executor",
            "codex-cli",
            "--session-id",
            "session-123",
        ]
    ) == 0

    execution = latest_execution_for_task(tmp_path, task["id"])
    assert execution is not None
    assert execution["executor_id"] == "codex-cli"
    assert execution["executor_session_id"] == "session-123"
    assert "codex resume session-123" in execution["executor_resume_command"]
    assert "codex resume --last" in execution["executor_continue_command"]

    assert main(["--root", str(tmp_path), "run", "resume", task["id"]]) == 0
    output = capsys.readouterr().out
    assert "Mode: attached" in output
    assert "codex resume session-123" in output

    assert main(["--root", str(tmp_path), "run", "resume", task["id"], "--latest-session"]) == 0
    output = capsys.readouterr().out
    assert "Mode: latest" in output
    assert "codex resume --last" in output


def test_run_resume_cli_can_open_terminal_on_macos(tmp_path: Path, monkeypatch, capsys) -> None:
    launched: dict = {}

    def fake_run(command: list[str], capture_output: bool, text: bool, check: bool):
        launched["command"] = command
        launched["capture_output"] = capture_output
        launched["text"] = text
        launched["check"] = check

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    monkeypatch.setattr(terminal_resume.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_resume.subprocess, "run", fake_run)

    main(["--root", str(tmp_path), "init", "--name", "demo"])
    main(["--root", str(tmp_path), "task", "create", "实现登录功能", "--priority", "high"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    main(["--root", str(tmp_path), "run", "--manual", task["id"], "--start"])
    main(["--root", str(tmp_path), "run", "attach", task["id"], "--executor", "codex-cli", "--session-id", "session-123"])

    assert main(["--root", str(tmp_path), "run", "resume", task["id"], "--open-terminal"]) == 0

    execution = latest_execution_for_task(tmp_path, task["id"])
    assert execution is not None
    assert execution["executor_terminal_launch_status"] == "opened"
    assert execution["executor_terminal_launch_app"] == "Terminal"
    assert execution["executor_terminal_launch_mode"] == "attached"
    assert execution["executor_terminal_launch_command"] == execution["executor_resume_last_command"]
    assert launched["command"][0] == "osascript"
    assert "session-123" in " ".join(launched["command"])
    output = capsys.readouterr().out
    assert "Resume opened for" in output


def test_run_resume_api_can_open_terminal_on_macos(tmp_path: Path, monkeypatch) -> None:
    launched: dict = {}

    def fake_run(command: list[str], capture_output: bool, text: bool, check: bool):
        launched["command"] = command

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    monkeypatch.setattr(terminal_resume.sys, "platform", "darwin")
    monkeypatch.setattr(terminal_resume.subprocess, "run", fake_run)
    handle = start_web_server(tmp_path, port=0)
    try:
        request_json(handle.url, "/api/init", method="POST", payload={"name": "demo", "type": "web-app"})
        request_json(handle.url, "/api/tasks", method="POST", payload={"title": "修复登录报错", "priority": "high"})
        task_id = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]["id"]
        request_json(handle.url, "/api/run/manual", method="POST", payload={"task_id": task_id, "start": True})
        request_json(
            handle.url,
            "/api/run/attach",
            method="POST",
            payload={"task_id": task_id, "executor_id": "codex-cli", "session_id": "session-456"},
        )

        status_code, payload = request_json(
            handle.url,
            "/api/run/resume",
            method="POST",
            payload={"task_id": task_id, "open_terminal": True},
        )
        assert status_code == 201
        assert payload["terminal"]["opened"] is True
        assert payload["execution"]["executor_terminal_launch_status"] == "opened"
        assert payload["execution"]["executor_terminal_launch_app"] == "Terminal"
        assert "session-456" in " ".join(launched["command"])
    finally:
        handle.close()


def test_ccswitch_export_cli_stdout_outputs_json(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    main(["--root", str(tmp_path), "task", "create", "实现登录功能", "--priority", "high"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    main(["--root", str(tmp_path), "run", "--manual", task["id"], "--start"])

    assert main(["--root", str(tmp_path), "ccswitch", "export", task["id"], "--stdout"]) == 0
    output = capsys.readouterr().out
    assert '"task_id"' in output
    assert '"export_model"' in output


def test_ccswitch_deeplink_cli_outputs_url_and_records_execution(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    main(["--root", str(tmp_path), "task", "create", "实现登录功能", "--priority", "high"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    main(["--root", str(tmp_path), "run", "--manual", task["id"], "--start"])

    assert main(["--root", str(tmp_path), "ccswitch", "deeplink", task["id"], "--app", "codex", "--stdout"]) == 0
    output = capsys.readouterr().out
    assert "ccswitch://v1/import?" in output

    execution = latest_execution_for_task(tmp_path, task["id"])
    assert execution is not None
    assert execution["ccswitch_deeplink"].startswith("ccswitch://v1/import?")
    assert execution["ccswitch_deeplink_app"] == "codex"


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


def test_ccswitch_deeplink_api_returns_prompt_link(tmp_path: Path) -> None:
    handle = start_web_server(tmp_path, port=0)
    try:
        request_json(handle.url, "/api/init", method="POST", payload={"name": "demo", "type": "web-app"})
        request_json(handle.url, "/api/tasks", method="POST", payload={"title": "修复登录报错", "priority": "high"})
        task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
        request_json(handle.url, "/api/run/manual", method="POST", payload={"task_id": task["id"], "start": True})

        status_code, payload = request_json(
            handle.url,
            "/api/ccswitch/deeplink",
            method="POST",
            payload={"task_id": task["id"], "app": "codex"},
        )
        assert status_code == 201
        assert payload["app"] == "codex"
        assert payload["deeplink"].startswith("ccswitch://v1/import?")
        assert payload["execution"]["ccswitch_deeplink_app"] == "codex"
    finally:
        handle.close()


def test_ccswitch_provider_deeplink_cli_uses_global_model_metadata(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    create_model(
        None,
        "gpt-5.5-coder",
        "GPT 5.5 Coder",
        "openai",
        True,
        1,
        ["complex_coding"],
        "https://api.openai.com/v1",
        None,
        "需要本地路由",
        "https://example.com/openai-config.json",
    )
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    main(["--root", str(tmp_path), "task", "create", "实现登录功能", "--priority", "high"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    main(["--root", str(tmp_path), "run", "--manual", task["id"], "--model", "gpt-5.5-coder", "--start"])

    assert main(["--root", str(tmp_path), "ccswitch", "provider", task["id"], "--app", "codex", "--stdout"]) == 0
    output = capsys.readouterr().out
    assert "resource=provider" in output
    assert "https%3A%2F%2Fapi.openai.com%2Fv1" in output

    execution = latest_execution_for_task(tmp_path, task["id"])
    assert execution is not None
    assert execution["ccswitch_provider_name"] == "openai"
    assert execution["ccswitch_provider_model"] == "gpt-5.5-coder"


def test_ccswitch_session_handoff_cli_exports_json_bundle(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    create_model(
        None,
        "gpt-5.5-coder",
        "GPT 5.5 Coder",
        "openai",
        True,
        1,
        ["complex_coding"],
        "https://api.openai.com/v1",
        None,
        "需要本地路由",
        None,
    )
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    main(["--root", str(tmp_path), "task", "create", "实现登录功能", "--priority", "high"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    main(["--root", str(tmp_path), "run", "--manual", task["id"], "--model", "gpt-5.5-coder", "--start"])

    assert main(["--root", str(tmp_path), "ccswitch", "session", task["id"]]) == 0

    execution = latest_execution_for_task(tmp_path, task["id"])
    assert execution is not None
    handoff_path = tmp_path / execution["ccswitch_session_handoff_path"]
    assert handoff_path.exists()
    payload = json.loads(handoff_path.read_text(encoding="utf-8"))
    assert payload["provider"] == "openai"
    assert payload["model"] == "gpt-5.5-coder"
    assert payload["provider_deeplink"].startswith("ccswitch://v1/import?")
    assert payload["prompt_deeplink"].startswith("ccswitch://v1/import?")
    assert task["id"] in payload["session_search_keywords"]


def test_ccswitch_bridge_cli_exports_and_opens_sequence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    create_model(
        None,
        "gpt-5.5-coder",
        "GPT 5.5 Coder",
        "openai",
        True,
        1,
        ["complex_coding"],
        "https://api.openai.com/v1",
        None,
        "需要本地路由",
        None,
    )
    opened_links: list[str] = []
    launched_commands: list[tuple[str, str]] = []
    delays: list[float] = []

    monkeypatch.setattr(ccswitch_core, "open_ccswitch_deeplink", lambda deeplink: opened_links.append(deeplink))
    monkeypatch.setattr(ccswitch_core, "launch_command_in_terminal", lambda command, app="Terminal": launched_commands.append((command, app)) or {"opened": True, "app": app, "command": command})
    monkeypatch.setattr(ccswitch_core.time, "sleep", lambda seconds: delays.append(seconds))

    main(["--root", str(tmp_path), "init", "--name", "demo"])
    main(["--root", str(tmp_path), "task", "create", "实现登录功能", "--priority", "high"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    main(["--root", str(tmp_path), "run", "--manual", task["id"], "--model", "gpt-5.5-coder", "--start"])
    main(["--root", str(tmp_path), "run", "attach", task["id"], "--executor", "codex-cli", "--session-id", "session-123"])

    assert main(["--root", str(tmp_path), "ccswitch", "bridge", task["id"], "--open"]) == 0

    execution = latest_execution_for_task(tmp_path, task["id"])
    assert execution is not None
    bridge_path = tmp_path / execution["ccswitch_bridge_path"]
    assert bridge_path.exists()
    payload = json.loads(bridge_path.read_text(encoding="utf-8"))
    assert payload["bridge_mode"] == "attached"
    assert payload["bridge_status"] == "completed"
    assert payload["bridge_confirmation_status"] == "pending_confirmation"
    assert payload["bridge_last_step"] == "attached"
    assert payload["bridge_error"] is None
    assert payload["provider_deeplink"].startswith("ccswitch://v1/import?")
    assert payload["prompt_deeplink"].startswith("ccswitch://v1/import?")
    assert "codex resume session-123" in payload["resume_command"]
    assert [step["status"] for step in payload["steps"]] == ["completed", "completed", "completed", "completed", "completed"]
    assert len(opened_links) == 2
    assert len(launched_commands) == 1
    assert launched_commands[0][1] == "Terminal"
    assert delays == [1.2, 1.2]
    assert execution["ccswitch_bridge_status"] == "completed"
    assert execution["ccswitch_bridge_confirmation_status"] == "pending_confirmation"
    assert execution["ccswitch_bridge_last_step"] == "attached"
    assert execution["ccswitch_bridge_error"] is None


def test_ccswitch_provider_and_session_api_return_auditable_payloads(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    create_model(
        None,
        "gpt-5.5-coder",
        "GPT 5.5 Coder",
        "openai",
        True,
        1,
        ["complex_coding"],
        "https://api.openai.com/v1",
        None,
        "需要本地路由",
        "https://example.com/openai-config.json",
    )
    handle = start_web_server(tmp_path, port=0)
    try:
        request_json(handle.url, "/api/init", method="POST", payload={"name": "demo", "type": "web-app"})
        request_json(handle.url, "/api/tasks", method="POST", payload={"title": "修复登录报错", "priority": "high"})
        task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
        request_json(
            handle.url,
            "/api/run/manual",
            method="POST",
            payload={"task_id": task["id"], "model": "gpt-5.5-coder", "start": True},
        )

        status_code, provider_payload = request_json(
            handle.url,
            "/api/ccswitch/provider-deeplink",
            method="POST",
            payload={"task_id": task["id"], "app": "codex"},
        )
        assert status_code == 201
        assert provider_payload["provider"] == "openai"
        assert provider_payload["deeplink"].startswith("ccswitch://v1/import?")

        status_code, session_payload = request_json(
            handle.url,
            "/api/ccswitch/session-handoff",
            method="POST",
            payload={"task_id": task["id"], "app": "codex"},
        )
        assert status_code == 201
        assert session_payload["handoff"]["provider_config"]["endpoint"] == "https://api.openai.com/v1"
        assert (tmp_path / session_payload["handoff_path"]).exists()
        assert session_payload["execution"]["ccswitch_session_app"] == "codex"
    finally:
        handle.close()


def test_ccswitch_bridge_api_returns_bundle_and_audits_execution(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    create_model(
        None,
        "gpt-5.5-coder",
        "GPT 5.5 Coder",
        "openai",
        True,
        1,
        ["complex_coding"],
        "https://api.openai.com/v1",
        None,
        "需要本地路由",
        None,
    )
    opened_links: list[str] = []
    launched_commands: list[tuple[str, str]] = []
    monkeypatch.setattr(ccswitch_core, "open_ccswitch_deeplink", lambda deeplink: opened_links.append(deeplink))
    monkeypatch.setattr(ccswitch_core, "launch_command_in_terminal", lambda command, app="Terminal": launched_commands.append((command, app)) or {"opened": True, "app": app, "command": command})
    monkeypatch.setattr(ccswitch_core.time, "sleep", lambda seconds: None)

    handle = start_web_server(tmp_path, port=0)
    try:
        request_json(handle.url, "/api/init", method="POST", payload={"name": "demo", "type": "web-app"})
        request_json(handle.url, "/api/tasks", method="POST", payload={"title": "修复登录报错", "priority": "high"})
        task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
        request_json(
            handle.url,
            "/api/run/manual",
            method="POST",
            payload={"task_id": task["id"], "model": "gpt-5.5-coder", "start": True},
        )
        request_json(
            handle.url,
            "/api/run/attach",
            method="POST",
            payload={"task_id": task["id"], "executor_id": "codex-cli", "session_id": "session-789"},
        )

        status_code, bridge_payload = request_json(
            handle.url,
            "/api/ccswitch/bridge",
            method="POST",
            payload={"task_id": task["id"], "app": "codex", "open": True},
        )
        assert status_code == 201
        assert bridge_payload["bridge"]["bridge_mode"] == "attached"
        assert bridge_payload["bridge"]["bridge_status"] == "completed"
        assert bridge_payload["bridge"]["bridge_confirmation_status"] == "pending_confirmation"
        assert bridge_payload["opened"] is True
        assert bridge_payload["execution"]["ccswitch_bridge_app"] == "codex"
        assert bridge_payload["execution"]["ccswitch_bridge_status"] == "completed"
        assert bridge_payload["execution"]["ccswitch_bridge_confirmation_status"] == "pending_confirmation"
        assert (tmp_path / bridge_payload["bridge_path"]).exists()
        assert len(opened_links) == 2
        assert launched_commands[0][1] == "Terminal"
    finally:
        handle.close()


def test_ccswitch_bridge_marks_failed_step_when_prompt_import_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    create_model(
        None,
        "gpt-5.5-coder",
        "GPT 5.5 Coder",
        "openai",
        True,
        1,
        ["complex_coding"],
        "https://api.openai.com/v1",
        None,
        "需要本地路由",
        None,
    )
    calls: list[str] = []

    def flaky_open(deeplink: str) -> None:
        calls.append(deeplink)
        if len(calls) == 2:
            raise ValueError("prompt import failed")

    monkeypatch.setattr(ccswitch_core, "open_ccswitch_deeplink", flaky_open)
    monkeypatch.setattr(ccswitch_core, "launch_command_in_terminal", lambda command, app="Terminal": {"opened": True, "app": app, "command": command})
    monkeypatch.setattr(ccswitch_core.time, "sleep", lambda seconds: None)

    main(["--root", str(tmp_path), "init", "--name", "demo"])
    main(["--root", str(tmp_path), "task", "create", "实现登录功能", "--priority", "high"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    main(["--root", str(tmp_path), "run", "--manual", task["id"], "--model", "gpt-5.5-coder", "--start"])
    main(["--root", str(tmp_path), "run", "attach", task["id"], "--executor", "codex-cli", "--session-id", "session-123"])

    assert main(["--root", str(tmp_path), "ccswitch", "bridge", task["id"], "--open"]) == 0

    execution = latest_execution_for_task(tmp_path, task["id"])
    assert execution is not None
    assert execution["ccswitch_bridge_status"] == "failed"
    assert execution["ccswitch_bridge_confirmation_status"] == "pending_confirmation"
    assert execution["ccswitch_bridge_last_step"] == "prompt"
    assert execution["ccswitch_bridge_error"] == "prompt import failed"
    payload = json.loads((tmp_path / execution["ccswitch_bridge_path"]).read_text(encoding="utf-8"))
    assert payload["bridge_status"] == "failed"
    assert payload["bridge_confirmation_status"] == "pending_confirmation"
    assert payload["bridge_error"] == "prompt import failed"
    assert payload["steps"][0]["status"] == "completed"
    assert payload["steps"][2]["status"] == "failed"
    assert payload["steps"][4]["status"] == "pending"


def test_ccswitch_confirm_cli_updates_bridge_confirmation_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    create_model(
        None,
        "gpt-5.5-coder",
        "GPT 5.5 Coder",
        "openai",
        True,
        1,
        ["complex_coding"],
        "https://api.openai.com/v1",
        None,
        "需要本地路由",
        None,
    )
    monkeypatch.setattr(ccswitch_core, "open_ccswitch_deeplink", lambda deeplink: None)
    monkeypatch.setattr(ccswitch_core, "launch_command_in_terminal", lambda command, app="Terminal": {"opened": True, "app": app, "command": command})
    monkeypatch.setattr(ccswitch_core.time, "sleep", lambda seconds: None)

    main(["--root", str(tmp_path), "init", "--name", "demo"])
    main(["--root", str(tmp_path), "task", "create", "实现登录功能", "--priority", "high"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    main(["--root", str(tmp_path), "run", "--manual", task["id"], "--model", "gpt-5.5-coder", "--start"])
    main(["--root", str(tmp_path), "run", "attach", task["id"], "--executor", "codex-cli", "--session-id", "session-123"])
    main(["--root", str(tmp_path), "ccswitch", "bridge", task["id"], "--open"])

    assert main(
        [
            "--root",
            str(tmp_path),
            "ccswitch",
            "confirm",
            task["id"],
            "--status",
            "confirmed_ready",
            "--note",
            "已切到正确 provider 并恢复会话",
        ]
    ) == 0

    execution = latest_execution_for_task(tmp_path, task["id"])
    assert execution is not None
    assert execution["ccswitch_bridge_confirmation_status"] == "confirmed_ready"
    assert execution["ccswitch_bridge_confirmation_note"] == "已切到正确 provider 并恢复会话"
    payload = json.loads((tmp_path / execution["ccswitch_bridge_path"]).read_text(encoding="utf-8"))
    assert payload["bridge_confirmation_status"] == "confirmed_ready"
    assert payload["bridge_confirmation_note"] == "已切到正确 provider 并恢复会话"


def test_ccswitch_confirm_api_updates_bridge_confirmation_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    create_model(
        None,
        "gpt-5.5-coder",
        "GPT 5.5 Coder",
        "openai",
        True,
        1,
        ["complex_coding"],
        "https://api.openai.com/v1",
        None,
        "需要本地路由",
        None,
    )
    monkeypatch.setattr(ccswitch_core, "open_ccswitch_deeplink", lambda deeplink: None)
    monkeypatch.setattr(ccswitch_core, "launch_command_in_terminal", lambda command, app="Terminal": {"opened": True, "app": app, "command": command})
    monkeypatch.setattr(ccswitch_core.time, "sleep", lambda seconds: None)

    handle = start_web_server(tmp_path, port=0)
    try:
        request_json(handle.url, "/api/init", method="POST", payload={"name": "demo", "type": "web-app"})
        request_json(handle.url, "/api/tasks", method="POST", payload={"title": "修复登录报错", "priority": "high"})
        task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
        request_json(handle.url, "/api/run/manual", method="POST", payload={"task_id": task["id"], "model": "gpt-5.5-coder", "start": True})
        request_json(handle.url, "/api/run/attach", method="POST", payload={"task_id": task["id"], "executor_id": "codex-cli", "session_id": "session-abc"})
        request_json(handle.url, "/api/ccswitch/bridge", method="POST", payload={"task_id": task["id"], "app": "codex", "open": True})

        status_code, confirm_payload = request_json(
            handle.url,
            "/api/ccswitch/confirm",
            method="POST",
            payload={"task_id": task["id"], "status": "confirmed_failed", "note": "provider 已导入但会话不对"},
        )
        assert status_code == 201
        assert confirm_payload["bridge"]["bridge_confirmation_status"] == "confirmed_failed"
        assert confirm_payload["execution"]["ccswitch_bridge_confirmation_status"] == "confirmed_failed"
        assert confirm_payload["bridge"]["bridge_confirmation_note"] == "provider 已导入但会话不对"
    finally:
        handle.close()


def test_bridge_resume_wrapper_writes_signal_file(tmp_path: Path) -> None:
    signal_path = tmp_path / ".aios" / "ccswitch" / "TASK-1-EXEC-1-model-resume-signal.json"
    wrapped = ccswitch_core._wrap_resume_command_with_signal(
        {
            "project_root": str(tmp_path),
            "resume_signal_path": str(signal_path.relative_to(tmp_path)),
            "task_id": "TASK-1",
            "execution_id": "EXEC-1",
            "model": "model",
            "bridge_mode": "attached",
            "resume_command": "python3 -c \"print('ok')\"",
        }
    )
    completed = subprocess.run(["sh", "-lc", wrapped], cwd=str(tmp_path), capture_output=True, text=True, check=False, timeout=10)
    assert completed.returncode == 0
    assert signal_path.exists()
    payload = json.loads(signal_path.read_text(encoding="utf-8"))
    assert payload["task_id"] == "TASK-1"
    assert payload["execution_id"] == "EXEC-1"
    assert payload["bridge_mode"] == "attached"


def test_task_api_enriches_execution_with_bridge_signal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    create_model(
        None,
        "gpt-5.5-coder",
        "GPT 5.5 Coder",
        "openai",
        True,
        1,
        ["complex_coding"],
        "https://api.openai.com/v1",
        None,
        "需要本地路由",
        None,
    )
    monkeypatch.setattr(ccswitch_core, "open_ccswitch_deeplink", lambda deeplink: None)
    monkeypatch.setattr(ccswitch_core, "launch_command_in_terminal", lambda command, app="Terminal": {"opened": True, "app": app, "command": command})
    monkeypatch.setattr(ccswitch_core.time, "sleep", lambda seconds: None)
    handle = start_web_server(tmp_path, port=0)
    try:
        request_json(handle.url, "/api/init", method="POST", payload={"name": "demo", "type": "web-app"})
        request_json(handle.url, "/api/tasks", method="POST", payload={"title": "修复登录报错", "priority": "high"})
        task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
        request_json(handle.url, "/api/run/manual", method="POST", payload={"task_id": task["id"], "model": "gpt-5.5-coder", "start": True})
        request_json(handle.url, "/api/run/attach", method="POST", payload={"task_id": task["id"], "executor_id": "codex-cli", "session_id": "session-abc"})
        bridge_code, bridge_payload = request_json(handle.url, "/api/ccswitch/bridge", method="POST", payload={"task_id": task["id"], "app": "codex", "open": False})
        assert bridge_code == 201
        signal_path = tmp_path / bridge_payload["bridge"]["resume_signal_path"]
        signal_path.parent.mkdir(parents=True, exist_ok=True)
        signal_path.write_text(json.dumps({"started_at": "2026-07-02T12:00:00", "task_id": task["id"]}, ensure_ascii=False), encoding="utf-8")

        status_code, task_payload = request_json(handle.url, f"/api/tasks/{task['id']}")
        assert status_code == 200
        assert task_payload["execution"]["ccswitch_bridge_resume_signal_status"] == "started"
        assert task_payload["execution"]["ccswitch_bridge_resume_started_at"] == "2026-07-02T12:00:00"
        assert task_payload["execution"]["ccswitch_bridge_effective_confirmation_status"] == "signal_detected"
    finally:
        handle.close()


def test_run_attach_and_resume_api_returns_session_commands(tmp_path: Path) -> None:
    handle = start_web_server(tmp_path, port=0)
    try:
        request_json(handle.url, "/api/init", method="POST", payload={"name": "demo", "type": "web-app"})
        request_json(handle.url, "/api/tasks", method="POST", payload={"title": "修复登录报错", "priority": "high"})
        task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
        request_json(handle.url, "/api/run/manual", method="POST", payload={"task_id": task["id"], "start": True})

        status_code, attach_payload = request_json(
            handle.url,
            "/api/run/attach",
            method="POST",
            payload={"task_id": task["id"], "executor_id": "codex-cli", "session_id": "session-abc"},
        )
        assert status_code == 201
        assert attach_payload["execution"]["executor_session_id"] == "session-abc"
        assert "codex resume session-abc" in attach_payload["execution"]["executor_resume_command"]

        status_code, resume_payload = request_json(
            handle.url,
            "/api/run/resume",
            method="POST",
            payload={"task_id": task["id"]},
        )
        assert status_code == 201
        assert resume_payload["mode"] == "attached"
        assert "codex resume session-abc" in resume_payload["command"]

        status_code, latest_payload = request_json(
            handle.url,
            "/api/run/resume",
            method="POST",
            payload={"task_id": task["id"], "latest": True},
        )
        assert status_code == 201
        assert latest_payload["mode"] == "latest"
        assert "codex resume --last" in latest_payload["command"]
    finally:
        handle.close()


def test_run_resume_can_use_historical_session_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    create_executor(
        None,
        "history-cli",
        label="History CLI",
        kind="command",
        enabled=True,
        rank=1,
        binary="python3",
        args=["-c", "print('ok')", "{prompt}"],
        timeout_seconds=30,
        pass_model_as_flag=False,
        env={},
        resume_args=["resume", "{session_ref}"],
        continue_args=["resume", "--last"],
        resume_in_project_root=True,
        session_ref_label="session_id",
    )
    main(["--root", str(tmp_path), "task", "create", "修复登录报错", "--priority", "high"])
    main(["--root", str(tmp_path), "task", "create", "继续修复登录报错", "--priority", "high"])
    tasks = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"]
    first_task = tasks[0]
    second_task = tasks[1]

    assert main(["--root", str(tmp_path), "run", first_task["id"], "--executor", "history-cli"]) == 0
    assert main(["--root", str(tmp_path), "run", "attach", first_task["id"], "--executor", "history-cli", "--session-id", "session-old"]) == 0
    assert main(["--root", str(tmp_path), "run", second_task["id"], "--executor", "history-cli"]) == 0

    resume = build_execution_resume(tmp_path, second_task["id"], history_fallback=True)
    assert resume["mode"] == "history"
    assert resume["session_ref"] == "session-old"
    assert "python3 resume session-old" in resume["command"]

    execution = latest_execution_for_task(tmp_path, second_task["id"])
    assert execution is not None
    assert execution["executor_resume_history_session_ref"] == "session-old"
    assert execution["executor_resume_history_task_id"] == first_task["id"]


def test_run_sessions_cli_lists_historical_candidates(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    create_executor(
        None,
        "history-cli",
        label="History CLI",
        kind="command",
        enabled=True,
        rank=1,
        binary="python3",
        args=["-c", "print('ok')", "{prompt}"],
        timeout_seconds=30,
        pass_model_as_flag=False,
        env={},
        resume_args=["resume", "{session_ref}"],
        continue_args=["resume", "--last"],
        resume_in_project_root=True,
        session_ref_label="session_id",
    )
    main(["--root", str(tmp_path), "task", "create", "修复登录报错", "--priority", "high"])
    main(["--root", str(tmp_path), "task", "create", "继续修复登录报错", "--priority", "high"])
    tasks = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"]
    first_task = tasks[0]
    second_task = tasks[1]
    main(["--root", str(tmp_path), "run", first_task["id"], "--executor", "history-cli"])
    main(["--root", str(tmp_path), "run", "attach", first_task["id"], "--executor", "history-cli", "--session-id", "session-old"])

    assert main(["--root", str(tmp_path), "run", "sessions", second_task["id"]]) == 0
    output = capsys.readouterr().out
    assert "Historical sessions for" in output
    assert "session-old" in output


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


def test_run_executor_cli_executes_command_and_marks_review_pending(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    main(["--root", str(tmp_path), "task", "create", "更新说明文档", "--priority", "medium"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    create_executor(
        None,
        "mock-cli",
        label="Mock CLI",
        kind="command",
        enabled=True,
        rank=1,
        binary="python3",
        args=["-c", "import sys; print('MOCK EXECUTOR OK'); print(len(sys.argv[-1]))", "{prompt}"],
        timeout_seconds=30,
        pass_model_as_flag=False,
        env={"AIOS_TEST_EXECUTOR": "1"},
    )

    assert main(["--root", str(tmp_path), "run", task["id"], "--executor", "mock-cli"]) == 0

    execution = latest_execution_for_task(tmp_path, task["id"])
    assert execution is not None
    assert execution["mode"] == "cli"
    assert execution["status"] == "review_pending"
    assert execution["executor_id"] == "mock-cli"
    assert execution["executor_exit_code"] == 0
    assert execution["executor_log_path"]
    assert (tmp_path / execution["executor_log_path"]).exists()


def test_run_executor_cli_records_token_cost_and_duration(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    main(["--root", str(tmp_path), "task", "create", "更新说明文档", "--priority", "medium"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    update_model(
        None,
        "gpt-5.5",
        "gpt-5.5",
        "gpt-5.5",
        "openai",
        True,
        1,
        ["documentation", "simple_coding"],
        "https://api.openai.com/v1",
        None,
        None,
        None,
        ["OPENAI_API_KEY"],
        2.0,
        8.0,
        "USD",
    )
    create_executor(
        None,
        "cost-cli",
        label="Cost CLI",
        kind="command",
        enabled=True,
        rank=1,
        binary="python3",
        args=["-c", "print('ok output for token estimate')", "{prompt}"],
        timeout_seconds=30,
        pass_model_as_flag=False,
        env={},
    )

    assert main(["--root", str(tmp_path), "run", task["id"], "--executor", "cost-cli"]) == 0

    execution = latest_execution_for_task(tmp_path, task["id"])
    assert execution is not None
    assert execution["prompt_token_estimate"] > 0
    assert execution["output_token_estimate"] > 0
    assert execution["total_token_estimate"] == execution["prompt_token_estimate"] + execution["output_token_estimate"]
    assert execution["estimated_input_cost"] is not None
    assert execution["estimated_total_cost"] is not None
    assert execution["cost_currency"] == "USD"
    assert execution["duration_seconds"] is not None


def test_run_executor_cli_auto_extracts_session_reference(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    main(["--root", str(tmp_path), "task", "create", "更新说明文档", "--priority", "medium"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    create_executor(
        None,
        "capture-cli",
        label="Capture CLI",
        kind="command",
        enabled=True,
        rank=1,
        binary="python3",
        args=["-c", "print('session_id: 123e4567-e89b-12d3-a456-426614174000')"],
        timeout_seconds=30,
        pass_model_as_flag=False,
        env={},
        resume_args=["resume", "{session_ref}"],
        continue_args=["resume", "--last"],
        resume_in_project_root=True,
        session_ref_label="session_id",
        session_capture_patterns=[{"pattern": r"session_id:\s*(?P<session_id>[0-9a-fA-F-]{36})", "source": "stdout"}],
    )

    assert main(["--root", str(tmp_path), "run", task["id"], "--executor", "capture-cli"]) == 0

    execution = latest_execution_for_task(tmp_path, task["id"])
    assert execution is not None
    assert execution["executor_session_id"] == "123e4567-e89b-12d3-a456-426614174000"
    assert execution["executor_session_auto_captured"] is True
    assert execution["executor_session_capture_source"] == "stdout"
    assert "python3 resume 123e4567-e89b-12d3-a456-426614174000" in execution["executor_resume_command"]
    updated_task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    assert updated_task["status"] == "running"


def test_run_auto_cli_dispatches_first_ready_task(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    (tmp_path / ".aios" / "context.md").write_text("# 项目上下文\n\n正式背景。\n", encoding="utf-8")
    (tmp_path / ".aios" / "architecture.md").write_text("# 架构说明\n\n正式架构。\n", encoding="utf-8")
    (tmp_path / "service.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# docs\n", encoding="utf-8")
    main(["--root", str(tmp_path), "scan"])
    main(["--root", str(tmp_path), "task", "plan", "开发会员积分系统", "--priority", "high"])
    create_executor(
        None,
        "dispatch-cli",
        label="Dispatch CLI",
        kind="command",
        enabled=True,
        rank=1,
        binary="python3",
        args=["-c", "print('dispatch ok')", "{prompt}"],
        timeout_seconds=30,
        pass_model_as_flag=False,
        env={},
    )

    assert main(["--root", str(tmp_path), "run", "auto", "--executor", "dispatch-cli"]) == 0

    executions = load_executions(tmp_path)
    assert len(executions) == 1
    execution = executions[0]
    assert execution["task_title"] == "梳理系统范围与模块边界：会员积分系统"
    assert execution["status"] == "review_pending"


def test_run_auto_cli_can_use_cheapest_first_strategy(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    (tmp_path / ".aios" / "context.md").write_text("# 项目上下文\n\n正式背景。\n", encoding="utf-8")
    (tmp_path / ".aios" / "architecture.md").write_text("# 架构说明\n\n正式架构。\n", encoding="utf-8")
    (tmp_path / "service.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# docs\n", encoding="utf-8")
    main(["--root", str(tmp_path), "scan"])
    main(["--root", str(tmp_path), "task", "create", "更新说明文档", "--priority", "medium"])
    main(["--root", str(tmp_path), "task", "create", "修复登录报错", "--priority", "high"])
    request_json_payload = {
        "max_total_estimated_cost": None,
        "max_single_execution_cost": None,
        "block_on_unpriced_model": False,
        "dispatch_strategy": "cheapest_first",
        "cost_currency": "USD",
    }
    (tmp_path / ".aios" / "runtime-policy.json").write_text(json.dumps(request_json_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    create_model(
        None,
        "cheap-model-run",
        "Cheap Model Run",
        "openai",
        True,
        1,
        ["documentation"],
        "https://api.openai.com/v1",
        None,
        None,
        None,
        ["OPENAI_API_KEY"],
        0.1,
        0.2,
        "USD",
    )
    create_model(
        None,
        "expensive-model-run",
        "Expensive Model Run",
        "openai",
        True,
        2,
        ["bug_fix"],
        "https://api.openai.com/v1",
        None,
        None,
        None,
        ["OPENAI_API_KEY"],
        100.0,
        200.0,
        "USD",
    )
    tasks = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"]
    tasks[0]["recommended_model"] = "cheap-model-run"
    tasks[1]["recommended_model"] = "expensive-model-run"
    (tmp_path / ".aios" / "tasks.json").write_text(json.dumps({"tasks": tasks}, ensure_ascii=False, indent=2), encoding="utf-8")
    create_executor(
        None,
        "dispatch-cheap-cli",
        label="Dispatch Cheap CLI",
        kind="command",
        enabled=True,
        rank=1,
        binary="python3",
        args=["-c", "print('dispatch ok')", "{prompt}"],
        timeout_seconds=30,
        pass_model_as_flag=False,
        env={},
    )

    assert main(["--root", str(tmp_path), "run", "auto", "--executor", "dispatch-cheap-cli"]) == 0

    execution = load_executions(tmp_path)[0]
    assert execution["task_title"] == "更新说明文档"


def test_run_auto_cli_reports_unavailable_executor_pool(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    monkeypatch.setattr(executors_core.shutil, "which", lambda binary: None)
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    (tmp_path / ".aios" / "context.md").write_text("# 项目上下文\n\n正式背景。\n", encoding="utf-8")
    (tmp_path / ".aios" / "architecture.md").write_text("# 架构说明\n\n正式架构。\n", encoding="utf-8")
    (tmp_path / "service.py").write_text("print('ok')\n", encoding="utf-8")
    main(["--root", str(tmp_path), "scan"])
    main(["--root", str(tmp_path), "task", "plan", "开发会员积分系统", "--priority", "high"])

    assert main(["--root", str(tmp_path), "run", "auto"]) == 0
    output = capsys.readouterr().out
    assert "当前没有可用的命令型执行器" in output


def test_run_auto_cli_can_auto_confirm_bridge_signal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    create_model(
        None,
        "gpt-5.5-coder",
        "GPT 5.5 Coder",
        "openai",
        True,
        1,
        ["complex_coding"],
        "https://api.openai.com/v1",
        None,
        "需要本地路由",
        None,
    )
    monkeypatch.setattr(ccswitch_core, "open_ccswitch_deeplink", lambda deeplink: None)
    monkeypatch.setattr(ccswitch_core, "launch_command_in_terminal", lambda command, app="Terminal": {"opened": True, "app": app, "command": command})
    monkeypatch.setattr(ccswitch_core.time, "sleep", lambda seconds: None)

    main(["--root", str(tmp_path), "init", "--name", "demo"])
    main(["--root", str(tmp_path), "task", "create", "实现登录功能", "--priority", "high"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    main(["--root", str(tmp_path), "run", "--manual", task["id"], "--model", "gpt-5.5-coder", "--start"])
    main(["--root", str(tmp_path), "run", "attach", task["id"], "--executor", "codex-cli", "--session-id", "session-123"])
    main(["--root", str(tmp_path), "ccswitch", "bridge", task["id"], "--open"])

    execution = latest_execution_for_task(tmp_path, task["id"])
    assert execution is not None
    signal_path = tmp_path / execution["ccswitch_bridge_resume_signal_path"]
    signal_path.write_text(json.dumps({"started_at": "2026-07-02T12:00:00"}, ensure_ascii=False), encoding="utf-8")

    assert main(["--root", str(tmp_path), "run", "auto", "--auto-confirm-bridge-signal"]) == 0

    execution = latest_execution_for_task(tmp_path, task["id"])
    assert execution is not None
    assert execution["ccswitch_bridge_confirmation_status"] == "confirmed_ready"
    assert execution["ccswitch_bridge_confirmation_note"] == "Auto-confirmed from bridge resume signal."


def test_run_executor_cli_can_auto_finish_after_verification(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    main(["--root", str(tmp_path), "task", "create", "更新说明文档", "--priority", "medium"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    create_executor(
        None,
        "auto-finish-cli",
        label="Auto Finish CLI",
        kind="command",
        enabled=True,
        rank=1,
        binary="python3",
        args=["-c", "print('ok')", "{prompt}"],
        timeout_seconds=30,
        pass_model_as_flag=False,
        env={},
    )

    assert main(
        [
            "--root",
            str(tmp_path),
            "run",
            task["id"],
            "--executor",
            "auto-finish-cli",
            "--auto-finish",
            "--summary",
            "文档更新完成",
            "--verify-command",
            "python3 -c \"print('verify ok')\"",
        ]
    ) == 0

    execution = latest_execution_for_task(tmp_path, task["id"])
    assert execution is not None
    assert execution["status"] == "finished"
    assert execution["test_command"] == "python3 -c \"print('verify ok')\""
    assert "exit code: 0" in (execution["test_result"] or "")
    updated_task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    assert updated_task["status"] == "done"


def test_run_executor_execution_classifies_missing_binary_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    main(["--root", str(tmp_path), "task", "create", "更新说明文档", "--priority", "medium"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    create_executor(
        None,
        "missing-binary-cli",
        label="Missing Binary CLI",
        kind="command",
        enabled=True,
        rank=1,
        binary="python3",
        args=["{prompt}"],
        timeout_seconds=30,
        pass_model_as_flag=False,
        env={},
    )
    monkeypatch.setattr(executions_core.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError("missing binary")))

    try:
        run_executor_execution(tmp_path, task["id"], "missing-binary-cli")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "Executor binary not found" in str(exc)

    execution = latest_execution_for_task(tmp_path, task["id"])
    assert execution is not None
    assert execution["failure_category"] == "executor_missing_binary"
    assert execution["failure_next_action"] == "fix_executor_binary"
    assert execution["failure_retryable"] is False


def test_run_executor_cli_can_retry_once_with_fallback_after_verification_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    main(["--root", str(tmp_path), "task", "create", "更新说明文档", "--priority", "medium"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    update_task_fields(
        tmp_path,
        task["id"],
        {
            "recommended_model": "gpt-5.5",
            "fallback_models": ["claude"],
        },
    )
    create_executor(
        None,
        "retry-auto-cli",
        label="Retry Auto CLI",
        kind="command",
        enabled=True,
        rank=1,
        binary="python3",
        args=["-c", "print('ok')", "{prompt}"],
        timeout_seconds=30,
        pass_model_as_flag=False,
        env={},
    )
    verify_script = tmp_path / "verify_once.py"
    verify_script.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "import sys",
                "path = Path('.verify-once-count')",
                "count = int(path.read_text(encoding='utf-8')) if path.exists() else 0",
                "path.write_text(str(count + 1), encoding='utf-8')",
                "sys.exit(1 if count == 0 else 0)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert main(
        [
            "--root",
            str(tmp_path),
            "run",
            task["id"],
            "--executor",
            "retry-auto-cli",
            "--auto-finish",
            "--summary",
            "文档更新完成",
            "--verify-command",
            "python3 verify_once.py",
            "--retry-on-verify-fail",
        ]
    ) == 0

    executions = load_executions(tmp_path)
    assert len(executions) == 2
    first_execution = executions[0]
    second_execution = executions[1]
    assert first_execution["status"] == "retry_queued"
    assert first_execution["retry_next_model"] == "claude"
    assert second_execution["status"] == "finished"
    assert second_execution["planned_model"] == "claude"
    assert second_execution["retry_source_execution_id"] == first_execution["execution_id"]
    updated_task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    assert updated_task["status"] == "done"
    assert updated_task["auto_retry_count"] == 1


def test_run_finish_cli_can_auto_commit_when_repo_was_clean(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path.parent / f"{tmp_path.name}-state"))
    init_git_repo(tmp_path)
    (tmp_path / "main.py").write_text("print('demo')\n", encoding="utf-8")
    git_commit_all(tmp_path, "init")
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    git_commit_all(tmp_path, "add aios")
    main(["--root", str(tmp_path), "task", "create", "更新主脚本", "--priority", "medium"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    main(["--root", str(tmp_path), "run", "--manual", task["id"], "--start"])
    (tmp_path / "main.py").write_text("print('demo 2')\n", encoding="utf-8")

    assert main(
        [
            "--root",
            str(tmp_path),
            "run",
            "finish",
            task["id"],
            "--summary",
            "更新主脚本完成",
            "--auto-commit",
        ]
    ) == 0

    execution = latest_execution_for_task(tmp_path, task["id"])
    assert execution is not None
    assert execution["auto_commit_status"] == "committed"
    assert execution["git_commit_after"]


def test_run_finish_cli_skips_auto_commit_when_repo_was_dirty_before_execution(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path.parent / f"{tmp_path.name}-state"))
    init_git_repo(tmp_path)
    (tmp_path / "main.py").write_text("print('demo')\n", encoding="utf-8")
    git_commit_all(tmp_path, "init")
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    git_commit_all(tmp_path, "add aios")
    (tmp_path / "preexisting.txt").write_text("dirty\n", encoding="utf-8")
    main(["--root", str(tmp_path), "task", "create", "更新主脚本", "--priority", "medium"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    main(["--root", str(tmp_path), "run", "--manual", task["id"], "--start"])
    (tmp_path / "main.py").write_text("print('demo 2')\n", encoding="utf-8")

    assert main(
        [
            "--root",
            str(tmp_path),
            "run",
            "finish",
            task["id"],
            "--summary",
            "更新主脚本完成",
            "--auto-commit",
        ]
    ) == 0

    execution = latest_execution_for_task(tmp_path, task["id"])
    assert execution is not None
    assert execution["auto_commit_status"] == "skipped"
    assert "not clean" in (execution["auto_commit_reason"] or "")


def test_run_execute_api_reports_failed_executor(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    create_executor(
        None,
        "failing-cli",
        label="Failing CLI",
        kind="command",
        enabled=True,
        rank=1,
        binary="python3",
        args=["-c", "import sys; print('boom'); sys.exit(2)", "{prompt}"],
        timeout_seconds=30,
        pass_model_as_flag=False,
        env={},
    )
    handle = start_web_server(tmp_path, port=0)
    try:
        request_json(handle.url, "/api/init", method="POST", payload={"name": "demo", "type": "web-app"})
        request_json(handle.url, "/api/tasks", method="POST", payload={"title": "更新说明文档", "priority": "medium"})
        task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]

        status_code, payload = request_json(
            handle.url,
            "/api/run/execute",
            method="POST",
            payload={"task_id": task["id"], "executor_id": "failing-cli"},
        )
        assert status_code == 201
        assert payload["execution"]["status"] == "failed"
        assert payload["execution"]["executor_exit_code"] == 2
    finally:
        handle.close()


def test_run_execute_api_auto_extracts_session_reference(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    create_executor(
        None,
        "capture-api-cli",
        label="Capture API CLI",
        kind="command",
        enabled=True,
        rank=1,
        binary="python3",
        args=["-c", "print('session_id: auto-session-001')"],
        timeout_seconds=30,
        pass_model_as_flag=False,
        env={},
        resume_args=["resume", "{session_ref}"],
        continue_args=["resume", "--last"],
        resume_in_project_root=True,
        session_ref_label="session_id",
        session_capture_patterns=[{"pattern": r"session_id:\s*(?P<session_id>[A-Za-z0-9._:-]{6,})", "source": "stdout"}],
    )
    handle = start_web_server(tmp_path, port=0)
    try:
        request_json(handle.url, "/api/init", method="POST", payload={"name": "demo", "type": "web-app"})
        request_json(handle.url, "/api/tasks", method="POST", payload={"title": "修复登录报错", "priority": "high"})
        task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]

        status_code, payload = request_json(
            handle.url,
            "/api/run/execute",
            method="POST",
            payload={"task_id": task["id"], "executor_id": "capture-api-cli"},
        )
        assert status_code == 201
        assert payload["execution"]["executor_session_id"] == "auto-session-001"
        assert payload["execution"]["executor_session_auto_captured"] is True
        assert "python3 resume auto-session-001" in payload["execution"]["executor_resume_command"]
    finally:
        handle.close()


def test_run_dispatch_api_returns_noop_when_review_pending_exists(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    create_executor(
        None,
        "dispatch-api-cli",
        label="Dispatch API CLI",
        kind="command",
        enabled=True,
        rank=1,
        binary="python3",
        args=["-c", "print('ok')", "{prompt}"],
        timeout_seconds=30,
        pass_model_as_flag=False,
        env={},
    )
    handle = start_web_server(tmp_path, port=0)
    try:
        request_json(handle.url, "/api/init", method="POST", payload={"name": "demo", "type": "web-app"})
        request_json(handle.url, "/api/tasks", method="POST", payload={"title": "更新说明文档", "priority": "medium"})
        task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]

        request_json(
            handle.url,
            "/api/run/execute",
            method="POST",
            payload={"task_id": task["id"], "executor_id": "dispatch-api-cli"},
        )

        status_code, payload = request_json(
            handle.url,
            "/api/run/dispatch",
            method="POST",
            payload={},
        )
        assert status_code == 201
        assert payload["dispatched"] is False
        assert "待复核" in payload["reason"]
    finally:
        handle.close()


def test_run_dispatch_api_can_auto_finish_review_pending_task(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    create_executor(
        None,
        "review-auto-cli",
        label="Review Auto CLI",
        kind="command",
        enabled=True,
        rank=1,
        binary="python3",
        args=["-c", "print('ok')", "{prompt}"],
        timeout_seconds=30,
        pass_model_as_flag=False,
        env={},
    )
    handle = start_web_server(tmp_path, port=0)
    try:
        request_json(handle.url, "/api/init", method="POST", payload={"name": "demo", "type": "web-app"})
        request_json(handle.url, "/api/tasks", method="POST", payload={"title": "更新说明文档", "priority": "medium"})
        task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]

        request_json(
            handle.url,
            "/api/run/execute",
            method="POST",
            payload={"task_id": task["id"], "executor_id": "review-auto-cli"},
        )

        status_code, payload = request_json(
            handle.url,
            "/api/run/dispatch",
            method="POST",
            payload={
                "auto_finish": True,
                "summary": "文档更新完成",
                "verify_command": "python3 -c \"print('verify ok')\"",
            },
        )
        assert status_code == 201
        assert payload["progressed"] is True
        assert payload["auto_finished"] is True
        assert payload["task"]["status"] == "done"
        assert payload["execution"]["status"] == "finished"
    finally:
        handle.close()


def test_run_execute_api_can_auto_commit_after_finish(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path.parent / f"{tmp_path.name}-state"))
    init_git_repo(tmp_path)
    (tmp_path / "main.py").write_text("print('demo')\n", encoding="utf-8")
    git_commit_all(tmp_path, "init")
    handle = start_web_server(tmp_path, port=0)
    try:
        request_json(handle.url, "/api/init", method="POST", payload={"name": "demo", "type": "web-app"})
        git_commit_all(tmp_path, "add aios")
        create_executor(
            None,
            "git-auto-cli",
            label="Git Auto CLI",
            kind="command",
            enabled=True,
            rank=1,
            binary="python3",
            args=[
                "-c",
                "from pathlib import Path; Path('main.py').write_text(\"print('demo 2')\\n\", encoding='utf-8'); print('ok')",
                "{prompt}",
            ],
            timeout_seconds=30,
            pass_model_as_flag=False,
            env={},
        )
        request_json(handle.url, "/api/tasks", method="POST", payload={"title": "更新说明文档", "priority": "medium"})
        task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]

        status_code, payload = request_json(
            handle.url,
            "/api/run/execute",
            method="POST",
            payload={
                "task_id": task["id"],
                "executor_id": "git-auto-cli",
                "auto_finish": True,
                "summary": "更新完成",
                "verify_command": "python3 -c \"print('ok')\"",
                "auto_commit": True,
            },
        )
        assert status_code == 201
        assert payload["auto_finished"] is True
        assert payload["git_commit"]["committed"] is True
    finally:
        handle.close()


def test_run_finish_cli_can_auto_push_feature_branch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path.parent / f"{tmp_path.name}-state"))
    init_git_repo(tmp_path)
    remote = init_bare_remote(tmp_path)
    git_checkout_new_branch(tmp_path, "feature/auto-push")
    git_add_remote(tmp_path, "origin", remote)
    (tmp_path / "main.py").write_text("print('demo')\n", encoding="utf-8")
    git_commit_all(tmp_path, "init")
    __import__("subprocess").run(["git", "push", "-u", "origin", "feature/auto-push"], cwd=str(tmp_path), capture_output=True, check=False, timeout=10)
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    git_commit_all(tmp_path, "add aios")
    __import__("subprocess").run(["git", "push"], cwd=str(tmp_path), capture_output=True, check=False, timeout=10)
    main(["--root", str(tmp_path), "task", "create", "更新主脚本", "--priority", "medium"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    main(["--root", str(tmp_path), "run", "--manual", task["id"], "--start"])
    (tmp_path / "main.py").write_text("print('demo 2')\n", encoding="utf-8")

    assert main(
        [
            "--root",
            str(tmp_path),
            "run",
            "finish",
            task["id"],
            "--summary",
            "更新主脚本完成",
            "--auto-commit",
            "--auto-push",
        ]
    ) == 0

    execution = latest_execution_for_task(tmp_path, task["id"])
    assert execution is not None
    assert execution["auto_push_status"] == "pushed"
    assert execution["auto_push_branch"] == "feature/auto-push"


def test_run_finish_cli_skips_auto_push_on_main_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path.parent / f"{tmp_path.name}-state"))
    init_git_repo(tmp_path)
    remote = init_bare_remote(tmp_path)
    git_add_remote(tmp_path, "origin", remote)
    (tmp_path / "main.py").write_text("print('demo')\n", encoding="utf-8")
    git_commit_all(tmp_path, "init")
    __import__("subprocess").run(["git", "push", "-u", "origin", "master"], cwd=str(tmp_path), capture_output=True, check=False, timeout=10)
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    git_commit_all(tmp_path, "add aios")
    __import__("subprocess").run(["git", "push"], cwd=str(tmp_path), capture_output=True, check=False, timeout=10)
    main(["--root", str(tmp_path), "task", "create", "更新主脚本", "--priority", "medium"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    main(["--root", str(tmp_path), "run", "--manual", task["id"], "--start"])
    (tmp_path / "main.py").write_text("print('demo 2')\n", encoding="utf-8")

    assert main(
        [
            "--root",
            str(tmp_path),
            "run",
            "finish",
            task["id"],
            "--summary",
            "更新主脚本完成",
            "--auto-commit",
            "--auto-push",
        ]
    ) == 0

    execution = latest_execution_for_task(tmp_path, task["id"])
    assert execution is not None
    assert execution["auto_push_status"] == "skipped"
    assert "Protected branch push" in (execution["auto_push_reason"] or "")


def test_run_finish_cli_skips_auto_pr_without_successful_push(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path.parent / f"{tmp_path.name}-state"))
    init_git_repo(tmp_path)
    (tmp_path / "main.py").write_text("print('demo')\n", encoding="utf-8")
    git_commit_all(tmp_path, "init")
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    git_commit_all(tmp_path, "add aios")
    main(["--root", str(tmp_path), "task", "create", "更新主脚本", "--priority", "medium"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    main(["--root", str(tmp_path), "run", "--manual", task["id"], "--start"])
    (tmp_path / "main.py").write_text("print('demo 2')\n", encoding="utf-8")

    assert main(
        [
            "--root",
            str(tmp_path),
            "run",
            "finish",
            task["id"],
            "--summary",
            "更新主脚本完成",
            "--auto-commit",
            "--auto-pr",
        ]
    ) == 0

    execution = latest_execution_for_task(tmp_path, task["id"])
    assert execution is not None
    assert execution["auto_pr_status"] == "skipped"
    assert "No successful auto push" in (execution["auto_pr_reason"] or "")


def test_run_dispatch_api_keeps_review_pending_when_verification_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    create_executor(
        None,
        "verify-fail-cli",
        label="Verify Fail CLI",
        kind="command",
        enabled=True,
        rank=1,
        binary="python3",
        args=["-c", "print('ok')", "{prompt}"],
        timeout_seconds=30,
        pass_model_as_flag=False,
        env={},
    )
    handle = start_web_server(tmp_path, port=0)
    try:
        request_json(handle.url, "/api/init", method="POST", payload={"name": "demo", "type": "web-app"})
        request_json(handle.url, "/api/tasks", method="POST", payload={"title": "更新说明文档", "priority": "medium"})
        task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]

        request_json(
            handle.url,
            "/api/run/execute",
            method="POST",
            payload={"task_id": task["id"], "executor_id": "verify-fail-cli"},
        )

        status_code, payload = request_json(
            handle.url,
            "/api/run/dispatch",
            method="POST",
            payload={
                "auto_finish": True,
                "summary": "文档更新完成",
                "verify_command": "python3 -c \"import sys; sys.exit(3)\"",
            },
        )
        assert status_code == 201
        assert payload["progressed"] is False
        assert payload["auto_finished"] is False
        assert payload["execution"]["status"] == "review_pending"
        assert "Verification failed" in payload["reason"]
        assert payload["execution"]["failure_category"] == "verification_failed"
        assert payload["execution"]["failure_next_action"] == "retry_or_finish"
    finally:
        handle.close()


def test_run_dispatch_api_can_retry_once_with_fallback_after_verification_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    create_executor(
        None,
        "verify-retry-cli",
        label="Verify Retry CLI",
        kind="command",
        enabled=True,
        rank=1,
        binary="python3",
        args=["-c", "print('ok')", "{prompt}"],
        timeout_seconds=30,
        pass_model_as_flag=False,
        env={},
    )
    verify_script = tmp_path / "verify_once.py"
    verify_script.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "import sys",
                "path = Path('.verify-dispatch-count')",
                "count = int(path.read_text(encoding='utf-8')) if path.exists() else 0",
                "path.write_text(str(count + 1), encoding='utf-8')",
                "sys.exit(2 if count == 0 else 0)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    handle = start_web_server(tmp_path, port=0)
    try:
        request_json(handle.url, "/api/init", method="POST", payload={"name": "demo", "type": "web-app"})
        request_json(handle.url, "/api/tasks", method="POST", payload={"title": "更新说明文档", "priority": "medium"})
        task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
        update_task_fields(
            tmp_path,
            task["id"],
            {
                "recommended_model": "gpt-5.5",
                "fallback_models": ["claude"],
            },
        )

        status_code, payload = request_json(
            handle.url,
            "/api/run/dispatch",
            method="POST",
            payload={
                "executor_id": "verify-retry-cli",
                "auto_finish": True,
                "summary": "文档更新完成",
                "verify_command": "python3 verify_once.py",
                "retry_on_verify_fail": True,
            },
        )
        assert status_code == 201
        assert payload["progressed"] is True
        assert payload["dispatched"] is True
        assert payload["auto_retried"] is True
        assert payload["auto_finished"] is True
        assert payload["retry"]["failed_model"] == "gpt-5.5"
        assert payload["retry"]["retry_model"] == "claude"
        assert payload["execution"]["planned_model"] == "claude"
        assert payload["execution"]["status"] == "finished"

        executions = load_executions(tmp_path)
        assert len(executions) == 2
        assert executions[0]["status"] == "retry_queued"
        assert executions[1]["retry_source_execution_id"] == executions[0]["execution_id"]
    finally:
        handle.close()


def test_run_dispatch_api_blocks_when_bridge_confirmation_is_pending(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    create_model(
        None,
        "gpt-5.5-coder",
        "GPT 5.5 Coder",
        "openai",
        True,
        1,
        ["complex_coding"],
        "https://api.openai.com/v1",
        None,
        "需要本地路由",
        None,
    )
    monkeypatch.setattr(ccswitch_core, "open_ccswitch_deeplink", lambda deeplink: None)
    monkeypatch.setattr(ccswitch_core, "launch_command_in_terminal", lambda command, app="Terminal": {"opened": True, "app": app, "command": command})
    monkeypatch.setattr(ccswitch_core.time, "sleep", lambda seconds: None)
    create_executor(
        None,
        "dispatch-bridge-cli",
        label="Dispatch Bridge CLI",
        kind="command",
        enabled=True,
        rank=1,
        binary="python3",
        args=["-c", "print('ok')", "{prompt}"],
        timeout_seconds=30,
        pass_model_as_flag=False,
        env={},
    )
    handle = start_web_server(tmp_path, port=0)
    try:
        request_json(handle.url, "/api/init", method="POST", payload={"name": "demo", "type": "web-app"})
        request_json(handle.url, "/api/tasks", method="POST", payload={"title": "修复登录报错", "priority": "high"})
        task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
        request_json(handle.url, "/api/run/manual", method="POST", payload={"task_id": task["id"], "model": "gpt-5.5-coder", "start": True})
        request_json(handle.url, "/api/run/attach", method="POST", payload={"task_id": task["id"], "executor_id": "codex-cli", "session_id": "session-xyz"})
        request_json(handle.url, "/api/ccswitch/bridge", method="POST", payload={"task_id": task["id"], "app": "codex", "open": True})

        status_code, payload = request_json(
            handle.url,
            "/api/run/dispatch",
            method="POST",
            payload={"executor_id": "dispatch-bridge-cli"},
        )
        assert status_code == 201
        assert payload["dispatched"] is False
        assert "待确认的 bridge" in payload["reason"]
    finally:
        handle.close()


def test_run_dispatch_api_can_auto_confirm_bridge_signal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    create_model(
        None,
        "gpt-5.5-coder",
        "GPT 5.5 Coder",
        "openai",
        True,
        1,
        ["complex_coding"],
        "https://api.openai.com/v1",
        None,
        "需要本地路由",
        None,
    )
    monkeypatch.setattr(ccswitch_core, "open_ccswitch_deeplink", lambda deeplink: None)
    monkeypatch.setattr(ccswitch_core, "launch_command_in_terminal", lambda command, app="Terminal": {"opened": True, "app": app, "command": command})
    monkeypatch.setattr(ccswitch_core.time, "sleep", lambda seconds: None)

    handle = start_web_server(tmp_path, port=0)
    try:
        request_json(handle.url, "/api/init", method="POST", payload={"name": "demo", "type": "web-app"})
        request_json(handle.url, "/api/tasks", method="POST", payload={"title": "修复登录报错", "priority": "high"})
        task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
        request_json(handle.url, "/api/run/manual", method="POST", payload={"task_id": task["id"], "model": "gpt-5.5-coder", "start": True})
        request_json(handle.url, "/api/run/attach", method="POST", payload={"task_id": task["id"], "executor_id": "codex-cli", "session_id": "session-xyz"})
        bridge_status, bridge_payload = request_json(handle.url, "/api/ccswitch/bridge", method="POST", payload={"task_id": task["id"], "app": "codex", "open": True})
        assert bridge_status == 201
        signal_path = tmp_path / bridge_payload["bridge"]["resume_signal_path"]
        signal_path.write_text(json.dumps({"started_at": "2026-07-02T12:00:00"}, ensure_ascii=False), encoding="utf-8")

        status_code, payload = request_json(
            handle.url,
            "/api/run/dispatch",
            method="POST",
            payload={"auto_confirm_bridge_signal": True},
        )
        assert status_code == 201
        assert payload["progressed"] is True
        assert payload["dispatched"] is False
        assert payload["auto_confirmed_bridge"] is True
        assert payload["execution"]["ccswitch_bridge_confirmation_status"] == "confirmed_ready"
        assert payload["execution"]["ccswitch_bridge_confirmation_note"] == "Auto-confirmed from bridge resume signal."
        assert payload["scheduler_after"]["next_action"] == "monitor_running"
    finally:
        handle.close()


def test_run_sessions_api_returns_historical_candidates(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    create_executor(
        None,
        "history-cli",
        label="History CLI",
        kind="command",
        enabled=True,
        rank=1,
        binary="python3",
        args=["-c", "print('ok')", "{prompt}"],
        timeout_seconds=30,
        pass_model_as_flag=False,
        env={},
        resume_args=["resume", "{session_ref}"],
        continue_args=["resume", "--last"],
        resume_in_project_root=True,
        session_ref_label="session_id",
    )
    handle = start_web_server(tmp_path, port=0)
    try:
        request_json(handle.url, "/api/init", method="POST", payload={"name": "demo", "type": "web-app"})
        request_json(handle.url, "/api/tasks", method="POST", payload={"title": "修复登录报错", "priority": "high"})
        request_json(handle.url, "/api/tasks", method="POST", payload={"title": "继续修复登录报错", "priority": "high"})
        tasks = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"]
        first_task = tasks[0]
        second_task = tasks[1]
        request_json(handle.url, "/api/run/execute", method="POST", payload={"task_id": first_task["id"], "executor_id": "history-cli"})
        request_json(
            handle.url,
            "/api/run/attach",
            method="POST",
            payload={"task_id": first_task["id"], "executor_id": "history-cli", "session_id": "session-old"},
        )
        request_json(handle.url, "/api/run/execute", method="POST", payload={"task_id": second_task["id"], "executor_id": "history-cli"})

        status_code, sessions_payload = request_json(handle.url, f"/api/run/sessions/{second_task['id']}?limit=5")
        assert status_code == 200
        assert sessions_payload["sessions"][0]["session_ref"] == "session-old"
        assert sessions_payload["sessions"][0]["executor_id"] == "history-cli"

        status_code, resume_payload = request_json(
            handle.url,
            "/api/run/resume",
            method="POST",
            payload={"task_id": second_task["id"], "history_fallback": True},
        )
        assert status_code == 201
        assert resume_payload["mode"] == "history"
        assert resume_payload["session_ref"] == "session-old"
    finally:
        handle.close()


def test_executor_library_cli_lists_defaults(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    assert main(["executor", "reset"]) == 0
    assert main(["executor", "list"]) == 0
    output = capsys.readouterr().out
    assert "manual [manual]" in output
    assert "codex-cli [command]" in output
    assert load_executor_library()


def test_executor_doctor_cli_reports_runtime(monkeypatch, capsys) -> None:
    monkeypatch.setattr(executors_core.shutil, "which", lambda binary: f"/usr/local/bin/{binary}" if binary == "codex" else None)

    def fake_run(command, capture_output, text, timeout, check):
        class Result:
            returncode = 0
            stdout = "codex 1.2.3"
            stderr = ""
        return Result()

    monkeypatch.setattr(executors_core.subprocess, "run", fake_run)
    assert main(["executor", "doctor", "codex-cli"]) == 0
    output = capsys.readouterr().out
    assert "codex-cli: available" in output
    assert "healthcheck: ok" in output


def test_model_doctor_cli_reports_provider_auth_readiness(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")

    assert main(["model", "doctor", "gpt-5.5"]) == 0
    output = capsys.readouterr().out
    assert "gpt-5.5: ready" in output
    assert "auth_status: ready" in output
    assert "auth_env_vars: OPENAI_API_KEY" in output
    assert "provider_config: ready" in output


def test_model_probe_cli_records_provider_handshake(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")

    class FakeResponse:
        status = 401

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(models_core, "urlopen", lambda request, timeout=3.0: FakeResponse())

    assert main(["model", "probe", "gpt-5.5"]) == 0
    output = capsys.readouterr().out
    assert "gpt-5.5: ok" in output

    assert main(["model", "doctor", "gpt-5.5"]) == 0
    output = capsys.readouterr().out
    assert "handshake_status: ok" in output
    assert "handshake_http_status: 401" in output


def test_status_cli_reports_provider_readiness(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    main(["--root", str(tmp_path), "init", "--name", "demo"])

    assert main(["--root", str(tmp_path), "status"]) == 0
    output = capsys.readouterr().out
    assert "Providers:" in output
    assert "Handshake:" in output
    assert "ready /" in output
    assert "Usage:" in output
    assert "Policy:" in output


def test_plan_draft_api_create_confirm_and_delete(tmp_path: Path) -> None:
    handle = start_web_server(tmp_path, port=0)
    try:
        request_json(handle.url, "/api/init", method="POST", payload={"name": "demo", "type": "web-app"})
        goal = "开发会员积分系统，包含积分获取、积分扣减、明细查询和后台管理"
        status_code, preview_payload = request_json(
            handle.url,
            "/api/tasks/plan",
            method="POST",
            payload={"goal": goal, "priority": "high"},
        )
        assert status_code == 201
        draft_id = preview_payload["draft_id"]
        assert draft_id.startswith("DRAFT-")
        assert preview_payload["tasks"][2]["depends_on_task_ids"] == ["design"]

        status_code, draft_payload = request_json(handle.url, f"/api/task-plans/{draft_id}")
        assert status_code == 200
        assert draft_payload["draft"]["draft_id"] == draft_id

        status_code, confirm_payload = request_json(
            handle.url,
            "/api/tasks/plan",
            method="POST",
            payload={"goal": goal, "priority": "high", "confirm": True, "draft_id": draft_id},
        )
        assert status_code == 201
        assert confirm_payload["tasks"][0]["id"].startswith("TASK-")
        assert confirm_payload["tasks"][2]["depends_on_task_ids"]

        request = Request(f"{handle.url}/api/task-plans/{draft_id}", method="DELETE")
        with urlopen(request) as response:
            assert response.status == 200
    finally:
        handle.close()
