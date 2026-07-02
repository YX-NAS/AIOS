from __future__ import annotations

import json
import subprocess
from pathlib import Path


def auto_create_pr_draft(
    root: Path,
    task: dict,
    summary: str,
    push_result: dict | None,
    base_branch: str = "main",
) -> dict:
    if not push_result or not push_result.get("pushed"):
        return {"created": False, "reason": "No successful auto push available for PR draft creation."}

    branch = str(push_result.get("branch") or "").strip()
    if not branch:
        return {"created": False, "reason": "Current branch is unavailable for PR draft creation."}
    if branch == base_branch:
        return {"created": False, "reason": f"Source branch matches base branch: {base_branch}"}

    title = build_pr_title(task)
    body = build_pr_body(task, summary)
    result = subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--draft",
            "--base",
            base_branch,
            "--head",
            branch,
            "--title",
            title,
            "--body",
            body,
            "--json",
            "url,number",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return {"created": False, "reason": (result.stderr or result.stdout or "gh pr create failed").strip(), "branch": branch, "base_branch": base_branch}

    parsed = _parse_gh_json(result.stdout)
    return {
        "created": True,
        "reason": None,
        "branch": branch,
        "base_branch": base_branch,
        "url": parsed.get("url"),
        "number": parsed.get("number"),
        "title": title,
    }


def build_pr_title(task: dict) -> str:
    title = str(task.get("title") or "").strip()
    return f"[AIOS] {task['id']} {title}".strip()


def build_pr_body(task: dict, summary: str) -> str:
    return "\n".join(
        [
            f"Task: {task['id']}",
            f"Title: {task['title']}",
            "",
            "Summary:",
            summary.strip(),
        ]
    ).strip()


def _parse_gh_json(raw: str) -> dict:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}
