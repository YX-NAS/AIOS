"""P2-3: Git diff analysis tests."""

from __future__ import annotations

import json
from pathlib import Path

from aios.core.git_utils import (
    collect_git_status,
    get_current_branch,
    get_current_commit,
    is_git_repo,
)
from aios.core.scanner import scan_project
from aios.main import main


def test_scan_includes_git_status(tmp_path: Path) -> None:
    # Create a git repo with a tracked and an untracked file
    subprocess = __import__("subprocess")
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, timeout=10)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), capture_output=True, timeout=5)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), capture_output=True, timeout=5)
    (tmp_path / "hello.py").write_text("print('hello')", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True, timeout=5)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), capture_output=True, timeout=10)
    # Modify the file
    (tmp_path / "hello.py").write_text("print('hello world')", encoding="utf-8")
    # Add an untracked file
    (tmp_path / "new_file.py").write_text("# new", encoding="utf-8")

    main(["--root", str(tmp_path), "init", "--name", "demo", "--force"])
    report = scan_project(tmp_path)

    # File entries should have git_status
    hello_entry = next(f for f in report["files"] if f["path"] == "hello.py")
    assert hello_entry["git_status"] == "modified"
    new_entry = next(f for f in report["files"] if f["path"] == "new_file.py")
    assert new_entry["git_status"] == "untracked"

    # Summary should include git fields
    assert report["summary"]["git_branch"] is not None
    assert report["summary"]["git_commit"] is not None
    assert report["summary"]["changed_files"] >= 2


def test_scan_non_git_repo_skips_git(tmp_path: Path) -> None:
    main(["--root", str(tmp_path), "init", "--name", "demo"])
    (tmp_path / "hello.py").write_text("print('hello')", encoding="utf-8")
    report = scan_project(tmp_path)
    for f in report["files"]:
        assert f["git_status"] is None
    assert report["summary"]["changed_files"] == 0
    assert report["summary"]["git_branch"] is None
    assert report["summary"]["git_commit"] is None


def test_git_utils_branch_and_commit(tmp_path: Path) -> None:
    subprocess = __import__("subprocess")
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, timeout=10)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), capture_output=True, timeout=5)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), capture_output=True, timeout=5)
    (tmp_path / "f.txt").write_text("hi", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True, timeout=5)
    subprocess.run(["git", "commit", "-m", "c1"], cwd=str(tmp_path), capture_output=True, timeout=10)

    branch = get_current_branch(tmp_path)
    assert branch is not None
    commit = get_current_commit(tmp_path)
    assert commit is not None
    assert len(commit) >= 7


def test_context_pack_prefers_changed_files(tmp_path: Path) -> None:
    from aios.core.context_builder import choose_relevant_files
    files = [
        {"path": "src/a.py", "type": "source", "language": "python", "importance": "medium", "summary": "s", "size_bytes": 100, "git_status": None},
        {"path": "src/b.py", "type": "source", "language": "python", "importance": "medium", "summary": "s", "size_bytes": 100, "git_status": "modified"},
        {"path": "src/c.py", "type": "source", "language": "python", "importance": "high", "summary": "s", "size_bytes": 100, "git_status": None},
    ]
    result = choose_relevant_files(files, "simple_coding", "更新 src b 模块")
    # b.py (modified) should come before a.py (same importance, no git change)
    paths = [f["path"] for f in result]
    assert paths.index("src/b.py") < paths.index("src/a.py")


def test_context_pack_prefers_keyword_matches(tmp_path: Path) -> None:
    from aios.core.context_builder import choose_relevant_files

    files = [
        {"path": "src/login_service.py", "type": "backend", "language": "python", "importance": "medium", "summary": "登录服务", "size_bytes": 100, "git_status": None},
        {"path": "src/profile_service.py", "type": "backend", "language": "python", "importance": "high", "summary": "资料服务", "size_bytes": 100, "git_status": None},
    ]
    result = choose_relevant_files(files, "bug_fix", "修复登录报错")
    assert result[0]["path"] == "src/login_service.py"


def test_is_git_repo(tmp_path: Path) -> None:
    assert not is_git_repo(tmp_path)
    subprocess = __import__("subprocess")
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, timeout=10)
    assert is_git_repo(tmp_path)
