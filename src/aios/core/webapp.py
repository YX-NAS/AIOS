from __future__ import annotations

import json
import mimetypes
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from aios.core.context_builder import build_context_pack
from aios.core.scoring import load_scores, model_score_summary, save_score
from aios.core.handoff import build_handoff
from aios.core.models import model_summary
from aios.core.paths import aios_path
from aios.core.project import initialize_project
from aios.core.router import log_routing, route_task
from aios.core.scanner import scan_project
from aios.core.tasks import create_task, get_task, load_tasks, plan_goal
from aios.core.workflow import finalize_task
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
                if parsed.path.startswith("/api/tasks/"):
                    task_id = parsed.path.rsplit("/", 1)[-1]
                    return self._send_json({"task": get_task(self.project_root, task_id)})
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
                if parsed.path == "/api/handoffs":
                    return self._send_json({"handoffs": list_handoffs(self.project_root)})
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
                    planned = plan_goal(
                        self.project_root,
                        goal,
                        payload.get("priority", "high"),
                        create=bool(payload.get("confirm")),
                    )
                    return self._send_json(
                        {
                            "message": "Goal split completed.",
                            "tasks": planned,
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
                if parsed.path == "/api/complete":
                    summary = (payload.get("summary") or "").strip()
                    if not summary:
                        raise ValueError("Completion summary is required.")
                    task = finalize_task(self.project_root, payload["task_id"], summary)
                    score = payload.get("score")
                    if score is not None:
                        save_score(self.project_root, task["id"], task.get("recommended_model", "unknown"), int(score), payload.get("score_note"), task.get("type"))
                    return self._send_json({"message": "Task completed.", "task": task})
                self._send_error(HTTPStatus.NOT_FOUND, "Not found")
            except FileNotFoundError as exc:
                self._send_error(HTTPStatus.NOT_FOUND, str(exc))
            except KeyError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, f"Missing field: {exc.args[0]}")
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))

        def log_message(self, format: str, *args: object) -> None:
            return

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


def list_packs(root: Path) -> list[dict]:
    pack_dir = aios_path(root) / "context-packs"
    if not pack_dir.exists():
        return []
    packs = []
    for path in sorted(pack_dir.glob("*.md"), reverse=True):
        packs.append(
            {
                "name": path.name,
                "path": str(path.relative_to(root)),
                "size_bytes": path.stat().st_size,
                "task_id": pack_task_id(path.name),
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
    return {
        "name": pack_name,
        "path": str(path.relative_to(root)),
        "content": path.read_text(encoding="utf-8"),
        "task_id": pack_task_id(pack_name),
    }


def pack_task_id(pack_name: str) -> str | None:
    if not pack_name.startswith("TASK-"):
        return None
    parts = pack_name.split("-")
    if len(parts) < 3:
        return None
    return "-".join(parts[:3])
from urllib.parse import urlparse, parse_qs
