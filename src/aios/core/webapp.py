from __future__ import annotations

import json
import mimetypes
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from aios.core.ccswitch import build_ccswitch_deeplink, export_ccswitch_payload
from aios.core.context_builder import build_context_pack
from aios.core.dispatch import auto_progress_next_step
from aios.core.executors import executor_summary
from aios.core.executions import execution_summary, finish_manual_execution, latest_execution_for_task, prepare_manual_execution
from aios.core.executions import run_executor_with_auto_finish
from aios.core.scoring import load_scores, model_score_summary
from aios.core.handoff import build_handoff
from aios.core.models import model_summary
from aios.core.paths import aios_path
from aios.core.project import initialize_project
from aios.core.router import log_routing, route_task
from aios.core.scanner import scan_project
from aios.core.scheduler import scheduler_summary
from aios.core.tasks import (
    confirm_plan_draft,
    create_plan_draft,
    create_task,
    delete_plan_draft,
    get_plan_draft,
    get_task,
    list_plan_drafts,
    load_tasks,
    plan_goal,
)
from aios.utils.json_utils import read_json


ASSET_DIR = Path(__file__).resolve().parent.parent / "web"


@dataclass
class WebServerHandle:
    server: ThreadingHTTPServer
    thread: threading.Thread
    url: str

    def close(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()


def start_web_server(root: Path, host: str = "127.0.0.1", port: int = 8765) -> WebServerHandle:
    class AIOSWebHandler(BaseHTTPRequestHandler):
        project_root = root

        def do_GET(self) -> None:  # noqa: N802
            try:
                parsed = urlparse(self.path)
                if parsed.path == "/":
                    return self._serve_asset("index.html")
                if parsed.path.startswith("/assets/"):
                    return self._serve_asset(parsed.path.removeprefix("/assets/"))
                if parsed.path == "/api/status":
                    return self._send_json(self._status_payload())
                if parsed.path == "/api/tasks":
                    return self._send_json({"tasks": load_tasks_safe(self.project_root)})
                if parsed.path == "/api/scheduler":
                    return self._send_json(scheduler_summary(self.project_root))
                if parsed.path == "/api/task-plans":
                    return self._send_json({"drafts": list_plan_drafts(self.project_root)})
                if parsed.path.startswith("/api/task-plans/"):
                    draft_id = parsed.path.rsplit("/", 1)[-1]
                    return self._send_json({"draft": get_plan_draft(self.project_root, draft_id)})
                if parsed.path.startswith("/api/tasks/"):
                    task_id = parsed.path.rsplit("/", 1)[-1]
                    return self._send_json(
                        {
                            "task": get_task(self.project_root, task_id),
                            "execution": latest_execution_for_task(self.project_root, task_id),
                        }
                    )
                if parsed.path.startswith("/api/run/task/"):
                    task_id = parsed.path.rsplit("/", 1)[-1]
                    return self._send_json({"execution": latest_execution_for_task(self.project_root, task_id)})
                if parsed.path.startswith("/api/route/"):
                    task_id = parsed.path.rsplit("/", 1)[-1]
                    route = route_task(get_task(self.project_root, task_id), self.project_root)
                    log_routing(self.project_root, route)
                    return self._send_json({"route": route})
                if parsed.path == "/api/scores/summary":
                    qs = parse_qs(parsed.query)
                    model_filter = qs.get("model", [None])[0]
                    return self._send_json(model_score_summary(self.project_root, model_filter))
                if parsed.path == "/api/scores":
                    return self._send_json({"scores": load_scores(self.project_root)})
                if parsed.path == "/api/packs":
                    return self._send_json({"packs": list_packs(self.project_root)})
                if parsed.path == "/api/executors":
                    return self._send_json(executor_summary())
                if parsed.path == "/api/handoffs":
                    return self._send_json({"handoffs": list_handoffs(self.project_root)})
                if parsed.path == "/api/ccswitch/export":
                    self._send_error(HTTPStatus.NOT_FOUND, "Not found")
                    return
                if parsed.path.startswith("/api/packs/by-task/"):
                    task_id = parsed.path.rsplit("/", 1)[-1]
                    pack = get_pack_for_task(self.project_root, task_id)
                    return self._send_json({"pack": pack})
                if parsed.path.startswith("/api/packs/content/"):
                    pack_name = parsed.path.rsplit("/", 1)[-1]
                    pack = get_pack_content(self.project_root, pack_name)
                    return self._send_json({"pack": pack})
                self._send_error(HTTPStatus.NOT_FOUND, "Not found")
            except FileNotFoundError as exc:
                self._send_error(HTTPStatus.NOT_FOUND, str(exc))
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))

        def do_POST(self) -> None:  # noqa: N802
            try:
                parsed = urlparse(self.path)
                payload = self._read_json()
                if parsed.path == "/api/init":
                    if aios_path(self.project_root).exists():
                        return self._send_json(
                            {
                                "message": "AIOS project already initialized.",
                                "created": [],
                                "status": self._status_payload(),
                            }
                        )
                    created = initialize_project(
                        self.project_root,
                        payload.get("name") or self.project_root.name,
                        payload.get("type") or "software-project",
                        bool(payload.get("force")),
                    )
                    return self._send_json(
                        {
                            "message": "AIOS project initialized.",
                            "created": [str(path.relative_to(self.project_root)) for path in created],
                            "status": self._status_payload(),
                        },
                        status=HTTPStatus.CREATED,
                    )
                if parsed.path == "/api/scan":
                    report = scan_project(self.project_root)
                    return self._send_json({"message": "Project scanned.", "report": report})
                if parsed.path == "/api/tasks":
                    title = (payload.get("title") or "").strip()
                    if not title:
                        raise ValueError("Task title is required.")
                    task = create_task(
                        self.project_root,
                        title,
                        payload.get("priority", "medium"),
                        payload.get("acceptance") or None,
                    )
                    return self._send_json({"message": "Task created.", "task": task}, status=HTTPStatus.CREATED)
                if parsed.path == "/api/tasks/plan":
                    goal = (payload.get("goal") or "").strip()
                    if not goal:
                        raise ValueError("Goal is required.")
                    if payload.get("confirm"):
                        draft_id = (payload.get("draft_id") or "").strip()
                        planned = confirm_plan_draft(self.project_root, draft_id) if draft_id else plan_goal(
                            self.project_root,
                            goal,
                            payload.get("priority", "high"),
                            create=True,
                        )
                        return self._send_json(
                            {
                                "message": "Goal split completed.",
                                "draft_id": draft_id or None,
                                "tasks": planned,
                            },
                            status=HTTPStatus.CREATED,
                        )
                    draft = create_plan_draft(
                        self.project_root,
                        goal,
                        payload.get("priority", "high"),
                    )
                    return self._send_json(
                        {
                            "message": "Goal split draft created.",
                            "draft_id": draft["draft_id"],
                            "draft": draft,
                            "tasks": draft["tasks"],
                        },
                        status=HTTPStatus.CREATED,
                    )
                if parsed.path == "/api/pack":
                    task = get_task(self.project_root, payload["task_id"])
                    model = payload.get("model") or task["recommended_model"]
                    result = build_context_pack(self.project_root, task, model)
                    return self._send_json(
                        {
                            "message": "Context pack created.",
                            "path": str(result["path"].relative_to(self.project_root)),
                            "token_estimate": result["token_estimate"],
                            "context_window": result["context_window"],
                            "window_usage_pct": result["window_usage_pct"],
                            "warning": result["warning"],
                            "warnings": result["warnings"],
                            "quality": result["quality"],
                            "relevant_file_count": len(result["relevant_files"]),
                        },
                        status=HTTPStatus.CREATED,
                    )
                if parsed.path == "/api/handoff":
                    handoff = build_handoff(
                        self.project_root,
                        payload["task_id"],
                        payload.get("model") or None,
                        bool(payload.get("refresh_pack")),
                    )
                    return self._send_json(
                        {
                            "message": "Task handoff created.",
                            "handoff": handoff,
                        },
                        status=HTTPStatus.CREATED,
                    )
                if parsed.path == "/api/ccswitch/export":
                    result = export_ccswitch_payload(
                        self.project_root,
                        payload["task_id"],
                        model=(payload.get("model") or "").strip() or None,
                    )
                    return self._send_json(
                        {
                            "message": "ccswitch payload exported.",
                            "export_path": result["export_path"],
                            "payload": result["payload"],
                            "execution": result["execution"],
                        },
                        status=HTTPStatus.CREATED,
                    )
                if parsed.path == "/api/ccswitch/deeplink":
                    result = build_ccswitch_deeplink(
                        self.project_root,
                        payload["task_id"],
                        app=(payload.get("app") or "codex").strip() or "codex",
                        model=(payload.get("model") or "").strip() or None,
                        open_link=bool(payload.get("open")),
                    )
                    return self._send_json(
                        {
                            "message": "ccswitch deeplink generated.",
                            **result,
                        },
                        status=HTTPStatus.CREATED,
                    )
                if parsed.path == "/api/run/manual":
                    result = prepare_manual_execution(
                        self.project_root,
                        payload["task_id"],
                        payload.get("model") or None,
                        bool(payload.get("refresh_pack")),
                        bool(payload.get("start")),
                        (payload.get("note") or "").strip() or None,
                    )
                    return self._send_json(
                        {
                            "message": "Manual execution prepared.",
                            "task": result["task"],
                            "route": result["route"],
                            "handoff": result["handoff"],
                            "execution": result["execution"],
                        },
                        status=HTTPStatus.CREATED,
                    )
                if parsed.path == "/api/run/execute":
                    result = run_executor_with_auto_finish(
                        self.project_root,
                        payload["task_id"],
                        payload["executor_id"],
                        (payload.get("model") or "").strip() or None,
                        bool(payload.get("refresh_pack")),
                        (payload.get("note") or "").strip() or None,
                        bool(payload.get("auto_finish")),
                        (payload.get("summary") or "").strip() or None,
                        (payload.get("actual_model") or "").strip() or None,
                        (payload.get("verify_command") or "").strip() or None,
                        int(payload["score"]) if payload.get("score") is not None else None,
                        (payload.get("score_note") or "").strip() or None,
                        bool(payload.get("auto_commit")),
                        bool(payload.get("auto_push")),
                        (payload.get("push_remote") or "origin").strip() or "origin",
                        bool(payload.get("allow_protected_push")),
                        bool(payload.get("auto_pr")),
                        (payload.get("pr_base_branch") or "main").strip() or "main",
                    )
                    return self._send_json(
                        {
                            "message": "Executor finished.",
                            "task": result["task"],
                            "route": result["route"],
                            "handoff": result["handoff"],
                            "execution": result["execution"],
                            "executor": result["executor"],
                            "auto_finished": result.get("auto_finished"),
                            "verification": result.get("verification"),
                            "reason": result.get("reason"),
                            "git_commit": result.get("git_commit"),
                            "git_push": result.get("git_push"),
                            "git_pr": result.get("git_pr"),
                        },
                        status=HTTPStatus.CREATED,
                    )
                if parsed.path == "/api/run/dispatch":
                    result = auto_progress_next_step(
                        self.project_root,
                        executor_id=(payload.get("executor_id") or "").strip() or None,
                        model=(payload.get("model") or "").strip() or None,
                        refresh_pack=bool(payload.get("refresh_pack")),
                        note=(payload.get("note") or "").strip() or None,
                        auto_finish=bool(payload.get("auto_finish")),
                        summary=(payload.get("summary") or "").strip() or None,
                        actual_model=(payload.get("actual_model") or "").strip() or None,
                        verify_command=(payload.get("verify_command") or "").strip() or None,
                        score=int(payload["score"]) if payload.get("score") is not None else None,
                        score_note=(payload.get("score_note") or "").strip() or None,
                        auto_commit=bool(payload.get("auto_commit")),
                        auto_push=bool(payload.get("auto_push")),
                        push_remote=(payload.get("push_remote") or "origin").strip() or "origin",
                        allow_protected_push=bool(payload.get("allow_protected_push")),
                        auto_pr=bool(payload.get("auto_pr")),
                        pr_base_branch=(payload.get("pr_base_branch") or "main").strip() or "main",
                    )
                    return self._send_json(
                        {
                            "message": "Task progressed." if result["progressed"] else "No dispatchable task.",
                            **result,
                        },
                        status=HTTPStatus.CREATED,
                    )
                if parsed.path == "/api/run/finish":
                    summary = (payload.get("summary") or "").strip()
                    if not summary:
                        raise ValueError("Completion summary is required.")
                    result = finish_manual_execution(
                        self.project_root,
                        payload["task_id"],
                        summary,
                        actual_model=(payload.get("actual_model") or "").strip() or None,
                        test_command=(payload.get("test_command") or "").strip() or None,
                        test_result=(payload.get("test_result") or "").strip() or None,
                        score=int(payload["score"]) if payload.get("score") is not None else None,
                        score_note=(payload.get("score_note") or "").strip() or None,
                        auto_commit=bool(payload.get("auto_commit")),
                        auto_push=bool(payload.get("auto_push")),
                        push_remote=(payload.get("push_remote") or "origin").strip() or "origin",
                        allow_protected_push=bool(payload.get("allow_protected_push")),
                        auto_pr=bool(payload.get("auto_pr")),
                        pr_base_branch=(payload.get("pr_base_branch") or "main").strip() or "main",
                    )
                    return self._send_json({"message": "Task completed.", **result})
                if parsed.path == "/api/complete":
                    summary = (payload.get("summary") or "").strip()
                    if not summary:
                        raise ValueError("Completion summary is required.")
                    result = finish_manual_execution(
                        self.project_root,
                        payload["task_id"],
                        summary,
                        actual_model=(payload.get("actual_model") or "").strip() or None,
                        test_command=(payload.get("test_command") or "").strip() or None,
                        test_result=(payload.get("test_result") or "").strip() or None,
                        score=int(payload["score"]) if payload.get("score") is not None else None,
                        score_note=(payload.get("score_note") or "").strip() or None,
                        auto_commit=bool(payload.get("auto_commit")),
                        auto_push=bool(payload.get("auto_push")),
                        push_remote=(payload.get("push_remote") or "origin").strip() or "origin",
                        allow_protected_push=bool(payload.get("allow_protected_push")),
                        auto_pr=bool(payload.get("auto_pr")),
                        pr_base_branch=(payload.get("pr_base_branch") or "main").strip() or "main",
                    )
                    return self._send_json({"message": "Task completed.", **result})
                self._send_error(HTTPStatus.NOT_FOUND, "Not found")
            except FileNotFoundError as exc:
                self._send_error(HTTPStatus.NOT_FOUND, str(exc))
            except KeyError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, f"Missing field: {exc.args[0]}")
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))

        def log_message(self, format: str, *args: object) -> None:
            return

        def do_DELETE(self) -> None:  # noqa: N802
            try:
                parsed = urlparse(self.path)
                if parsed.path.startswith("/api/task-plans/"):
                    draft_id = parsed.path.rsplit("/", 1)[-1]
                    delete_plan_draft(self.project_root, draft_id)
                    return self._send_json({"message": "Draft deleted."})
                self._send_error(HTTPStatus.NOT_FOUND, "Not found")
            except FileNotFoundError as exc:
                self._send_error(HTTPStatus.NOT_FOUND, str(exc))
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))

        def _status_payload(self) -> dict:
            aios_dir = aios_path(self.project_root)
            initialized = aios_dir.exists()
            tasks = load_tasks_safe(self.project_root) if initialized else []
            file_index = read_json(aios_dir / "file-index.json", {}) if initialized else {}
            summary = file_index.get("summary", {})
            return {
                "initialized": initialized,
                "root": str(self.project_root),
                "aios_dir": str(aios_dir),
                "task_count": len(tasks),
                "open_tasks": len([task for task in tasks if task["status"] != "done"]),
                "done_tasks": len([task for task in tasks if task["status"] == "done"]),
                "file_count": summary.get("file_count", 0),
                "languages": summary.get("languages", []),
                "frameworks": summary.get("frameworks", []),
                "packs": list_packs(self.project_root) if initialized else [],
                "handoffs": list_handoffs(self.project_root) if initialized else [],
                "enabled_model_count": model_summary()["enabled_model_count"],
                "enabled_executor_count": executor_summary()["enabled_executor_count"],
                **(scheduler_summary(self.project_root) if initialized else scheduler_summary_empty()),
                **(execution_summary(self.project_root) if initialized else execution_summary_empty()),
            }

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            if length == 0:
                return {}
            raw = self.rfile.read(length)
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))

        def _serve_asset(self, relative: str) -> None:
            asset = ASSET_DIR / relative
            if not asset.exists() or not asset.is_file():
                self._send_error(HTTPStatus.NOT_FOUND, "Asset not found")
                return
            mime = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
            body = asset.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_error(self, status: HTTPStatus, message: str) -> None:
            self._send_json({"error": message}, status=status)

    server = ThreadingHTTPServer((host, port), AIOSWebHandler)
    actual_host, actual_port = server.server_address[:2]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return WebServerHandle(server=server, thread=thread, url=f"http://{actual_host}:{actual_port}")


