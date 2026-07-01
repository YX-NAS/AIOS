from __future__ import annotations

import argparse
from pathlib import Path

from aios.core.scanner import scan_project


def add_scan_parser(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser("scan", help="Scan project files and update .aios/file-index.json.")


def run_scan(root: Path, args: argparse.Namespace) -> None:
    report = scan_project(root)
    summary = report["summary"]
    print(f"Scanned {summary['file_count']} files.")
    print(f"Languages: {', '.join(summary['languages']) or 'unknown'}")
    print(f"Frameworks: {', '.join(summary['frameworks']) or 'unknown'}")

