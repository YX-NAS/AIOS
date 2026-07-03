"""Repository map generator for AIOS.

Builds a structured representation of a project directory:
- Module hierarchy with inferred roles
- Entry point files identification
- Symbol extraction from source files
- Hot file detection via git history
- Automatic exclusion of build artifacts and metadata directories
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from aios.core.git_utils import git_snapshot, git_changed_files
from aios.core.paths import AIOS_DIR, require_aios
from aios.utils.json_utils import read_json, write_json
from aios.utils.text import now_iso

# Directories and patterns excluded from repository map
DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".aios",
    "__pycache__",
    ".venv",
    "venv",
    ".env",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    "*.egg-info",
    ".tox",
    ".eggs",
}

DEFAULT_EXCLUDE_PATTERNS = [
    r".*\.pyc$",
    r".*\.pyo$",
    r".*\.so$",
    r".*\.dylib$",
    r".*\.dll$",
    r".*\.class$",
    r".*\.o$",
    r".*\.a$",
]

# Files that indicate a Python package or module entry
PACKAGE_MARKERS = {"__init__.py"}
ENTRY_MARKERS = {
    "setup.py",
    "main.py",
    "app.py",
    "manage.py",
    "cli.py",
    "run.py",
}

# Files that define project-level configuration
CONFIG_MARKERS = {
    "pyproject.toml",
    "setup.cfg",
    "requirements.txt",
    "Pipfile",
    "package.json",
    "Cargo.toml",
    "Makefile",
    "Dockerfile",
    "docker-compose.yml",
    ".env.example",
}

# Language-specific symbol extraction patterns
SYMBOL_EXTRACTORS = {
    ".py": "_extract_python_symbols",
    ".js": "_extract_js_symbols",
    ".ts": "_extract_js_symbols",
    ".jsx": "_extract_js_symbols",
    ".tsx": "_extract_js_symbols",
}


@dataclass
class ModuleNode:
    """Represents a directory or file module in the project tree."""
    name: str
    path: str
    is_package: bool = False
    is_entry: bool = False
    is_config: bool = False
    role: str | None = None
    key_files: list[dict] = field(default_factory=list)
    hot_files: list[str] = field(default_factory=list)
    sub_modules: list[ModuleNode] = field(default_factory=list)
    file_count: int = 0


def generate_repo_map(
    root: Path,
    force_refresh: bool = False,
    max_depth: int = 6,
    exclude_dirs: set[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> dict:
    """Generate a structured repository map.

    Args:
        root: Project root directory.
        force_refresh: Regenerate even if a cached map exists.
        max_depth: Maximum directory depth to traverse.
        exclude_dirs: Additional directory names to exclude.
        exclude_patterns: Additional regex patterns to exclude.

    Returns:
        A dict with 'modules', 'stats', 'generated_at', and 'version'.
    """
    aios_dir = require_aios(root)
    map_path = aios_dir / "repo-map.json"

    if not force_refresh and map_path.exists():
        cached = read_json(map_path)
        if cached:
            cached["_source"] = "cache"
            return cached

    ex_dirs = DEFAULT_EXCLUDE_DIRS | (exclude_dirs or set())
    ex_patterns = DEFAULT_EXCLUDE_PATTERNS + (exclude_patterns or [])
    compiled_ex = [re.compile(pattern) for pattern in ex_patterns]

    git_state = git_snapshot(root)
    changed_files = set()
    if git_state["is_git_repo"]:
        changed_files = set(git_changed_files(root, max_count=50))

    modules: list[ModuleNode] = []
    total_files = 0
    total_source_files = 0

    try:
        entries = sorted(
            root.iterdir(),
            key=lambda p: (not p.is_dir(), p.name.lower()),
        )
    except PermissionError:
        entries = []

    for entry in entries:
        name = entry.name
        if name in ex_dirs:
            continue
        if any(pattern.match(name) for pattern in compiled_ex):
            continue
        if name.startswith("."):
            # Still include .github, etc if not excluded
            if name not in {".github"}:
                continue

        if entry.is_dir():
            module = _build_module_node(
                entry,
                root,
                changed_files,
                max_depth=max_depth,
                current_depth=1,
                exclude_dirs=ex_dirs,
                compiled_ex=compiled_ex,
            )
            if module and (module.file_count > 0 or module.sub_modules):
                modules.append(module)
                total_files += module.file_count
        else:
            total_files += 1

    # Count source files
    for module in modules:
        total_source_files += _count_source_files(module)

    repo_map = {
        "root": str(root.resolve()),
        "modules": [module_to_dict(m) for m in modules],
        "stats": {
            "module_count": len(modules),
            "total_files": total_files,
            "total_source_files": total_source_files,
            "is_git_repo": git_state["is_git_repo"],
            "git_branch": git_state["branch"],
            "hot_files_count": len(changed_files),
        },
        "generated_at": now_iso(),
        "version": "1.0",
    }

    write_json(map_path, repo_map)
    repo_map["_source"] = "generated"
    return repo_map


def load_repo_map(root: Path) -> dict | None:
    """Load the cached repository map, or None if it doesn't exist."""
    aios_dir = require_aios(root)
    map_path = aios_dir / "repo-map.json"
    if not map_path.exists():
        return None
    return read_json(map_path)


