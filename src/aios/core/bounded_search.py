"""Bounded context search for AIOS.

Provides keyword-based and relevance-ranked file search within a project,
leveraging the search index built by repo_map.py.

Features:
- Keyword matching against file paths and extracted symbols
- Relevance scoring (exact path match > stem match > symbol match)
- Result filtering by file type, directory, and exclude patterns
- Configurable result limit with truncation
"""

from __future__ import annotations

import re
from pathlib import Path

from aios.core.paths import require_aios
from aios.utils.json_utils import read_json


def load_search_index(root: Path) -> dict:
    """Load the cached search index."""
    aios_dir = require_aios(root)
    index_path = aios_dir / "search-index.json"
    return read_json(index_path, {"tokens": {}, "symbols": {}, "generated_at": None})


def search_files(
    root: Path,
    query: str,
    *,
    limit: int = 20,
    extensions: list[str] | None = None,
    subdir: str | None = None,
    exclude: list[str] | None = None,
) -> list[dict]:
    """Search for files matching a query string.

    Args:
        root: Project root.
        query: Search query (space-separated keywords).
        limit: Maximum number of results.
        extensions: Only return files with these extensions (e.g. ['.py']).
        subdir: Limit search to a specific subdirectory.
        exclude: Glob exclude patterns.

    Returns:
        List of result dicts with 'path', 'score', 'reason'.
    """
    index = load_search_index(root)
    tokens = index.get("tokens") or {}
    symbols = index.get("symbols") or {}
    file_symbols_inverted: dict[str, list[str]] = {}

    for file_path, sym_names in symbols.items():
        for name in sym_names:
            file_symbols_inverted.setdefault(name.lower(), []).append(file_path)

    keywords = _tokenize_query(query)
    if not keywords:
        return []

    scores: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}

    for keyword in keywords:
        # 1. Exact stem match
        for file_path, kw_list in tokens.items():
            if file_path == keyword:
                scores[file_path] = scores.get(file_path, 0) + 10.0
                reasons.setdefault(file_path, []).append(f"exact_stem:{keyword}")
                continue
            if keyword in file_path.split("/")[-1].lower():
                scores[file_path] = scores.get(file_path, 0) + 8.0
                reasons.setdefault(file_path, []).append(f"filename_match:{keyword}")

        # 2. Keyword in token index
        for file_path in tokens.get(keyword, []):
            base_score = 5.0
            # Boost based on path depth — closer to keyword in name is better
            file_lower = file_path.lower()
            if keyword in Path(file_path).stem.lower():
                base_score += 2.0
            if keyword in file_lower.split("/"):
                base_score += 1.0
            scores[file_path] = scores.get(file_path, 0) + base_score
            reasons.setdefault(file_path, []).append(f"token_match:{keyword}")

        # 3. Symbol name match
        for file_path in file_symbols_inverted.get(keyword, []):
            scores[file_path] = scores.get(file_path, 0) + 3.0
            reasons.setdefault(file_path, []).append(f"symbol_match:{keyword}")

    # Apply filters
    exclude_patterns = [re.compile(_glob_to_regex(p)) for p in (exclude or [])]
    results: list[dict] = []
    for file_path, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        if len(results) >= limit:
            break

        if extensions and not any(file_path.endswith(ext) for ext in extensions):
            continue
        if subdir and not file_path.startswith(subdir.rstrip("/") + "/") and file_path != subdir:
            continue
        if any(pattern.search(file_path) for pattern in exclude_patterns):
            continue

        results.append({
            "path": file_path,
            "score": round(score, 2),
            "reasons": reasons.get(file_path, [])[:5],
        })

    return results


