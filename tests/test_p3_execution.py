from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen

from aios.core.executors import create_executor, load_executor_library
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
    updated_task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    assert updated_task["status"] == "running"


def test_run_auto_cli_dispatches_first_ready_task(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    (tmp_path / ".aios" / "context.md").write_text("# 项目上下文\n\n正式背景。\n", encoding="utf-8")
    (tmp_path / ".aios" / "architecture.md").write_text("# 架构说明\n\n正式架构。\n", encoding="utf-8")
    (tmp_path / "service.py").write_text("print('ok')\n", encoding="utf-8")
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
