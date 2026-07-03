"""P4-3: Manual takeover queue for unrecoverable automation failures.

When the auto-pipeline hits a failure it cannot recover from,
it writes a takeover entry instead of silently stopping.
The launcher and project web UI can surface these entries
so the human operator knows exactly where to intervene.
"""

from __future__ import annotations

from pathlib import Path

from aios.core.paths import aios_path, require_aios
from aios.core.tasks import get_task
from aios.utils.json_utils import read_json, write_json
from aios.utils.text import now_iso

TAKEOVER_VERSION = 1


def takeover_queue_path(root: Path) -> Path:
    aios_dir = aios_path(root)
    if aios_dir:
        return aios_dir / "takeover.json"
    return require_aios(root) / "takeover.json"


def load_takeover_queue(root: Path) -> dict:
    path = takeover_queue_path(root)
    payload = read_json(path, {"version": TAKEOVER_VERSION, "entries": []})
    if not isinstance(payload.get("entries"), list):
        payload["entries"] = []
    return payload


def save_takeover_queue(root: Path, queue: dict) -> None:
    path = takeover_queue_path(root)
    write_json(path, queue)


def enqueue_takeover(
    root: Path,
    task_id: str,
    reason: str,
    failure_category: str | None = None,
    execution_id: str | None = None,
    suggested_action: str | None = None,
    evidence: dict | None = None,
) -> dict:
    """Push an unrecoverable failure onto the takeover queue."""
    queue = load_takeover_queue(root)
    entry = {
        "takeover_id": f"TAKEOVER-{now_iso().replace('T', '-').replace(':', '').replace('-', '')[:12]}",
        "task_id": task_id,
        "task_title": _safe_task_title(root, task_id),
        "reason": reason,
        "failure_category": failure_category,
        "execution_id": execution_id,
        "suggested_action": suggested_action,
        "evidence": evidence or {},
        "status": "pending",
        "created_at": now_iso(),
    }
    queue["entries"].append(entry)
    save_takeover_queue(root, queue)
    return entry


def resolve_takeover(root: Path, takeover_id: str, resolution_note: str) -> dict | None:
    """Mark a takeover entry as resolved."""
    queue = load_takeover_queue(root)
    for entry in queue["entries"]:
        if entry.get("takeover_id") == takeover_id:
            entry["status"] = "resolved"
            entry["resolved_at"] = now_iso()
            entry["resolution_note"] = resolution_note
            save_takeover_queue(root, queue)
            return entry
    return None


def pending_takeover_count(root: Path) -> int:
    queue = load_takeover_queue(root)
    return len([e for e in queue.get("entries", []) if e.get("status") == "pending"])


def takeover_summary(root: Path) -> dict:
    queue = load_takeover_queue(root)
    entries = queue.get("entries", [])
    pending = [e for e in entries if e.get("status") == "pending"]
    return {
        "total": len(entries),
        "pending": len(pending),
        "resolved": len(entries) - len(pending),
        "latest_pending": pending[:5] if pending else [],
    }


def should_takeover(failure_category: str | None, recovery_attempts: int, max_recovery_attempts: int) -> bool:
    """Determine whether a failure warrants a takeover.

    Returns True when:
    - Recovery attempts exhausted
    - Category is permanently unrecoverable (e.g. auth_failure, missing_binary)
    """
    if not failure_category:
        return recovery_attempts >= max_recovery_attempts

    unrecoverable_categories = {"provider_auth_blocked", "missing_binary", "permission_denied"}
    if failure_category in unrecoverable_categories:
        return True

    return recovery_attempts >= max_recovery_attempts


def takeover_suggested_action(failure_category: str | None) -> str:
    actions = {
        "provider_auth_blocked": "检查并更新 API 密钥，然后重新探测 provider。",
        "missing_binary": "安装缺失的执行器 CLI 工具。",
        "permission_denied": "检查文件权限或执行器沙箱配置。",
        "verification_failed": "人工 review 执行输出，修正代码后重新执行。",
        "network_timeout": "检查网络连接并重试。",
        "unknown": "人工检查执行日志，手动完成或重新执行。",
    }
    return actions.get(failure_category or "unknown", actions["unknown"])


def _safe_task_title(root: Path, task_id: str) -> str:
    try:
        return get_task(root, task_id).get("title", task_id)
    except Exception:
        return task_id
