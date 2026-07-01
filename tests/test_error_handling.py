"""P0-1 + P0-3: Error path tests for CLI and Web API."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from aios.core.webapp import start_web_server
from aios.main import main


# ---- CLI error paths ----


def test_scan_before_init_returns_error(tmp_path: Path) -> None:
    import pytest
    with pytest.raises(SystemExit) as exc_info:
        main(["--root", str(tmp_path), "scan"])
    assert exc_info.value.code == 2


def test_route_nonexistent_task_returns_error(tmp_path: Path) -> None:
    import pytest
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    with pytest.raises(SystemExit) as exc_info:
        main(["--root", str(tmp_path), "route", "TASK-99999999-999"])
    assert exc_info.value.code == 2


def test_pack_nonexistent_task_returns_error(tmp_path: Path) -> None:
    import pytest
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    with pytest.raises(SystemExit) as exc_info:
        main(["--root", str(tmp_path), "pack", "TASK-99999999-999", "--model", "gpt-5.5"])
    assert exc_info.value.code == 2


def test_complete_nonexistent_task_returns_error(tmp_path: Path) -> None:
    import pytest
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    with pytest.raises(SystemExit) as exc_info:
        main(["--root", str(tmp_path), "complete", "TASK-99999999-999", "--summary", "x"])
    assert exc_info.value.code == 2


def test_init_twice_without_force_returns_error(tmp_path: Path) -> None:
    import pytest
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    with pytest.raises(SystemExit) as exc_info:
        main(["--root", str(tmp_path), "init", "--name", "demo"])
    assert exc_info.value.code == 2


def test_task_show_nonexistent_returns_error(tmp_path: Path) -> None:
    import pytest
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    with pytest.raises(SystemExit) as exc_info:
        main(["--root", str(tmp_path), "task", "show", "TASK-99999999-999"])
    assert exc_info.value.code == 2


# ---- Web API error paths ----


def request_json(base_url: str, path: str, method: str = "GET", payload: dict | None = None) -> tuple[int, dict]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = json.loads(exc.read().decode("utf-8"))
        return exc.code, body


def test_api_route_missing_task_returns_error(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    handle = start_web_server(tmp_path, port=0)
    try:
        status, body = request_json(handle.url, "/api/route/TASK-99999999-999")
        assert status == 400
        assert "error" in body
    finally:
        handle.close()


def test_api_pack_missing_task_id_returns_400(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    handle = start_web_server(tmp_path, port=0)
    try:
        status, body = request_json(handle.url, "/api/pack", method="POST", payload={"model": "gpt-5.5"})
        assert status == 400
        assert "error" in body
    finally:
        handle.close()


def test_api_complete_missing_summary_returns_400(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    handle = start_web_server(tmp_path, port=0)
    try:
        status, body = request_json(handle.url, "/api/complete", method="POST", payload={"task_id": "TASK-99999999-999"})
        assert status == 400
        assert "error" in body
    finally:
        handle.close()


def test_api_create_task_empty_title_returns_400(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    handle = start_web_server(tmp_path, port=0)
    try:
        status, body = request_json(handle.url, "/api/tasks", method="POST", payload={"title": "  ", "priority": "high"})
        assert status == 400
        assert "error" in body
    finally:
        handle.close()


def test_api_plan_empty_goal_returns_400(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    handle = start_web_server(tmp_path, port=0)
    try:
        status, body = request_json(handle.url, "/api/tasks/plan", method="POST", payload={"goal": "", "priority": "high"})
        assert status == 400
        assert "error" in body
    finally:
        handle.close()


def test_api_unknown_path_returns_404(tmp_path: Path) -> None:
    handle = start_web_server(tmp_path, port=0)
    try:
        status, body = request_json(handle.url, "/api/nonexistent")
        assert status == 404
        assert "error" in body
    finally:
        handle.close()
