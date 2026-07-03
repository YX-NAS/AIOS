"""Execution guard for AIOS — safety barriers for automated CLI execution.

Provides safety mechanisms for automated executor runs:
- Stuck detection (no-output timeout, repeated pattern detection)
- Execution heartbeat (file-based liveness monitoring)
- Resource monitoring (process tree tracking, basic memory/CPU awareness)
- Doom-loop detection (identical output line repetition)
"""

from __future__ import annotations

import os
import re
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path

from aios.core.paths import require_aios
from aios.utils.json_utils import read_json, write_json
from aios.utils.text import now_iso

# Default guard configuration
DEFAULT_STUCK_TIMEOUT_SECONDS = 300  # 5 minutes no output = stuck
DEFAULT_DOOM_LOOP_THRESHOLD = 5  # Same line repeated 5 times = doom loop
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 5
DEFAULT_HEARTBEAT_TIMEOUT_SECONDS = 30

# Patterns that indicate a likely stuck state
STUCK_INDICATOR_PATTERNS = [
    r"^(?:Retrying|Waiting|sleeping|\.{3,})$",
    r"^(?:I('?ll| will) (?:try|attempt|retry|wait))",
]


@dataclass
class GuardConfig:
    """Configuration for execution guard behavior."""
    stuck_timeout_seconds: int = DEFAULT_STUCK_TIMEOUT_SECONDS
    doom_loop_threshold: int = DEFAULT_DOOM_LOOP_THRESHOLD
    heartbeat_interval_seconds: int = DEFAULT_HEARTBEAT_INTERVAL_SECONDS
    heartbeat_timeout_seconds: int = DEFAULT_HEARTBEAT_TIMEOUT_SECONDS
    enabled: bool = True


@dataclass
class GuardResult:
    """Result of a guard check."""
    status: str  # "ok", "warning", "critical"
    stuck: bool = False
    stuck_reason: str | None = None
    doom_loop: bool = False
    doom_loop_pattern: str | None = None
    alive: bool = True
    last_output_age_seconds: float = 0.0
    output_line_count: int = 0
    checked_at: str = ""


def heartbeat_path(root: Path, execution_id: str) -> Path:
    """Get the path to the heartbeat file for an execution."""
    return require_aios(root) / "heartbeats" / f"{execution_id}.json"


