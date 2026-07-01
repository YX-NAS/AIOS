#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${1:-$PWD}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  python3 -m venv "${REPO_ROOT}/.venv"
fi

PROJECT_ROOT="${PROJECT_ROOT}" PYTHONPATH="${REPO_ROOT}/src" "${PYTHON_BIN}" <<'PY'
import os
from pathlib import Path

from aios.core.instance_manager import project_id_for_root, stop_project_instance

root = Path(os.environ["PROJECT_ROOT"]).expanduser().resolve()
stop_project_instance(project_id_for_root(root))
print(f"AIOS Web UI stopped for {root}.")
PY