def load_tasks_safe(root: Path) -> list[dict]:
    try:
        return load_tasks(root)
    except FileNotFoundError:
        return []


def execution_summary_empty() -> dict:
    return {
        "execution_count": 0,
        "active_execution_count": 0,
        "latest_execution_status": None,
        "last_execution_updated_at": None,
    }


def scheduler_summary_empty() -> dict:
    return {
        "ready_count": 0,
        "blocked_count": 0,
        "review_pending_count": 0,
        "failed_count": 0,
        "active_count": 0,
        "next_task_id": None,
        "next_task_title": None,
        "next_action": None,
        "items": [],
    }


def list_packs(root: Path) -> list[dict]:
    pack_dir = aios_path(root) / "context-packs"
    if not pack_dir.exists():
        return []
    tasks_by_id = {task["id"]: task for task in load_tasks_safe(root)}
    packs = []
    for path in sorted(pack_dir.glob("*.md"), reverse=True):
        task_id = pack_task_id(path.name)
        task = tasks_by_id.get(task_id) if task_id else None
        packs.append(
            {
                "name": path.name,
                "display_name": f"{task['title']} ({path.name})" if task else path.name,
                "path": str(path.relative_to(root)),
                "size_bytes": path.stat().st_size,
                "task_id": task_id,
                "task_title": task.get("title") if task else None,
            }
        )
    return packs


