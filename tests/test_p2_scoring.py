"""P2-1: Model scoring tests."""

from __future__ import annotations

import json
from pathlib import Path

from aios.core.scoring import load_scores, model_score_summary, save_score
from aios.main import main


def test_complete_with_score_writes_model_scores(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    main(["--root", str(tmp_path), "task", "create", "实现登录功能", "--priority", "high"])
    tasks = json.loads((tmp_path / ".aios" / "tasks.json").read_text())["tasks"]
    task_id = tasks[0]["id"]

    main(["--root", str(tmp_path), "complete", task_id, "--summary", "done", "--score", "4", "--score-note", "一次通过"])

    scores = load_scores(tmp_path)
    assert len(scores) == 1
    assert scores[0]["task_id"] == task_id
    assert scores[0]["score"] == 4
    assert scores[0]["note"] == "一次通过"
    assert scores[0]["model"]
    assert scores[0]["task_type"] == "complex_coding"


def test_complete_without_score_does_not_create_file(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    main(["--root", str(tmp_path), "task", "create", "test task"])
    tasks = json.loads((tmp_path / ".aios" / "tasks.json").read_text())["tasks"]
    main(["--root", str(tmp_path), "complete", tasks[0]["id"], "--summary", "done"])

    assert not (tmp_path / ".aios" / "model-scores.json").exists()


def test_save_score_direct(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    save_score(tmp_path, "TASK-001", "gpt-5.5", 5, "excellent", "complex_coding")
    save_score(tmp_path, "TASK-002", "gpt-5.5", 3, "", "complex_coding")
    save_score(tmp_path, "TASK-003", "deepseek-v4-pro", 4, "good", "simple_coding")

    scores = load_scores(tmp_path)
    assert len(scores) == 3


def test_model_score_summary(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    save_score(tmp_path, "TASK-001", "gpt-5.5", 5, None, "complex_coding")
    save_score(tmp_path, "TASK-002", "gpt-5.5", 3, None, "complex_coding")
    save_score(tmp_path, "TASK-003", "gpt-5.5", 4, None, "bug_fix")
    save_score(tmp_path, "TASK-004", "deepseek-v4-pro", 4, None, "simple_coding")

    summary = model_score_summary(tmp_path)
    assert summary["total_entries"] == 4
    assert len(summary["models"]) == 2

    gpt = next(m for m in summary["models"] if m["model"] == "gpt-5.5")
    assert gpt["total_scores"] == 3
    assert gpt["avg_score"] == 4.0
    assert "complex_coding" in gpt["by_task_type"]
    assert gpt["by_task_type"]["complex_coding"]["avg_score"] == 4.0

    deepseek = next(m for m in summary["models"] if m["model"] == "deepseek-v4-pro")
    assert deepseek["total_scores"] == 1
    assert deepseek["avg_score"] == 4.0


def test_model_score_summary_filter_by_model(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    save_score(tmp_path, "TASK-001", "gpt-5.5", 5, None, "complex_coding")
    save_score(tmp_path, "TASK-002", "deepseek-v4-pro", 4, None, "simple_coding")

    summary = model_score_summary(tmp_path, model_id="gpt-5.5")
    assert len(summary["models"]) == 1
    assert summary["models"][0]["model"] == "gpt-5.5"


def test_invalid_score_raises(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    import pytest
    with pytest.raises(ValueError):
        save_score(tmp_path, "TASK-001", "gpt-5.5", 6, None, "complex_coding")


def test_api_scores_endpoints(tmp_path: Path) -> None:
    import json as _json
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
    from aios.core.webapp import start_web_server

    def req(path, method="GET", payload=None):
        data = None
        headers = {}
        if payload is not None:
            data = _json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        r = Request(f"{handle.url}{path}", data=data, headers=headers, method=method)
        with urlopen(r) as resp:
            return resp.status, _json.loads(resp.read().decode())

    main(["--root", str(tmp_path), "init", "--name", "demo"])
    handle = start_web_server(tmp_path, port=0)
    try:
        _, task_payload = req("/api/tasks", method="POST", payload={"title": "test scoring", "priority": "high"})
        task_id = task_payload["task"]["id"]

        req("/api/complete", method="POST", payload={"task_id": task_id, "summary": "done", "score": 4})

        _, scores_payload = req("/api/scores")
        assert len(scores_payload["scores"]) == 1
        assert scores_payload["scores"][0]["score"] == 4

        _, summary_payload = req("/api/scores/summary")
        assert summary_payload["total_entries"] == 1
    finally:
        handle.close()
