from __future__ import annotations

import subprocess
import sys


SUPPORTED_MAC_APPS = {"Terminal"}


def launch_command_in_terminal(command: str, app: str = "Terminal") -> dict:
    resolved_command = str(command or "").strip()
    if not resolved_command:
        raise ValueError("Terminal command is required.")

    resolved_app = str(app or "Terminal").strip() or "Terminal"
    if sys.platform != "darwin":
        raise ValueError("Terminal auto-launch is currently supported on macOS only.")
    if resolved_app not in SUPPORTED_MAC_APPS:
        supported = ", ".join(sorted(SUPPORTED_MAC_APPS))
        raise ValueError(f"Unsupported terminal app: {resolved_app}. Supported apps: {supported}")

    script_command = _escape_applescript_string(resolved_command)
    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                f'tell application "{resolved_app}" to activate',
                "-e",
                f'tell application "{resolved_app}" to do script "{script_command}"',
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip() or "unknown error"
        raise ValueError(f"Failed to open terminal command in {resolved_app}: {detail}") from exc
    return {
        "opened": True,
        "app": resolved_app,
        "command": resolved_command,
        "platform": sys.platform,
    }


def _escape_applescript_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
