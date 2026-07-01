"""P2-4: Token estimation tests."""

from __future__ import annotations

from pathlib import Path

from aios.core.context_builder import build_context_pack, estimate_tokens
from aios.main import main


def test_estimate_tokens_chinese_text() -> None:
    text = "\u8fd9\u662f\u4e00\u4e2a\u4e2d\u6587\u6d4b\u8bd5\u6587\u672c"
    tokens = estimate_tokens(text)
    # 10 Chinese chars * 1.5 = 15
    assert 10 <= tokens <= 20


def test_estimate_tokens_english_code() -> None:
    text = "def hello_world():\n    print('hello')\n    return True"
    tokens = estimate_tokens(text)
    # ~55 chars * 0.25 = ~14 tokens
    assert 10 <= tokens <= 25


def test_pack_returns_token_estimate(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    main(["--root", str(tmp_path), "task", "create", "test task"])
    import json
    tasks = json.loads((tmp_path / ".aios" / "tasks.json").read_text())["tasks"]
    task_id = tasks[0]["id"]

    from aios.core.tasks import get_task
    task = get_task(tmp_path, task_id)
    result = build_context_pack(tmp_path, task, "deepseek-v4-pro")

    assert "token_estimate" in result
    assert "context_window" in result
    assert "window_usage_pct" in result
    assert result["token_estimate"] > 0
    assert result["context_window"] == 128000
    assert 0 < result["window_usage_pct"] < 100
    assert result["path"].exists()
    content = result["path"].read_text(encoding="utf-8")
    assert "## 任务层" in content
    assert "## 项目层" in content
    assert "## 文件层" in content


def test_pack_warns_on_large_context(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    main(["--root", str(tmp_path), "task", "create", "test task"])
    import json
    tasks = json.loads((tmp_path / ".aios" / "tasks.json").read_text())["tasks"]
    from aios.core.tasks import get_task
    task = get_task(tmp_path, tasks[0]["id"])
    result = build_context_pack(tmp_path, task, "minimax-m2.7-highspeed")
    assert result["context_window"] == 32000
    assert result["quality"] == "ok"
    assert any("placeholder" in warning.lower() for warning in result["warnings"])


def test_pack_no_warning_within_window(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    main(["--root", str(tmp_path), "task", "create", "test task"])
    (tmp_path / ".aios" / "context.md").write_text("# 项目上下文\n\n正式背景。\n", encoding="utf-8")
    (tmp_path / ".aios" / "architecture.md").write_text("# 架构说明\n\n正式架构说明。\n", encoding="utf-8")
    import json
    tasks = json.loads((tmp_path / ".aios" / "tasks.json").read_text())["tasks"]
    from aios.core.tasks import get_task
    task = get_task(tmp_path, tasks[0]["id"])
    result = build_context_pack(tmp_path, task, "gpt-5.5")
    assert result["context_window"] == 200000
    assert result["warning"] is None
    assert result["window_usage_pct"] < 10
    assert result["quality"] == "ok"


def test_models_include_context_window(tmp_path: Path) -> None:
    from aios.core.models import load_model_library
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    models = load_model_library(tmp_path)
    gpt = next(m for m in models if m["id"] == "gpt-5.5")
    assert gpt["context_window"] == 200000
    deepseek = next(m for m in models if m["id"] == "deepseek-v4-pro")
    assert deepseek["context_window"] == 128000
