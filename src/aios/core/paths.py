from __future__ import annotations

from pathlib import Path


AIOS_DIR = ".aios"


def aios_path(root: Path) -> Path:
    return root / AIOS_DIR


def require_aios(root: Path) -> Path:
    path = aios_path(root)
    if not path.exists():
        raise FileNotFoundError("AIOS project is not initialized. Run `aios init` first.")
    return path

