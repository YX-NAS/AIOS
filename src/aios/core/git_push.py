from __future__ import annotations

import subprocess
from pathlib import Path


PROTECTED_BRANCHES = {"main", "master"}


def auto_push_commit(
    root: Path,
    commit_result: dict | None,
    remote: str = "origin",
    allow_protected: bool = False,
) -> dict:
    if not commit_result or not commit_result.get("committed"):
        return {"pushed": False, "reason": "No new auto commit available for push."}

    branch = str(commit_result.get("branch") or "").strip()
    commit = str(commit_result.get("commit") or "").strip()
    if not branch:
        return {"pushed": False, "reason": "Current branch is unavailable."}
    if branch in PROTECTED_BRANCHES and not allow_protected:
        return {"pushed": False, "reason": f"Protected branch push is disabled by default: {branch}", "branch": branch}

    remote_check = subprocess.run(
        ["git", "remote", "get-url", remote],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if remote_check.returncode != 0:
        return {"pushed": False, "reason": f"Git remote not found: {remote}", "branch": branch}

    push_result = subprocess.run(
        ["git", "push", "-u", remote, branch],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if push_result.returncode != 0:
        return {
            "pushed": False,
            "reason": (push_result.stderr or push_result.stdout or "git push failed").strip(),
            "branch": branch,
            "remote": remote,
            "commit": commit,
        }

    return {
        "pushed": True,
        "reason": None,
        "branch": branch,
        "remote": remote,
        "commit": commit,
    }
