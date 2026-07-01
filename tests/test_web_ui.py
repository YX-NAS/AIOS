from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen

from aios.core.webapp import start_web_server


def request_json(base_url: str, path: str, method: str = "GET", payload: dict | None = None) -> tuple[int, dict]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    with urlopen(request) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_web_ui_flow(tmp_path: Path) -> None:
    handle = start_web_server(tmp_path, port=0)
    try:
        status_code, status_payload = request_json(handle.url, "/api/status")
        assert status_code == 200
        assert status_payload["initialized"] is False

        status_code, init_payload = request_json(
            handle.url,
            "/api/init",
            method="POST",
            payload={"name": "demo", "type": "web-app"},
        )
        assert status_code == 201
        assert init_payload["status"]["initialized"] is True

        (tmp_path / "main.py").write_text("print('demo')\n", encoding="utf-8")
        status_code, scan_payload = request_json(handle.url, "/api/scan", method="POST", payload={})
        assert status_code == 200
        assert scan_payload["report"]["summary"]["file_count"] >= 1

        status_code, task_payload = request_json(
            handle.url,
            "/api/tasks",
            method="POST",
            payload={"title": "实现登录功能", "priority": "high"},
        )
        assert status_code == 201
        task_id = task_payload["task"]["id"]

        status_code, planned_payload = request_json(
            handle.url,
            "/api/tasks/plan",
            method="POST",
            payload={"goal": "完成聊天接口时间上下文修复", "priority": "high"},
        )
        assert status_code == 201
        assert len(planned_payload["tasks"]) >= 3
        assert planned_payload["tasks"][0]["recommended_model"]

        status_code, route_payload = request_json(handle.url, f"/api/route/{task_id}")
        assert status_code == 200
        assert route_payload["route"]["recommended_model"] == "gpt-5.5"

        status_code, pack_payload = request_json(
            handle.url,
            "/api/pack",
            method="POST",
            payload={"task_id": task_id, "model": "gpt-5.5"},
        )
        assert status_code == 201
        assert pack_payload["path"].endswith(".md")

        status_code, pack_by_task_payload = request_json(handle.url, f"/api/packs/by-task/{task_id}")
        assert status_code == 200
        assert "AIOS Context Pack" in pack_by_task_payload["pack"]["content"]
        assert "实现登录功能" in pack_by_task_payload["pack"]["display_name"]

        status_code, handoff_payload = request_json(
            handle.url,
            "/api/handoff",
            method="POST",
            payload={"task_id": task_id, "model": "gpt-5.5"},
        )
        assert status_code == 201
        assert handoff_payload["handoff"]["handoff_path"].endswith("-handoff.md")
        assert "Manual execution steps" in handoff_payload["handoff"]["content"]

        pack_name = pack_by_task_payload["pack"]["name"]
        status_code, packs_payload = request_json(handle.url, "/api/packs")
        assert status_code == 200
        assert any("实现登录功能" in pack["display_name"] for pack in packs_payload["packs"])
        status_code, pack_content_payload = request_json(handle.url, f"/api/packs/content/{pack_name}")
        assert status_code == 200
        assert pack_content_payload["pack"]["name"] == pack_name

        status_code, complete_payload = request_json(
            handle.url,
            "/api/complete",
            method="POST",
            payload={
                "task_id": task_id,
                "summary": "完成登录功能并验证通过",
                "actual_model": "gpt-5.5",
                "test_command": "pytest -q",
                "test_result": "all passed",
                "score": 5,
                "score_note": "一次通过",
            },
        )
        assert status_code == 200
        assert complete_payload["task"]["status"] == "done"
        changelog = (tmp_path / ".aios" / "changelog.md").read_text(encoding="utf-8")
        assert "实际执行模型：gpt-5.5" in changelog
        assert "测试命令：pytest -q" in changelog
        assert "测试结果：all passed" in changelog

        with urlopen(f"{handle.url}/") as response:
            html = response.read().decode("utf-8")
        assert "AIOS Web UI" in html
        assert 'id="taskPagination"' in html
        assert 'id="packPagination"' in html

        with urlopen(f"{handle.url}/assets/app.js") as response:
            js = response.read().decode("utf-8")
        assert "const ITEMS_PER_PAGE = 10;" in js
        assert "renderPagination(elements.taskPagination" in js
        assert "renderPagination(elements.packPagination" in js
    finally:
        handle.close()
