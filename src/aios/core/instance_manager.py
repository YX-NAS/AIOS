from __future__ import annotations

import hashlib
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
PORT_SEARCH_WINDOW = 30


def state_dir() -> Path:
    return Path(os.environ.get("AIOS_STATE_DIR", str(Path.home() / ".aios-local")))


def ensure_state_dir() -> Path:
    path = state_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def project_id_for_root(root: Path) -> str:
    resolved = str(root.expanduser().resolve())
    digest = hashlib.sha1(resolved.encode("utf-8")).hexdigest()[:12]
    return f"proj-{digest}"


def instance_files(project_id: str) -> dict[str, Path]:
    base = ensure_state_dir()
    return {
        "pid": base / f"{project_id}.pid",
        "port": base / f"{project_id}.port",
        "log": base / f"{project_id}.log",
    }


def is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_instance_pid(project_id: str) -> int | None:
    path = instance_files(project_id)["pid"]
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def read_instance_port(project_id: str) -> int | None:
    path = instance_files(project_id)["port"]
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def cleanup_instance_files(project_id: str) -> None:
    for path in instance_files(project_id).values():
        if path.exists():
            path.unlink()


def find_free_port(host: str = DEFAULT_HOST, start: int = DEFAULT_PORT) -> int:
    for port in range(start, start + PORT_SEARCH_WINDOW):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError("No free port found in the local range.")


def wait_until_ready(url: str, pid: int, timeout_seconds: float = 10.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not is_pid_running(pid):
            return False
        try:
            with urlopen(f"{url}/api/status", timeout=0.5) as response:
                if response.status == 200:
                    return True
        except URLError:
            pass
        time.sleep(0.25)
    return False


def instance_status(root: Path, project_id: str, host: str = DEFAULT_HOST) -> dict:
    pid = read_instance_pid(project_id)
    port = read_instance_port(project_id)
    running = bool(pid and is_pid_running(pid))
    if not running and pid is not None:
        cleanup_instance_files(project_id)
        pid = None
        port = None
    root_exists = root.exists()
    status = "missing" if not root_exists else "running" if running else "stopped"
    url = f"http://{host}:{port}" if running and port else None
    return {
        "project_id": project_id,
        "root": str(root),
        "pid": pid,
        "port": port,
        "running": running,
        "status": status,
        "url": url,
        "log_path": str(instance_files(project_id)["log"]),
    }


def start_project_instance(root: Path, project_id: str, host: str = DEFAULT_HOST, start_port: int = DEFAULT_PORT) -> dict:
    root = root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Project root does not exist: {root}")

    current = instance_status(root, project_id, host)
    if current["running"]:
        return current

    files = instance_files(project_id)
    port = find_free_port(host, start_port)
    log_file = files["log"].open("ab")
    process = subprocess.Popen(
        [sys.executable, "-m", "aios.main", "--root", str(root), "web", "--host", host, "--port", str(port)],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    files["pid"].write_text(str(process.pid), encoding="utf-8")
    files["port"].write_text(str(port), encoding="utf-8")
    url = f"http://{host}:{port}"
    if not wait_until_ready(url, process.pid):
        stop_project_instance(project_id)
        raise RuntimeError(f"AIOS Web UI did not become ready in time. Check log: {files['log']}")
    return instance_status(root, project_id, host)


def stop_project_instance(project_id: str) -> None:
    pid = read_instance_pid(project_id)
    if pid and is_pid_running(pid):
        os.kill(pid, signal.SIGTERM)
        for _ in range(20):
            if not is_pid_running(pid):
                break
            time.sleep(0.1)
        if is_pid_running(pid):
            os.kill(pid, signal.SIGKILL)
    cleanup_instance_files(project_id)
