"""Smart file selection for AIOS Context Pack generation.

Enhances Context Pack quality by intelligently selecting the most relevant
files for a given task, combining:
- Task type-driven heuristics
- Bounded search against keywords from task title/description
- Manual file annotations
- Automatic exclusion of non-relevant files
"""

from __future__ import annotations

from pathlib import Path

from aios.core.bounded_search import search_files
from aios.utils.json_utils import read_json

# Maximum recommended files to include in a smart pack
DEFAULT_MAX_FILES = 30

# Minimum relevance score to include a file
MIN_RELEVANCE_SCORE = 1.0

# Task type to file extension priority mapping
TASK_TYPE_EXTENSIONS: dict[str, list[str]] = {
    "testing": [".py", ".yaml", ".yml", ".toml", ".cfg", ".ini"],
    "documentation": [".md", ".rst", ".txt"],
    "ui_design": [".py", ".html", ".css", ".js", ".jsx", ".tsx", ".vue"],
    "deployment": [".yaml", ".yml", ".toml", ".dockerfile", ".conf", ".sh"],
    "data_processing": [".py", ".csv", ".json", ".sql", ".parquet"],
}

# Task type to file exclude patterns
TASK_TYPE_EXCLUDES: dict[str, list[str]] = {
    "testing": ["test_*.py", "*test.py", "conftest.py"],
    "documentation": ["*.py", "*.js", "*.ts"],
    "ui_design": ["test_*.py"],
}

# Task type to associated keywords for search boost
TASK_TYPE_KEYWORDS: dict[str, list[str]] = {
    "architecture": ["design", "module", "structure", "pattern", "interface", "abstract"],
    "bug_fix": ["fix", "error", "exception", "bug", "issue", "patch"],
    "complex_coding": ["implementation", "logic", "algorithm", "handler", "service"],
    "simple_coding": ["util", "helper", "format", "convert", "parse"],
    "testing": ["assert", "mock", "fixture", "pytest", "unittest", "coverage"],
    "documentation": ["readme", "docs", "api", "guide", "tutorial"],
    "ui_design": ["html", "css", "js", "component", "template", "render", "style"],
    "deployment": ["docker", "ci", "cd", "deploy", "nginx", "config", "env"],
    "data_processing": ["transform", "clean", "aggregate", "pipeline", "etl"],
    "batch_edit": [".*"],  # Wide match for batch edits
}

# Always-included core project files regardless of task type
CORE_PROJECT_FILES = [
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "README.md",
    ".aios/context.md",
    ".aios/architecture.md",
    ".aios/rules.md",
]


