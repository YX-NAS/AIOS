from __future__ import annotations

from pathlib import Path

from aios.core.paths import require_aios
from aios.utils.json_utils import write_json
from aios.utils.text import now_iso
from aios.core.git_utils import collect_git_status, get_current_branch, get_current_commit

IGNORE_DIRS = {
    ".aios",
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    ".next",
}

IGNORE_FILES = {".env", ".DS_Store"}

LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".json": "json",
    ".md": "markdown",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".css": "css",
    ".html": "html",
}


def scan_project(root: Path) -> dict:
    aios_dir = require_aios(root)
    files = []
    languages: set[str] = set()
    frameworks: set[str] = set()
    git_status_map = collect_git_status(root)

    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if _ignored(relative, path):
            continue
        if path.is_file():
            language = LANGUAGE_BY_SUFFIX.get(path.suffix.lower(), "unknown")
            if language != "unknown":
                languages.add(language)
            files.append(
                {
                    "path": relative.as_posix(),
                    "type": classify_file(relative),
                    "language": language,
                    "importance": importance(relative),
                    "summary": summarize(relative),
                    "size_bytes": path.stat().st_size,
                    "git_status": git_status_map.get(relative.as_posix()),
                }
            )

    if (root / "package.json").exists():
        frameworks.add("node")
    if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists():
        frameworks.add("python")
    if (root / "src" / "app").exists() or (root / "next.config.js").exists() or (root / "next.config.mjs").exists():
        frameworks.add("nextjs")

    report = {
        "generated_at": now_iso(),
        "root": str(root),
        "summary": {
            "file_count": len(files),
            "languages": sorted(languages),
            "frameworks": sorted(frameworks),
            "changed_files": len(git_status_map),
            "git_branch": get_current_branch(root),
            "git_commit": get_current_commit(root),
        },
        "files": files,
    }
    write_json(aios_dir / "file-index.json", report)
    write_scan_report(aios_dir / "reports" / "scan-report.md", report)
    return report


def _ignored(relative: Path, path: Path) -> bool:
    parts = set(relative.parts)
    if parts & IGNORE_DIRS:
        return True
    if path.name in IGNORE_FILES:
        return True
    return False


def classify_file(relative: Path) -> str:
    parts = relative.parts
    suffix = relative.suffix.lower()
    if "tests" in parts or relative.name.startswith("test_") or relative.name.endswith(".test.ts"):
        return "test"
    if "api" in parts or "backend" in parts or relative.name in {"main.py", "app.py"}:
        return "backend"
    if suffix in {".tsx", ".jsx", ".css", ".html"}:
        return "frontend"
    if relative.name.lower().startswith("readme") or suffix == ".md":
        return "documentation"
    if relative.name in {"pyproject.toml", "package.json", "requirements.txt"}:
        return "config"
    return "source"


def importance(relative: Path) -> str:
    name = relative.name
    if name in {"main.py", "app.py", "package.json", "pyproject.toml", "README.md"}:
        return "high"
    if "src" in relative.parts or "tests" in relative.parts:
        return "medium"
    return "low"


def summarize(relative: Path) -> str:
    file_type = classify_file(relative)
    if file_type == "test":
        return "测试文件"
    if file_type == "backend":
        return "后端或服务入口相关文件"
    if file_type == "frontend":
        return "前端界面相关文件"
    if file_type == "documentation":
        return "文档文件"
    if file_type == "config":
        return "项目配置文件"
    return "项目源文件"


def write_scan_report(path: Path, report: dict) -> None:
    summary = report["summary"]
    body = [
        "# 扫描报告",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 文件数量：{summary['file_count']}",
        f"- 语言：{', '.join(summary['languages']) or '未识别'}",
        f"- 框架：{', '.join(summary['frameworks']) or '未识别'}",
        "",
        "## 高重要文件",
        "",
    ]
    high_files = [item for item in report["files"] if item["importance"] == "high"]
    if not high_files:
        body.append("暂无。")
    else:
        body.extend(f"- `{item['path']}`：{item['summary']}" for item in high_files)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
