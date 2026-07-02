from __future__ import annotations

import json
from pathlib import Path
from urllib.request import urlopen

from aios.core.scheduler import scheduler_summary
from aios.core.webapp import start_web_server
from aios.main import main


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


def test_scheduler_api_is_visible_in_web_ui(tmp_path: Path) -> None:
    handle = start_web_server(tmp_path, port=0)
    try:
        status = urlopen(f"{handle.url}/assets/app.js").read().decode("utf-8")
        assert "schedulerCard" in status
        assert "自动推进下一步" in urlopen(f"{handle.url}/").read().decode("utf-8")
        assert 'id="metricReady"' in urlopen(f"{handle.url}/").read().decode("utf-8")
    finally:
        handle.close()
