from __future__ import annotations

from datetime import datetime
from pathlib import Path


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def today() -> str:
    return datetime.now().date().isoformat()


def append_section(path: Path, title: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    prefix = "\n" if path.exists() and path.read_text(encoding="utf-8").strip() else ""
    with path.open("a", encoding="utf-8") as file:
        file.write(f"{prefix}## {title}\n\n{body.rstrip()}\n")