def list_handoffs(root: Path) -> list[dict]:
    handoff_dir = aios_path(root) / "handoffs"
    if not handoff_dir.exists():
        return []
    handoffs = []
    for path in sorted(handoff_dir.glob("*.md"), reverse=True):
        handoffs.append(
            {
                "name": path.name,
                "path": str(path.relative_to(root)),
                "size_bytes": path.stat().st_size,
                "task_id": pack_task_id(path.name),
            }
        )
    return handoffs


def get_pack_for_task(root: Path, task_id: str) -> dict:
    packs = [pack for pack in list_packs(root) if pack.get("task_id") == task_id]
    if not packs:
        raise FileNotFoundError(f"No context pack found for task: {task_id}")
    return get_pack_content(root, packs[0]["name"])


def get_pack_content(root: Path, pack_name: str) -> dict:
    path = aios_path(root) / "context-packs" / pack_name
    if not path.exists():
        raise FileNotFoundError(f"Context pack not found: {pack_name}")
    task_id = pack_task_id(pack_name)
    task = next((item for item in load_tasks_safe(root) if item["id"] == task_id), None) if task_id else None
    return {
        "name": pack_name,
        "display_name": f"{task['title']} ({pack_name})" if task else pack_name,
        "path": str(path.relative_to(root)),
        "content": path.read_text(encoding="utf-8"),
        "task_id": task_id,
        "task_title": task.get("title") if task else None,
    }


def pack_task_id(pack_name: str) -> str | None:
    if not pack_name.startswith("TASK-"):
        return None
    parts = pack_name.split("-")
    if len(parts) < 3:
        return None
    return "-".join(parts[:3])
from urllib.parse import urlparse, parse_qs
