from __future__ import annotations

import argparse
import time
from pathlib import Path

from aios.core.launcher import start_launcher_server


def add_launcher_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("launcher", help="Start the AIOS multi-project launcher.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind.")
    parser.add_argument("--port", default=8755, type=int, help="Port to bind.")


def run_launcher(root: Path, args: argparse.Namespace) -> None:
    del root
    handle = start_launcher_server(args.host, args.port)
    print(f"AIOS launcher running at {handle.url}")
    print("Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        handle.close()
        print("AIOS launcher stopped.")