def _build_module_node(
    directory: Path,
    root: Path,
    hot_files: set[str],
    max_depth: int,
    current_depth: int,
    exclude_dirs: set[str],
    compiled_ex: list[re.Pattern],
) -> ModuleNode | None:
    """Recursively build a ModuleNode for a directory."""
    name = directory.name
    relative = str(directory.relative_to(root))
    is_package = (directory / "__init__.py").exists()

    node = ModuleNode(
        name=name,
        path=relative,
        is_package=is_package,
        role=_infer_module_role(name, relative),
    )

    try:
        entries = sorted(
            directory.iterdir(),
            key=lambda p: (not p.is_dir(), p.name.lower()),
        )
    except PermissionError:
        return node

    for entry in entries:
        entry_name = entry.name

        if entry_name in exclude_dirs:
            continue
        if any(pattern.match(entry_name) for pattern in compiled_ex):
            continue
        if entry_name.startswith("."):
            continue

        if entry.is_dir():
            if current_depth < max_depth:
                sub = _build_module_node(
                    entry,
                    root,
                    hot_files,
                    max_depth=max_depth,
                    current_depth=current_depth + 1,
                    exclude_dirs=exclude_dirs,
                    compiled_ex=compiled_ex,
                )
                if sub and sub.file_count > 0:
                    node.sub_modules.append(sub)
                    node.file_count += sub.file_count
        else:
            node.file_count += 1
            file_rel = str(entry.relative_to(root))

            if entry_name in ENTRY_MARKERS:
                node.is_entry = True
                node.key_files.append({
                    "name": entry_name,
                    "path": file_rel,
                    "role": "entry_point",
                })

            if entry_name in CONFIG_MARKERS:
                node.is_config = True
                node.key_files.append({
                    "name": entry_name,
                    "path": file_rel,
                    "role": "config",
                })

            if file_rel in hot_files:
                node.hot_files.append(file_rel)

    return node


def _count_source_files(module: ModuleNode) -> int:
    """Count source files in a module tree (non-binary, non-config files)."""
    count = 0
    for kf in module.key_files:
        if kf.get("role") in ("source", "entry_point"):
            count += 1
    for sub in module.sub_modules:
        count += _count_source_files(sub)
    return count


def module_to_dict(node: ModuleNode) -> dict:
    """Convert a ModuleNode tree to a plain dict for JSON serialization."""
    return {
        "name": node.name,
        "path": node.path,
        "is_package": node.is_package,
        "is_entry": node.is_entry,
        "is_config": node.is_config,
        "role": node.role,
        "key_files": node.key_files,
        "hot_files": node.hot_files,
        "file_count": node.file_count,
        "sub_modules": [module_to_dict(m) for m in node.sub_modules],
    }


def _infer_module_role(name: str, relative_path: str) -> str | None:
    """Infer the role of a module/directory based on common naming conventions."""
    lowered = name.lower()
    path_lowered = relative_path.lower()

    if name == "src" or path_lowered.endswith("/src"):
        return "source_root"
    if lowered in {"tests", "test"} or "test" in path_lowered.split("/"):
        return "tests"
    if lowered in {"docs", "doc", "documentation"}:
        return "documentation"
    if lowered in {"scripts", "bin"}:
        return "scripts"
    if lowered in {"examples", "samples", "demo"}:
        return "examples"
    if lowered in {"config", "settings", "conf"}:
        return "configuration"
    if lowered in {"static", "assets", "public"}:
        return "static_assets"
    if lowered in {"migrations", "migrate"}:
        return "migrations"
    if lowered in {"api", "rest"}:
        return "api_layer"
    if lowered in {"models", "entities", "domain"}:
        return "domain_models"
    if lowered in {"services", "service"}:
        return "services"
    if lowered in {"utils", "util", "helpers", "common"}:
        return "utilities"
    if lowered in {"middleware", "middlewares"}:
        return "middleware"
    if lowered in {"handlers", "controllers", "views", "routes"}:
        return "presentation"

    return None


def extract_file_symbols(file_path: Path) -> list[dict]:
    """Extract function/class/module-level symbols from a source file.

    Returns a list of dicts with 'name', 'type' (function/class/variable),
    'line', and 'docstring' (first line only).
    """
    suffix = file_path.suffix.lower()
    extractor_name = SYMBOL_EXTRACTORS.get(suffix)

    if extractor_name == "_extract_python_symbols":
        return _extract_python_symbols(file_path)
    if extractor_name == "_extract_js_symbols":
        return _extract_js_symbols(file_path)

    return []


