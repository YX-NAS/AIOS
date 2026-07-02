from __future__ import annotations

import subprocess
from pathlib import Path

from aios.core.git_utils import collect_git_status, get_current_branch, get_current_commit, is_git_repo


def git_snapshot(root: Path) -> dict:
    if not is_git_repo(root):
        return {
            "is_git_repo": False,
            "branch": None,
            "commit": None,
            "status_map": {},
            "user_status_map": {},
            "is_clean": True,
        }
    status_map = collect_git_status(root)
    user_status_map = {path: status for path, status in status_map.items() if not path.startswith(".aios/")}
    return {
        "is_git_repo": True,
        "branch": get_current_branch(root),
        "commit": get_current_commit(root),
        "status_map": status_map,
        "user_status_map": user_status_map,
        "is_clean": not bool(user_status_map),
    }


def auto_commit_task_changes(root: Path, execution: dict, task: dict, summary: str) -> dict:
    before_repo = bool(execution.get("git_is_repo_before"))
    if not before_repo:
        return {"committed": False, "reason": "Current project is not a git repository."}
    if not execution.get("git_is_clean_before", False):
        return {"committed": False, "reason": "Git worktree was not clean before execution; skip auto commit for safety."}

    after = git_snapshot(root)
    changed_paths = sorted(after["status_map"].keys())
    if not changed_paths:
        return {"committed": False, "reason": "No git changes to commit.", "branch": after["branch"], "commit": after["commit"], "paths": []}

    add_result = subprocess.run(
        ["git", "add", "-A", "--", *changed_paths],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if add_result.returncode != 0:
        return {"committed": False, "reason": (add_result.stderr or add_result.stdout or "git add failed").strip()}

    subject = build_commit_subject(task)
    body = build_commit_body(task, summary, changed_paths)
    commit_result = subprocess.run(
        ["git", "commit", "-m", subject, "-m", body],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if commit_result.returncode != 0:
        return {"committed": False, "reason": (commit_result.stderr or commit_result.stdout or "git commit failed").strip(), "paths": changed_paths}

    return {
        "committed": True,
        "reason": None,
        "branch": get_current_branch(root),
        "commit": get_current_commit(root),
        "paths": changed_paths,
        "subject": subject,
    }


def build_commit_subject(task: dict) -> str:
    title = str(task.get("title") or "").strip()
    compact_title = title[:48] + "..." if len(title) > 51 else title
    return f"aios: {task['id']} {compact_title}".strip()


def build_commit_body(task: dict, summary: str, changed_paths: list[str]) -> str:
    lines = [
        f"Task: {task['id']}",
        f"Title: {task['title']}",
        "",
        "Summary:",
        summary.strip(),
        "",
        "Changed paths:",
    ]
    lines.extend(f"- {path}" for path in changed_paths)
    return "\n".join(lines).strip()
