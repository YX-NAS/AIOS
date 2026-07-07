from __future__ import annotations

import json
import mimetypes
import subprocess
import sys
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from aios.core.instance_manager import DEFAULT_HOST, start_project_instance, stop_project_instance
from aios.core.models import create_model, delete_model, model_summary, probe_models, reset_model_library, update_model
from aios.core.scanner import scan_project
from aios.core.projects import (
    get_project,
    launcher_workbench_summary,
    list_project_summaries,
    production_project_candidates,
    project_summary,
    register_project,
    update_project,
)
from aios.utils.text import now_iso


ASSET_DIR = Path(__file__).resolve().parent.parent / "launcher"


def pick_project_directory() -> str | None:
    if sys.platform == "darwin":
        command = [
            "osascript",
            "-e",
            'POSIX path of (choose folder with prompt "选择要接入 AIOS 的项目目录")',
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip().lower()
            stdout = (completed.stdout or "").strip().lower()
            cancelled_tokens = ("cancel", "canceled", "user canceled", "execution error")
            if any(token in stderr for token in cancelled_tokens) or any(token in stdout for token in cancelled_tokens):
                return None
            message = (completed.stderr or completed.stdout or "Failed to pick project directory").strip()
            raise RuntimeError(message)
        return (completed.stdout or "").strip() or None

    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(title="选择要接入 AIOS 的项目目录")
        root.destroy()
        return selected or None
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Folder picker is not available on this platform: {exc}") from exc


@dataclass
class LauncherServerHandle:
    server: ThreadingHTTPServer
    thread: threading.Thread
    url: str

    def close(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()


def start_launcher_server(host: str = DEFAULT_HOST, port: int = 8755) -> LauncherServerHandle:
    class LauncherHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            try:
                parsed = urlparse(self.path)
                if parsed.path == "/":
                    return self._serve_asset("index.html")
                if parsed.path.startswith("/assets/"):
                    return self._serve_asset(parsed.path.removeprefix("/assets/"))
                if parsed.path == "/api/projects":
                    return self._send_json({"projects": list_project_summaries()})
                if parsed.path == "/api/workbench":
                    return self._send_json({"workbench": launcher_workbench_summary()})
                if parsed.path == "/api/production-projects":
                    return self._send_json({"projects": production_project_candidates()})
                if parsed.path == "/api/models":
                    return self._send_json(model_summary())
                if parsed.path.startswith("/api/projects/") and parsed.path.endswith("/status"):
                    project_id = parsed.path.split("/")[3]
                    return self._send_json({"project": project_summary(get_project(project_id))})
                self._send_error(HTTPStatus.NOT_FOUND, "Not found")
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))

        def do_POST(self) -> None:  # noqa: N802
            try:
                parsed = urlparse(self.path)
                payload = self._read_json()
                if parsed.path == "/api/projects":
                    root = (payload.get("root") or "").strip()
                    if not root:
                        raise ValueError("Project root is required.")
                    project = register_project(Path(root), (payload.get("name") or "").strip() or None)
                    return self._send_json({"project": project_summary(project)}, status=HTTPStatus.CREATED)
                if parsed.path == "/api/projects/pick-folder":
                    root = pick_project_directory()
                    return self._send_json({"root": root})
                if parsed.path == "/api/models/update":
                    current_model_id = (payload.get("current_model_id") or payload.get("model_id") or "").strip()
                    model_id = (payload.get("model_id") or "").strip()
                    task_types = payload.get("task_types") or []
                    model = update_model(
                        None,
                        current_model_id,
                        model_id,
                        (payload.get("label") or "").strip() or None,
                        (payload.get("provider") or "").strip() or None,
                        bool(payload.get("enabled")),
                        int(payload.get("rank", 1)),
                        task_types,
                        (payload.get("endpoint") or "").strip() or None,
                        (payload.get("homepage") or "").strip() or None,
                        (payload.get("notes") or "").strip() or None,
                        (payload.get("config_url") or "").strip() or None,
                        payload.get("auth_env_vars") or None,
                        payload.get("input_cost_per_1m"),
                        payload.get("output_cost_per_1m"),
                        (payload.get("cost_currency") or "USD").strip() or "USD",
                    )
                    return self._send_json({"message": "Model updated.", "model": model})
                if parsed.path == "/api/models/create":
                    task_types = payload.get("task_types") or []
                    model = create_model(
                        None,
                        (payload.get("model_id") or "").strip(),
                        (payload.get("label") or "").strip() or None,
                        (payload.get("provider") or "").strip() or None,
                        bool(payload.get("enabled", True)),
                        int(payload.get("rank", 1)),
                        task_types,
                        (payload.get("endpoint") or "").strip() or None,
                        (payload.get("homepage") or "").strip() or None,
                        (payload.get("notes") or "").strip() or None,
                        (payload.get("config_url") or "").strip() or None,
                        payload.get("auth_env_vars") or None,
                        payload.get("input_cost_per_1m"),
                        payload.get("output_cost_per_1m"),
                        (payload.get("cost_currency") or "USD").strip() or "USD",
                    )
                    return self._send_json({"message": "Model created.", "model": model}, status=HTTPStatus.CREATED)
                if parsed.path == "/api/models/delete":
                    model_id = (payload.get("model_id") or "").strip()
                    if not model_id:
                        raise ValueError("Model ID is required.")
                    models = delete_model(None, model_id)
                    return self._send_json({"message": "Model deleted.", "models": models})
                if parsed.path == "/api/models/reset":
                    models = reset_model_library()
                    return self._send_json({"message": "Model library reset.", "models": models})
                if parsed.path == "/api/models/probe":
                    results = probe_models(
                        None,
                        (payload.get("model_id") or "").strip() or None,
                        timeout_seconds=float(payload.get("timeout") or 3.0),
                    )
                    return self._send_json(
                        {
                            "message": "Model provider probe completed.",
                            "results": results,
                            **model_summary(),
                        }
                    )
                if parsed.path == "/api/projects/open":
                    project_id = payload.get("project_id")
                    if not project_id:
                        raise ValueError("Project ID is required.")
                    project = get_project(project_id)
                    runtime = start_project_instance(Path(project["root"]), project_id)
                    project = update_project(
                        project_id,
                        last_opened_at=now_iso(),
                        last_port=runtime["port"],
                        status=runtime["status"],
                        initialized=Path(project["root"], ".aios").exists(),
                    )
                    return self._send_json({"project": project_summary(project), "url": runtime["url"]})
                if parsed.path == "/api/projects/scan":
                    project_id = payload.get("project_id")
                    if not project_id:
                        raise ValueError("Project ID is required.")
                    project = get_project(project_id)
                    report = scan_project(Path(project["root"]))
                    project = update_project(project_id, initialized=Path(project["root"], ".aios").exists())
                    return self._send_json({"project": project_summary(project), "report": report})
                if parsed.path == "/api/projects/stop":
                    project_id = payload.get("project_id")
                    if not project_id:
                        raise ValueError("Project ID is required.")
                    stop_project_instance(project_id)
                    project = update_project(project_id, status="stopped")
                    return self._send_json({"project": project_summary(project)})
                self._send_error(HTTPStatus.NOT_FOUND, "Not found")
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
            except RuntimeError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))

        def log_message(self, format: str, *args: object) -> None:
            return

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

    server = ThreadingHTTPServer((host, port), LauncherHandler)
    actual_host, actual_port = server.server_address[:2]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return LauncherServerHandle(server=server, thread=thread, url=f"http://{actual_host}:{actual_port}")
