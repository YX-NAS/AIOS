"""Repository analysis commands for AIOS CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from aios.core.bounded_search import context_search_summary, search_files, search_imports_of, search_symbols
from aios.core.repo_map import build_search_index, generate_repo_map, load_repo_map


def add_repo_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("repo", help="Repository analysis and search.")
    repo_sub = parser.add_subparsers(dest="repo_action", required=True)

    # repo map
    map_parser = repo_sub.add_parser("map", help="Generate a structured repository map.")
    map_parser.add_argument("--force", action="store_true", help="Force regeneration even if cache exists.")

    # repo search
    search_parser = repo_sub.add_parser("search", help="Search for files by keyword.")
    search_parser.add_argument("query", help="Search query (space-separated keywords).")
    search_parser.add_argument("--limit", type=int, default=20, help="Maximum results (default: 20).")
    search_parser.add_argument("--ext", nargs="*", default=None, help="File extensions to include (e.g. .py .md).")
    search_parser.add_argument("--subdir", default=None, help="Limit to subdirectory.")
    search_parser.add_argument("--exclude", nargs="*", default=None, help="Glob patterns to exclude.")
    search_parser.add_argument("--symbols", action="store_true", help="Also search for matching symbols.")

    # repo index
    index_parser = repo_sub.add_parser("index", help="Build a search index for the project.")

    # repo imports-of
    imports_parser = repo_sub.add_parser("imports-of", help="Find files that import a specific module.")
    imports_parser.add_argument("module", help="Module name to search imports of.")
    imports_parser.add_argument("--limit", type=int, default=15, help="Maximum results.")


def run_repo(root: Path, args: argparse.Namespace) -> None:
    if args.repo_action == "map":
        repo_map = generate_repo_map(root, force_refresh=args.force)
        source = repo_map.pop("_source", "generated")
        stats = repo_map.get("stats", {})
        print(f"Repository map {source}.")
        print(f"  {stats.get('module_count', 0)} modules, {stats.get('total_files', 0)} files.")
        if stats.get("hot_files_count"):
            print(f"  {stats['hot_files_count']} recently changed files identified.")
        if source == "cache":
            print("  (use --force to regenerate)")

    elif args.repo_action == "search":
        results = search_files(
            root,
            args.query,
            limit=args.limit,
            extensions=args.ext,
            subdir=args.subdir,
            exclude=args.exclude,
        )
        if not results:
            print(f"No files found matching '{args.query}'.")
            return
        print(f"Found {len(results)} file(s) matching '{args.query}':")
        for r in results:
            reasons = ", ".join(r.get("reasons", []))
            print(f"  [{r['score']}] {r['path']}  ({reasons})")

        if args.symbols:
            print()
            sym_results = search_symbols(root, args.query, limit=args.limit)
            if sym_results:
                print(f"Found {len(sym_results)} symbol(s):")
                for s in sym_results:
                    print(f"  {s['type']} {s['symbol']} @ {s['path']}:{s['line']}")

    elif args.repo_action == "index":
        index = build_search_index(root)
        token_count = len(index.get("tokens", {}))
        symbol_file_count = len(index.get("symbols", {}))
        print(f"Search index built.")
        print(f"  {token_count} unique tokens indexed.")
        print(f"  {symbol_file_count} files with symbol information.")

    elif args.repo_action == "imports-of":
        results = search_imports_of(root, args.module, limit=args.limit)
        if not results:
            print(f"No files found importing '{args.module}'.")
            return
        print(f"Found {len(results)} file(s) importing '{args.module}':")
        for r in results:
            print(f"  {r['path']}:{r['line']}  {r['import_statement']}")
