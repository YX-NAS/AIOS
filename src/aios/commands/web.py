from __future__ import annotations

import argparse
import time
from pathlib import Path

from aios.core.webapp import start_web_server


def add_web_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("web", help="Start the AIOS local Web UI.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind.")
    parser.add_argument("--port", default=8765, type=int, help="Port to bind.")


def run_web(root: Path, args: argparse.Namespace) -> None:
    handle = start_web_server(root, args.host, args.port)
    print(f"AIOS Web UI running at {handle.url}")
    print(f"Project root: {root}")
    print("Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        handle.close()
        print("AIOS Web UI stopped.")
