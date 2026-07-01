from __future__ import annotations

import json
from pathlib import Path

from aios.core.models import create_model, delete_model, load_model_library, save_model_library
from aios.main import main


def test_init_creates_aios_files(tmp_path: Path) -> None:
    assert main(["--root", str(tmp_path), "init", "--name", "demo", "--type", "web-app"]) == 0

    aios_dir = tmp_path / ".aios"
    assert (aios_dir / "project.yaml").exists()
    assert (aios_dir / "context.md").exists()
    assert (aios_dir / "tasks.json").exists()
    assert (aios_dir / "task-plans.json").exists()
    assert (aios_dir / "executions.json").exists()
    assert (aios_dir / "model-routing.json").exists()
    assert (aios_dir / "context-packs").is_dir()
    assert (aios_dir / "handoffs").is_dir()


def test_scan_ignores_build_directories(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "skip.js").write_text("bad\n", encoding="utf-8")

    assert main(["--root", str(tmp_path), "scan"]) == 0

    index = json.loads((tmp_path / ".aios" / "file-index.json").read_text(encoding="utf-8"))
    paths = [item["path"] for item in index["files"]]
    assert "src/app.py" in paths
    assert "node_modules/skip.js" not in paths


def test_task_route_pack_and_complete_flow(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    (tmp_path / "main.py").write_text("print('hello')\n", encoding="utf-8")
    main(["--root", str(tmp_path), "scan"])

    assert main(["--root", str(tmp_path), "task", "create", "实现登录功能", "--priority", "high"]) == 0
    tasks = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"]
    task = tasks[0]
    assert task["id"].startswith("TASK-")
    assert task["type"] == "complex_coding"

    assert main(["--root", str(tmp_path), "route", task["id"]]) == 0
    assert main(["--root", str(tmp_path), "pack", task["id"], "--model", "gpt-5.5"]) == 0
    assert (tmp_path / ".aios" / "context-packs" / f"{task['id']}-gpt-5.5.md").exists()
    assert main(["--root", str(tmp_path), "handoff", task["id"], "--model", "gpt-5.5"]) == 0
    handoff_path = tmp_path / ".aios" / "handoffs" / f"{task['id']}-gpt-5.5-handoff.md"
    assert handoff_path.exists()
    handoff_content = handoff_path.read_text(encoding="utf-8")
    assert "AIOS Task Handoff" in handoff_content
    assert "## Context Pack" in handoff_content

    assert main(["--root", str(tmp_path), "complete", task["id"], "--summary", "完成登录功能"]) == 0
    updated = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"][0]
    assert updated["status"] == "done"
    assert "完成登录功能" in (tmp_path / ".aios" / "changelog.md").read_text(encoding="utf-8")


def test_task_plan_splits_time_state_bug_into_detailed_tasks(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    goal = (
        "今天的夏栀，这个时间状态没有根据真实的时间更新，比如已经10点多了，还在起床的状态，"
        "而不是工作的状态，夏栀的人生流状态应该同步到完整项目中，而不是跟随几小时以前的对话内容继续承接。"
    )

    assert main(["--root", str(tmp_path), "task", "plan", goal, "--priority", "high"]) == 0

    tasks = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"]
    assert len(tasks) == 5
    assert tasks[0]["type"] == "bug_fix"
    assert tasks[0]["title"].startswith("梳理现象与影响范围：")
    assert tasks[1]["title"].startswith("排查时间锚点与承接逻辑：")
    assert tasks[2]["title"].startswith("修复时间状态同步：")
    assert tasks[3]["type"] == "testing"
    assert tasks[4]["type"] == "documentation"
    assert "状态根据当前真实时间更新" in tasks[2]["acceptance_criteria"]
    assert tasks[1]["parent_task_id"] == tasks[0]["id"]
    assert tasks[2]["depends_on_task_ids"] == [tasks[1]["id"]]


def test_task_plan_splits_system_goal_into_module_tasks(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    goal = "开发会员积分系统，包含积分获取、积分扣减、明细查询和后台管理"

    assert main(["--root", str(tmp_path), "task", "plan", goal, "--priority", "high"]) == 0

    tasks = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"]
    titles = [task["title"] for task in tasks]
    assert len(tasks) == 8
    assert titles[0] == "梳理系统范围与模块边界：会员积分系统"
    assert titles[1] == "设计核心数据与接口：会员积分系统"
    assert "实现积分获取：会员积分系统" in titles
    assert "实现积分扣减：会员积分系统" in titles
    assert "实现明细查询：会员积分系统" in titles
    assert "实现后台管理：会员积分系统" in titles
    admin_task = next(task for task in tasks if task["title"] == "实现后台管理：会员积分系统")
    assert admin_task["type"] == "ui_design"
    design_task = next(task for task in tasks if task["title"] == "设计核心数据与接口：会员积分系统")
    testing_task = next(task for task in tasks if task["title"] == "补充测试与验收：会员积分系统")
    assert admin_task["depends_on_task_ids"] == [design_task["id"]]
    assert len(testing_task["depends_on_task_ids"]) == 4


def test_task_plan_splits_short_system_goal_into_system_stages(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    goal = "开发会员积分系统"

    assert main(["--root", str(tmp_path), "task", "plan", goal, "--priority", "high"]) == 0

    tasks = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"]
    titles = [task["title"] for task in tasks]
    assert len(tasks) == 5
    assert titles[0] == "梳理系统范围与模块边界：会员积分系统"
    assert titles[1] == "设计核心数据与接口：会员积分系统"
    assert titles[2] == "实现核心能力：会员积分系统"
    assert titles[3] == "补充测试与验收：会员积分系统"
    assert titles[4] == "更新文档与交付记录：会员积分系统"


def test_task_plan_draft_cli_roundtrip(tmp_path: Path, capsys) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    goal = "开发会员积分系统，包含积分获取、积分扣减、明细查询和后台管理"

    assert main(["--root", str(tmp_path), "task", "plan", goal, "--priority", "high", "--draft"]) == 0
    drafts = json.loads((tmp_path / ".aios" / "task-plans.json").read_text(encoding="utf-8"))["drafts"]
    assert len(drafts) == 1
    draft_id = drafts[0]["draft_id"]
    assert drafts[0]["status"] == "draft"
    assert main(["--root", str(tmp_path), "task", "draft", "confirm", draft_id]) == 0
    tasks = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"]
    assert len(tasks) == 8
    updated_drafts = json.loads((tmp_path / ".aios" / "task-plans.json").read_text(encoding="utf-8"))["drafts"]
    assert updated_drafts[0]["status"] == "confirmed"
    assert any(task.get("plan_draft_id") == draft_id for task in tasks)


def test_task_create_uses_global_model_library_recommendation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    models = load_model_library()
    for model in models:
        if model["id"] == "claude":
            model["enabled"] = True
            model["rank"] = 1
            model["task_types"] = ["bug_fix"]
        elif model["id"] == "gpt-5.5":
            model["rank"] = 9
    save_model_library(None, models)

    assert main(["--root", str(tmp_path), "task", "create", "修复登录报错", "--priority", "high"]) == 0
    tasks = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"]
    assert tasks[0]["recommended_model"] == "claude"


def test_task_create_falls_back_after_custom_model_deleted(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_STATE_DIR", str(tmp_path / ".state"))
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    create_model(None, "custom-bug", "Custom Bug", "custom", True, 1, ["bug_fix"])
    delete_model(None, "claude")
    delete_model(None, "gpt-5.5")
    delete_model(None, "deepseek-v4-pro")

    assert main(["--root", str(tmp_path), "task", "create", "修复登录报错", "--priority", "high"]) == 0
    tasks = json.loads((tmp_path / ".aios" / "tasks.json").read_text(encoding="utf-8"))["tasks"]
    assert tasks[0]["recommended_model"] == "custom-bug"
