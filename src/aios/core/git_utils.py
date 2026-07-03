"""P2-3: Git utilities for diff analysis."""

from __future__ import annotations

import subprocess
from pathlib import Path


def is_git_repo(root: Path) -> bool:
    return (root / ".git").exists()


def collect_git_status(root: Path) -> dict[str, str]:
    """Return {relative_path: git_status} for changed files."""
    if not is_git_repo(root):
        return {}
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {}
    if result.returncode != 0:
        return {}
    status_map: dict[str, str] = {}
    _code_map = {"A": "added", "M": "modified", "D": "deleted", "R": "modified"}
    for line in result.stdout.splitlines():
        line = line.rstrip("\n\r")
        if not line.strip():
            continue
        xy = line[:2]
        path = line[3:].strip()
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1]
        if xy[0] in _code_map:
            status_map[path] = _code_map[xy[0]]
        elif xy[1] == "M":
            status_map[path] = "modified"
        elif xy[1] == "D":
            status_map[path] = "deleted"
        elif xy[0] == "?" or xy[1] == "?":
            status_map[path] = "untracked"
        else:
            status_map[path] = "modified"
    return status_map


def get_current_branch(root: Path) -> str | None:
    if not is_git_repo(root):
        return None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def get_current_commit(root: Path) -> str | None:
    if not is_git_repo(root):
        return None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def get_recent_diff(root: Path, max_files: int = 50) -> list[str]:
    """Return list of files changed in the last commit."""
    if not is_git_repo(root):
        return []
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    files = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
    return files[:max_files]


def git_snapshot(root: Path) -> dict:
    """Take a snapshot of the git state for an execution record."""
    status_map = collect_git_status(root)
    status_codes: dict[str, int] = {}
    for _, label in status_map.items():
        status_codes[label] = status_codes.get(label, 0) + 1

    return {
        "is_git_repo": is_git_repo(root),
        "branch": get_current_branch(root),
        "commit": get_current_commit(root),
        "is_clean": len(status_map) == 0,
        "status_map": status_codes,
    }


def git_changed_files(root: Path, max_count: int = 50) -> list[str]:
    """Return list of recently changed files (from git log).

    Args:
        root: Project root.
        max_count: Maximum number of recent commits to scan.

    Returns:
        List of relative file paths.
    """
    if not is_git_repo(root):
        return []
    try:
        result = subprocess.run(
            ["git", "log", f"--max-count={max_count}", "--name-only", "--pretty=format:", "--diff-filter=AM"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    files: list[str] = []
    seen: set[str] = set()
    for line in result.stdout.splitlines():
        clean = line.strip()
        if clean and clean not in seen:
            seen.add(clean)
            files.append(clean)
    return files[:max_count]