def select_files_for_task(
    root: Path,
    task: dict,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    manual_files: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> dict:
    """Select the most relevant files for a task's Context Pack.

    Combines four sources:
    1. Manual annotations (highest priority)
    2. Task-type-driven keyword boosting
    3. Bounded search from task title/description keywords
    4. Core project files (always included)

    Args:
        root: Project root.
        task: Task dict with 'id', 'title', 'type', 'description'.
        max_files: Maximum number of files to select.
        manual_files: User-specified file paths to always include.
        exclude_patterns: Additional exclude globs.

    Returns:
        Dict with 'files' (ordered by relevance), 'stats', and 'reasons'.
    """
    task_type = task.get("type") or "simple_coding"
    task_title = task.get("title") or ""
    task_desc = task.get("description") or ""
    target_extensions = TASK_TYPE_EXTENSIONS.get(task_type)

    selected: dict[str, dict] = {}  # file_path -> {score, reasons}
    reasons_map: dict[str, list[str]] = {}  # file_path -> [reason strings]

    # 1. Manual files (highest priority)
    for manual in (manual_files or []):
        clean_path = manual.strip().lstrip("/")
        if clean_path and (root / clean_path).exists():
            selected[clean_path] = {"score": 100.0, "path": clean_path}
            reasons_map.setdefault(clean_path, []).append("manual_annotation")

    # 2. Core project files
    for core_file in CORE_PROJECT_FILES:
        if (root / core_file).exists() and core_file not in selected:
            selected[core_file] = {"score": 90.0, "path": core_file}
            reasons_map.setdefault(core_file, []).append("core_project_file")

    # 3. Task-type keyword boosted search
    search_terms = _extract_search_terms(task_title, task_desc, task_type)
    for term in search_terms:
        results = search_files(
            root,
            term,
            limit=max_files,
            extensions=target_extensions,
            exclude=TASK_TYPE_EXCLUDES.get(task_type, []),
        )
        for result in results:
            path = result["path"]
            base_score = result.get("score", 0) * _task_type_boost(task_type)
            if path in selected:
                selected[path]["score"] += base_score
                reasons_map.setdefault(path, []).append(f"search:{term}")
            else:
                selected[path] = {"score": base_score, "path": path}
                reasons_map.setdefault(path, []).append(f"search:{term}")

    # 4. Apply exclude patterns
    for pattern in (exclude_patterns or []):
        to_remove = [p for p in selected if _matches_glob(p, pattern)]
        for p in to_remove:
            del selected[p]
            reasons_map.pop(p, None)

    # 5. Sort by score descending, truncate to max_files
    sorted_files = sorted(
        selected.values(),
        key=lambda x: x["score"],
        reverse=True,
    )[:max_files]

    # 6. Build enriched result with reasons
    result_files: list[dict] = []
    for entry in sorted_files:
        path = entry["path"]
        file_info = {
            "path": path,
            "score": round(entry["score"], 2),
            "reasons": reasons_map.get(path, []),
            "size_bytes": _file_size(root, path),
            "extension": Path(path).suffix,
        }
        result_files.append(file_info)

    # Statistics
    total_project_files = _count_project_files(root)
    coverage_pct = round(len(result_files) / max(total_project_files, 1) * 100, 1)

    return {
        "files": result_files,
        "stats": {
            "selected_count": len(result_files),
            "total_project_files": total_project_files,
            "coverage_pct": coverage_pct,
            "task_type": task_type,
            "search_terms_used": search_terms,
            "max_files_limit": max_files,
        },
        "quality": _assess_selection_quality(result_files, task),
    }


def _extract_search_terms(title: str, description: str, task_type: str) -> list[str]:
    """Extract search terms from task metadata."""
    import re

    terms: list[str] = []
    combined = f"{title} {description}".lower()

    # Add task-type-specific keywords
    type_keywords = TASK_TYPE_KEYWORDS.get(task_type, [])
    for kw in type_keywords:
        if kw != ".*" and kw in combined:
            terms.append(kw)

    # Extract nouns/keywords from title
    # Split Chinese/English mixed text
    words = re.findall(r"[一-鿿]+|[a-zA-Z0-9_]+", combined)
    for word in words:
        clean = word.strip().lower()
        if len(clean) >= 2 and clean not in {"的", "了", "是", "在", "和", "或", "与", "the", "and", "for", "with"}:
            terms.append(clean)

    # Limit to 8 most relevant
    seen: set[str] = set()
    unique: list[str] = []
    for t in terms:
        if t not in seen:
            seen.add(t)
            unique.append(t)
            if len(unique) >= 8:
                break

    return unique


def _task_type_boost(task_type: str) -> float:
    """Return a relevance boost multiplier for a task type."""
    boosts = {
        "testing": 1.5,
        "bug_fix": 1.3,
        "architecture": 1.2,
        "documentation": 0.8,
    }
    return boosts.get(task_type, 1.0)


def _file_size(root: Path, relative_path: str) -> int | None:
    """Get file size in bytes, or None if inaccessible."""
    full_path = root / relative_path
    try:
        return full_path.stat().st_size
    except OSError:
        return None


def _count_project_files(root: Path) -> int:
    """Count total project files excluding build artifacts."""
    from aios.core.repo_map import DEFAULT_EXCLUDE_DIRS

    count = 0
    for entry in root.rglob("*"):
        if entry.is_file():
            parts = entry.relative_to(root).parts
            if any(p.startswith(".") for p in parts):
                continue
            if any(p in DEFAULT_EXCLUDE_DIRS for p in parts):
                continue
            count += 1
        if count > 10000:
            break
    return count


def _matches_glob(filepath: str, pattern: str) -> bool:
    """Simple glob matching for file paths."""
    from fnmatch import fnmatch
    return fnmatch(filepath, pattern)


def _assess_selection_quality(files: list[dict], task: dict) -> dict:
    """Assess the quality of the file selection for a task."""
    if not files:
        return {
            "status": "warning",
            "message": "No files selected. The project may be empty or the search terms too narrow.",
            "scores": {"relevance": 0.0, "completeness": 0.0, "redundancy": 0.0},
        }

    score_values = [f.get("score", 0) for f in files]
    avg_score = sum(score_values) / len(score_values)
    high_relevance_count = sum(1 for s in score_values if s >= 5.0)
    low_relevance_count = sum(1 for s in score_values if s < 2.0)

    relevance = min(1.0, avg_score / 10.0)
    completeness = 0.7  # Base completeness - hard to measure automatically
    redundancy = low_relevance_count / max(len(files), 1)

    status = "ok"
    message = None
    if relevance < 0.3:
        status = "warning"
        message = "Low relevance scores. Consider adding manual file annotations or refining the task title."
    elif redundancy > 0.4:
        status = "warning"
        message = "High proportion of low-relevance files. Consider narrowing the search scope."

    return {
        "status": status,
        "message": message,
        "scores": {
            "relevance": round(relevance, 2),
            "completeness": round(completeness, 2),
            "redundancy": round(redundancy, 2),
        },
        "high_relevance_count": high_relevance_count,
        "low_relevance_count": low_relevance_count,
        "average_score": round(avg_score, 2),
    }
