from __future__ import annotations

import json
from pathlib import Path
from urllib.request import urlopen

import aios.core.ccswitch as ccswitch_core
from aios.core.scheduler import scheduler_summary
from aios.core.runtime_policy import save_runtime_policy
from aios.core.webapp import start_web_server
from aios.main import main
from aios.core.models import create_model


def test_scheduler_summary_tracks_ready_blocked_and_review_pending(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    (tmp_path / ".aios" / "context.md").write_text("# 项目上下文\n\n正式背景。\n", encoding="utf-8")
    (tmp_path / ".aios" / "architecture.md").write_text("# 架构说明\n\n正式架构。\n", encoding="utf-8")
    (tmp_path / "service.py").write_text("print('ok')\n", encoding="utf-8")
    main(["--root", str(tmp_path), "scan"])
    main(["--root", str(tmp_path), "task", "plan", "开发会员积分系统", "--priority", "high"])

    tasks = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"]
    summary = scheduler_summary(tmp_path)
    assert summary["ready_count"] >= 1
    assert summary["blocked_count"] >= 1
    scope_task = next(task for task in tasks if task["title"] == "梳理系统范围与模块边界：会员积分系统")
    design_task = next(task for task in tasks if task["title"] == "设计核心数据与接口：会员积分系统")
    items = {item["task_id"]: item for item in summary["items"]}
    assert items[scope_task["id"]]["scheduler_state"] == "ready"
    assert items[design_task["id"]]["scheduler_state"] == "blocked"


def test_scheduler_summary_marks_review_pending_after_executor_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    (tmp_path / ".aios" / "context.md").write_text("# 项目上下文\n\n正式背景。\n", encoding="utf-8")
    (tmp_path / ".aios" / "architecture.md").write_text("# 架构说明\n\n正式架构。\n", encoding="utf-8")
    (tmp_path / "doc.md").write_text("# hi\n", encoding="utf-8")
    main(["--root", str(tmp_path), "scan"])
    main(["--root", str(tmp_path), "task", "create", "更新说明文档", "--priority", "medium"])
    task = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    main(
        [
            "--root",
            str(tmp_path),
            "executor",
            "create",
            "mock-scheduler",
            "--label",
            "Mock Scheduler",
            "--kind",
            "command",
            "--binary",
            "python3",
            "--arg=-c",
            "--arg=print('ok')",
            "--arg={prompt}",
        ]
    )
    main(["--root", str(tmp_path), "run", task["id"], "--executor", "mock-scheduler"])
    summary = scheduler_summary(tmp_path)
    assert summary["review_pending_count"] == 1
    assert summary["next_action"] == "review_finish"


def test_scheduler_summary_marks_bridge_confirmation_as_blocking_state(tmp_path: Path, monkeypatch) -> None:
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

    summary = scheduler_summary(tmp_path)
    item = summary["items"][0]
    assert item["scheduler_state"] == "bridge_confirmation"
    assert item["next_action"] == "confirm_bridge"
    assert item["bridge_confirmation_status"] == "pending_confirmation"
    assert summary["bridge_pending_count"] == 1
    assert summary["next_action"] == "confirm_bridge"


def test_scheduler_uses_signal_detected_when_resume_signal_exists(tmp_path: Path, monkeypatch) -> None:
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

    execution = json.loads((tmp_path / ".aios" / "executions.json").read_text(encoding="utf-8"))["executions"][0]
    signal_path = tmp_path / execution["ccswitch_bridge_resume_signal_path"]
    signal_path.write_text(json.dumps({"started_at": "2026-07-02T12:00:00"}, ensure_ascii=False), encoding="utf-8")

    summary = scheduler_summary(tmp_path)
    item = summary["items"][0]
    assert item["scheduler_state"] == "bridge_confirmation"
    assert item["next_action"] == "validate_resumed_session"
    assert item["bridge_confirmation_status"] == "signal_detected"
    assert item["bridge_resume_signal_status"] == "started"
    assert summary["next_action"] == "validate_resumed_session"


def test_scheduler_api_is_visible_in_web_ui(tmp_path: Path) -> None:
    handle = start_web_server(tmp_path, port=0)
    try:
        status = urlopen(f"{handle.url}/assets/app.js").read().decode("utf-8")
        assert "schedulerCard" in status
        assert "自动推进下一步" in urlopen(f"{handle.url}/").read().decode("utf-8")
        assert 'id="metricReady"' in urlopen(f"{handle.url}/").read().decode("utf-8")
    finally:
        handle.close()


def test_scheduler_blocks_ready_task_when_budget_policy_is_exceeded(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    (tmp_path / ".aios" / "context.md").write_text("# 项目上下文\n\n正式背景。\n", encoding="utf-8")
    (tmp_path / ".aios" / "architecture.md").write_text("# 架构说明\n\n正式架构。\n", encoding="utf-8")
    (tmp_path / "service.py").write_text("print('ok')\n", encoding="utf-8")
    main(["--root", str(tmp_path), "scan"])
    main(["--root", str(tmp_path), "task", "create", "实现登录功能", "--priority", "high"])
    save_runtime_policy(
        tmp_path,
        {
            "max_total_estimated_cost": 0.000001,
            "max_single_execution_cost": None,
            "block_on_unpriced_model": True,
            "dispatch_strategy": "default",
            "cost_currency": "USD",
        },
    )

    summary = scheduler_summary(tmp_path)
    item = summary["items"][0]
    assert item["scheduler_state"] == "blocked"
    assert item["next_action"] == "adjust_budget"
    assert "预算" in item["reason"]


def test_scheduler_uses_cheapest_first_strategy_for_ready_tasks(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    (tmp_path / ".aios" / "context.md").write_text("# 项目上下文\n\n正式背景。\n", encoding="utf-8")
    (tmp_path / ".aios" / "architecture.md").write_text("# 架构说明\n\n正式架构。\n", encoding="utf-8")
    (tmp_path / "service.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# docs\n", encoding="utf-8")
    main(["--root", str(tmp_path), "scan"])
    main(["--root", str(tmp_path), "task", "create", "更新说明文档", "--priority", "medium"])
    main(["--root", str(tmp_path), "task", "create", "实现登录功能", "--priority", "high"])
    save_runtime_policy(
        tmp_path,
        {
            "max_total_estimated_cost": None,
            "max_single_execution_cost": None,
            "block_on_unpriced_model": False,
            "dispatch_strategy": "cheapest_first",
            "cost_currency": "USD",
        },
    )
    create_model(
        None,
        "cheap-model",
        "Cheap Model",
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
        "expensive-model",
        "Expensive Model",
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
    tasks[0]["recommended_model"] = "cheap-model"
    tasks[1]["recommended_model"] = "expensive-model"
    (tmp_path / ".aios" / "tasks.json").write_text(json.dumps({"tasks": tasks}, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = scheduler_summary(tmp_path)
    assert summary["dispatch_strategy"] == "cheapest_first"
    assert summary["next_task_id"] == tasks[0]["id"]