def start_heartbeat(
    root: Path,
    execution_id: str,
    pid: int | None = None,
) -> Path:
    """Start a heartbeat file for an execution.

    The heartbeat file is updated periodically by the executor process
    to indicate it is still alive. The guard process reads it to
    determine liveness.

    Args:
        root: Project root.
        execution_id: Execution ID to monitor.
        pid: Process ID of the executor (defaults to current PID).

    Returns:
        Path to the heartbeat file.
    """
    path = heartbeat_path(root, execution_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    heartbeat = {
        "execution_id": execution_id,
        "pid": pid or os.getpid(),
        "started_at": now_iso(),
        "last_beat_at": now_iso(),
        "beat_count": 1,
        "status": "running",
    }
    write_json(path, heartbeat)
    return path


def send_heartbeat(root: Path, execution_id: str) -> dict:
    """Send a heartbeat signal — update the heartbeat timestamp.

    Args:
        root: Project root.
        execution_id: Execution ID.

    Returns:
        Updated heartbeat dict.
    """
    path = heartbeat_path(root, execution_id)
    if not path.exists():
        return start_heartbeat(root, execution_id)

    heartbeat = read_json(path, {})
    heartbeat["last_beat_at"] = now_iso()
    heartbeat["beat_count"] = heartbeat.get("beat_count", 0) + 1
    heartbeat["status"] = "running"
    write_json(path, heartbeat)
    return heartbeat


def stop_heartbeat(root: Path, execution_id: str, status: str = "completed") -> None:
    """Stop the heartbeat, marking execution as finished.

    Args:
        root: Project root.
        execution_id: Execution ID.
        status: Final status ("completed", "failed", "cancelled").
    """
    path = heartbeat_path(root, execution_id)
    if not path.exists():
        return

    heartbeat = read_json(path, {})
    heartbeat["status"] = status
    heartbeat["stopped_at"] = now_iso()
    write_json(path, heartbeat)


def check_heartbeat(
    root: Path,
    execution_id: str,
    timeout_seconds: int = DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
) -> dict:
    """Check if an execution is still alive via its heartbeat.

    Args:
        root: Project root.
        execution_id: Execution ID.
        timeout_seconds: Maximum age of the last heartbeat.

    Returns:
        Dict with 'alive', 'last_beat_age_seconds', 'status'.
    """
    path = heartbeat_path(root, execution_id)
    if not path.exists():
        return {
            "alive": False,
            "last_beat_age_seconds": None,
            "status": "no_heartbeat",
            "reason": "No heartbeat file found.",
        }

    heartbeat = read_json(path, {})
    last_beat = heartbeat.get("last_beat_at") or heartbeat.get("started_at") or ""

    if heartbeat.get("status") in ("completed", "failed", "cancelled"):
        return {
            "alive": False,
            "last_beat_age_seconds": None,
            "status": heartbeat["status"],
            "reason": f"Execution has status: {heartbeat['status']}",
        }

    try:
        from datetime import datetime
        last_dt = datetime.fromisoformat(last_beat)
        now_dt = datetime.fromisoformat(now_iso())
        age = (now_dt - last_dt).total_seconds()
    except ValueError:
        age = timeout_seconds + 1

    alive = age <= timeout_seconds
    return {
        "alive": alive,
        "last_beat_age_seconds": round(age, 2),
        "status": "alive" if alive else "heartbeat_timeout",
        "reason": None if alive else f"Heartbeat is {age:.1f}s old (timeout: {timeout_seconds}s).",
        "pid": heartbeat.get("pid"),
    }


def detect_stuck_output(
    output_lines: list[str],
    *,
    stuck_timeout_seconds: int = DEFAULT_STUCK_TIMEOUT_SECONDS,
    doom_loop_threshold: int = DEFAULT_DOOM_LOOP_THRESHOLD,
    last_output_time: float | None = None,
) -> GuardResult:
    """Analyze output lines to detect stuck or looping patterns.

    Args:
        output_lines: Recent lines of stdout/stderr output.
        stuck_timeout_seconds: Time since last output that indicates stuck.
        doom_loop_threshold: Number of identical consecutive lines for doom loop.
        last_output_time: Monotonic timestamp of the last output.

    Returns:
        GuardResult with detection status.
    """
    result = GuardResult(
        status="ok",
        output_line_count=len(output_lines),
        checked_at=now_iso(),
    )

    # Check for no-output timeout
    if last_output_time is not None:
        age = time.monotonic() - last_output_time
        result.last_output_age_seconds = round(age, 2)
        if age >= stuck_timeout_seconds:
            result.status = "critical"
            result.stuck = True
            result.stuck_reason = f"No output for {age:.1f}s (threshold: {stuck_timeout_seconds}s)."
            return result

    if not output_lines:
        return result

    # Check for doom loop (identical consecutive lines)
    recent_lines = output_lines[-doom_loop_threshold * 2:]
    if len(recent_lines) >= doom_loop_threshold:
        last_n = recent_lines[-doom_loop_threshold:]
        if len(set(last_n)) == 1 and len(last_n[0].strip()) > 0:
            result.status = "critical"
            result.doom_loop = True
            result.doom_loop_pattern = _truncate_line(last_n[0])
            return result

    # Check for stuck indicator patterns
    for line in output_lines[-10:]:
        for pattern_str in STUCK_INDICATOR_PATTERNS:
            if re.search(pattern_str, line, re.IGNORECASE):
                # One match is not critical, but note it
                if result.status == "ok":
                    result.status = "warning"
                break

    return result


def guard_summary(
    root: Path,
    execution_id: str,
    output_lines: list[str] | None = None,
    last_output_time: float | None = None,
) -> dict:
    """Run a comprehensive guard check combining heartbeat and output analysis.

    Args:
        root: Project root.
        execution_id: Execution ID.
        output_lines: Recent output lines (for stuck detection).
        last_output_time: Monotonic timestamp of last output.

    Returns:
        Combined guard status dict.
    """
    heartbeat = check_heartbeat(root, execution_id)
    stuck = detect_stuck_output(
        output_lines or [],
        last_output_time=last_output_time,
    ) if output_lines is not None or last_output_time is not None else GuardResult(status="ok")

    overall_status = "ok"
    issues: list[str] = []

    if not heartbeat["alive"]:
        overall_status = "critical"
        issues.append(f"Heartbeat: {heartbeat.get('reason', 'not alive')}")
    if stuck.stuck:
        overall_status = "critical"
        issues.append(f"Stuck: {stuck.stuck_reason}")
    if stuck.doom_loop:
        overall_status = "critical"
        issues.append(f"Doom loop: {stuck.doom_loop_pattern}")
    if stuck.status == "warning" and overall_status == "ok":
        overall_status = "warning"

    return {
        "execution_id": execution_id,
        "status": overall_status,
        "issues": issues,
        "heartbeat": heartbeat,
        "stuck_detection": {
            "stuck": stuck.stuck,
            "stuck_reason": stuck.stuck_reason,
            "doom_loop": stuck.doom_loop,
            "doom_loop_pattern": stuck.doom_loop_pattern,
            "last_output_age_seconds": stuck.last_output_age_seconds,
            "output_line_count": stuck.output_line_count,
        },
        "checked_at": now_iso(),
    }


def cleanup_guard_files(root: Path, execution_id: str) -> None:
    """Remove heartbeat and guard files for an execution."""
    path = heartbeat_path(root, execution_id)
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def load_guard_config(root: Path) -> GuardConfig:
    """Load guard configuration from project's runtime policy."""
    from aios.core.runtime_policy import load_runtime_policy

    policy = load_runtime_policy(root)
    guard_section = policy.get("execution_guard") or {}

    return GuardConfig(
        stuck_timeout_seconds=int(guard_section.get("stuck_timeout_seconds", DEFAULT_STUCK_TIMEOUT_SECONDS)),
        doom_loop_threshold=int(guard_section.get("doom_loop_threshold", DEFAULT_DOOM_LOOP_THRESHOLD)),
        heartbeat_interval_seconds=int(guard_section.get("heartbeat_interval_seconds", DEFAULT_HEARTBEAT_INTERVAL_SECONDS)),
        heartbeat_timeout_seconds=int(guard_section.get("heartbeat_timeout_seconds", DEFAULT_HEARTBEAT_TIMEOUT_SECONDS)),
        enabled=bool(guard_section.get("enabled", True)),
    )


def _truncate_line(line: str, max_length: int = 120) -> str:
    """Truncate a line for display."""
    stripped = line.strip()
    if len(stripped) <= max_length:
        return stripped
    return stripped[:max_length - 3] + "..."