def _extract_python_symbols(file_path: Path) -> list[dict]:
    """Extract top-level symbols from a Python file using AST."""
    symbols: list[dict] = []
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError, RecursionError):
        return symbols

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef):
            doc = ast.get_docstring(node)
            symbols.append({
                "name": node.name,
                "type": "function",
                "line": node.lineno,
                "docstring": _first_line(doc) if doc else None,
            })
        elif isinstance(node, ast.AsyncFunctionDef):
            doc = ast.get_docstring(node)
            symbols.append({
                "name": node.name,
                "type": "async_function",
                "line": node.lineno,
                "docstring": _first_line(doc) if doc else None,
            })
        elif isinstance(node, ast.ClassDef):
            doc = ast.get_docstring(node)
            methods = [
                {"name": m.name, "type": "method", "line": m.lineno}
                for m in node.body
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            symbols.append({
                "name": node.name,
                "type": "class",
                "line": node.lineno,
                "docstring": _first_line(doc) if doc else None,
                "methods": methods[:10],  # Limit methods to avoid huge payloads
            })
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    symbols.append({
                        "name": target.id,
                        "type": "constant",
                        "line": node.lineno,
                        "docstring": None,
                    })

    return symbols


def _extract_js_symbols(file_path: Path) -> list[dict]:
    """Extract top-level symbols from a JavaScript/TypeScript file using regex."""
    symbols: list[dict] = []
    try:
        source = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return symbols

    patterns = [
        (r"(?:export\s+)?(?:async\s+)?function\s+(\w+)", "function"),
        (r"(?:export\s+)?class\s+(\w+)", "class"),
        (r"(?:export\s+)?const\s+(\w+)\s*=", "constant"),
        (r"(?:export\s+)?let\s+(\w+)\s*=", "variable"),
    ]

    seen: set[str] = set()
    for pattern, sym_type in patterns:
        for match in re.finditer(pattern, source):
            name = match.group(1)
            if name not in seen:
                seen.add(name)
                line_no = source[: match.start()].count("\n") + 1
                symbols.append({
                    "name": name,
                    "type": sym_type,
                    "line": line_no,
                    "docstring": None,
                })
                if len(symbols) >= 50:
                    break
        if len(symbols) >= 50:
            break

    return symbols


def _first_line(text: str) -> str:
    """Return the first non-empty line of text, truncated to 120 chars."""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line:
            return line[:120]
    return ""


def build_search_index(root: Path) -> dict:
    """Build a simple keyword search index from project source files.

    Walks the project tree, tokenizes file paths and extracted symbols,
    and builds an inverted index for fast keyword-based file search.

    Returns a dict with 'tokens' (keyword -> [file_paths]) and
    'generated_at' timestamp.
    """
    aios_dir = require_aios(root)
    index_path = aios_dir / "search-index.json"

    # Load repo map first for structured traversal
    repo_map = load_repo_map(root)
    tokens: dict[str, list[str]] = {}
    file_symbols: dict[str, list[str]] = {}  # file_path -> [symbol_names]

    def _walk_module(module: dict, base_path: str):
        module_path = module.get("path") or base_path
        full_dir = root / module_path

        if not full_dir.exists() or not full_dir.is_dir():
            return

        try:
            for entry in sorted(full_dir.iterdir()):
                if entry.name.startswith("."):
                    continue
                if entry.name in DEFAULT_EXCLUDE_DIRS:
                    continue
                if entry.is_file():
                    _index_file(entry, tokens, file_symbols)
        except PermissionError:
            pass

        for sub in module.get("sub_modules", []):
            _walk_module(sub, module_path)

    if repo_map and repo_map.get("modules"):
        for module in repo_map["modules"]:
            _walk_module(module, ".")
    else:
        # Fallback: walk the root directory with basic exclusions
        for entry in sorted(root.rglob("*.py")):
            rel = str(entry.relative_to(root))
            parts = rel.split("/")
            if any(p.startswith(".") for p in parts):
                continue
            if any(p in DEFAULT_EXCLUDE_DIRS for p in parts):
                continue
            _index_file(entry, tokens, file_symbols)

    result = {
        "tokens": {k: sorted(set(v)) for k, v in tokens.items()},
        "symbols": file_symbols,
        "generated_at": now_iso(),
    }
    write_json(index_path, result)
    return result


def _index_file(
    entry: Path,
    tokens: dict[str, list[str]],
    file_symbols: dict[str, list[str]],
) -> None:
    """Index a single file: tokenize path components and extract symbols."""
    rel = str(entry)
    stem_lower = entry.stem.lower()

    # Tokenize the file name and path components
    path_parts = rel.replace("\\", "/").split("/")
    keywords: set[str] = set()

    for part in path_parts:
        # Split on common separators
        sub_parts = re.split(r"[_\-.]+", part.lower())
        for sp in sub_parts:
            if len(sp) >= 2:
                keywords.add(sp)

    # Add the full stem as a keyword
    if len(stem_lower) >= 2:
        keywords.add(stem_lower)

    for kw_sorted in keywords:
        tokens.setdefault(kw_sorted, []).append(rel)

    # Extract symbols for source files
    if entry.suffix.lower() in SYMBOL_EXTRACTORS:
        sym_list = extract_file_symbols(entry)
        if sym_list:
            file_symbols[rel] = [s["name"] for s in sym_list]
            for s in sym_list:
                name_lower = s["name"].lower()
                if len(name_lower) >= 2:
                    tokens.setdefault(name_lower, []).append(rel)