def search_symbols(
    root: Path,
    symbol_name: str,
    *,
    limit: int = 10,
) -> list[dict]:
    """Search for a specific symbol across the project.

    Args:
        root: Project root.
        symbol_name: Symbol name to search for (case-insensitive partial match).
        limit: Maximum results.

    Returns:
        List of dicts with 'path', 'symbol', 'line', 'type'.
    """
    from aios.core.repo_map import extract_file_symbols

    index = load_search_index(root)
    file_symbols = index.get("symbols") or {}
    query_lower = symbol_name.lower().strip()

    results: list[dict] = []

    for file_path, _sym_names in file_symbols.items():
        if len(results) >= limit:
            break
        full_path = root / file_path
        if not full_path.exists():
            continue
        symbols = extract_file_symbols(full_path)
        for s in symbols:
            if query_lower in s["name"].lower():
                results.append({
                    "path": file_path,
                    "symbol": s["name"],
                    "type": s.get("type", "unknown"),
                    "line": s.get("line"),
                    "docstring": s.get("docstring"),
                })
                if len(results) >= limit:
                    break

    return results[:limit]


def search_imports_of(
    root: Path,
    module_name: str,
    *,
    limit: int = 15,
) -> list[dict]:
    """Find files that import a specific module.

    Args:
        root: Project root.
        module_name: Module name to search for imports of.
        limit: Maximum results.

    Returns:
        List of dicts with 'path', 'import_statement', 'line'.
    """
    from aios.utils.json_utils import read_json

    aiOS_dir = require_aios(root)
    repo_map = read_json(aiOS_dir / "repo-map.json")

    results: list[dict] = []
    import_pattern = re.compile(
        rf"(?:from\s+{re.escape(module_name)}\s+import|import\s+{re.escape(module_name)})",
        re.IGNORECASE,
    )

    file_list = _collect_files_from_repo_map(root, repo_map) if repo_map else sorted(root.rglob("*.py"))

    for file_path_str in file_list:
        if len(results) >= limit:
            break
        full_path = root / file_path_str if isinstance(file_path_str, str) else file_path_str
        if isinstance(full_path, Path) and full_path.exists() and full_path.is_file():
            try:
                content = full_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, PermissionError):
                continue
            for match in import_pattern.finditer(content):
                line_no = content[: match.start()].count("\n") + 1
                results.append({
                    "path": str(full_path.relative_to(root)),
                    "import_statement": match.group(0),
                    "line": line_no,
                })
                if len(results) >= limit:
                    break

    return results[:limit]


def _tokenize_query(query: str) -> list[str]:
    """Split a query string into normalized, deduplicated keywords."""
    raw = query.lower().strip()
    if not raw:
        return []
    # Split on whitespace and common punctuation
    parts = re.split(r"[\s,;]+", raw)
    keywords: list[str] = []
    for part in parts:
        cleaned = part.strip("._-")
        if len(cleaned) >= 2:
            keywords.append(cleaned)
    # Remove duplicates while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            result.append(kw)
    return result


def _glob_to_regex(pattern: str) -> str:
    """Convert a simple glob pattern to regex."""
    escaped = re.escape(pattern)
    escaped = escaped.replace(r"\*", ".*")
    escaped = escaped.replace(r"\?", ".")
    return f"^{escaped}$"


def _collect_files_from_repo_map(root: Path, repo_map: dict) -> list[str]:
    """Flatten all file paths from a repository map."""
    files: list[str] = []
    for module in repo_map.get("modules", []):
        _collect_module_files(module, files)
    return files


def _collect_module_files(module: dict, collector: list[str]) -> None:
    """Recursively collect file paths from a module node."""
    for kf in module.get("key_files", []):
        collector.append(kf.get("path", ""))
    for hot in module.get("hot_files", []):
        if hot not in collector:
            collector.append(hot)
    for sub in module.get("sub_modules", []):
        _collect_module_files(sub, collector)


def context_search_summary(
    root: Path,
    query: str,
    *,
    max_files: int = 15,
    max_symbols: int = 5,
) -> dict:
    """Run a combined file + symbol search and return a summary.

    Useful as a one-shot call for "show me everything related to X".
    """
    files = search_files(root, query, limit=max_files)
    symbols = search_symbols(root, query, limit=max_symbols)
    return {
        "query": query,
        "files": files,
        "symbols": symbols,
        "total_file_matches": len(files),
        "total_symbol_matches": len(symbols),
    }
