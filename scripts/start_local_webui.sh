#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ROOT="${1:-$PWD}"
HOST="${AIOS_HOST:-127.0.0.1}"
DEFAULT_PORT="${AIOS_PORT:-8765}"

if [[ ! -d "${REPO_ROOT}/.venv" ]]; then
  python3 -m venv "${REPO_ROOT}/.venv"
fi

source "${REPO_ROOT}/.venv/bin/activate"
python -m pip install --upgrade pip setuptools wheel >/dev/null
python -m pip install -e "${REPO_ROOT}[dev]" >/dev/null

PROJECT_ROOT="${PROJECT_ROOT}" AIOS_HOST="${HOST}" AIOS_PORT="${DEFAULT_PORT}" PYTHONPATH="${REPO_ROOT}/src" python <<'PY'
import os
from pathlib import Path

from aios.core.instance_manager import project_id_for_root, start_project_instance
from aios.core.projects import register_project

root = Path(os.environ["PROJECT_ROOT"]).expanduser().resolve()
host = os.environ["AIOS_HOST"]
start_port = int(os.environ["AIOS_PORT"])

project = register_project(root)
runtime = start_project_instance(root, project["project_id"], host=host, start_port=start_port)

print("AIOS Web UI started.")
print(f"Project: {root}")
print(f"URL: {runtime['url']}")
print(f"Log: {runtime['log_path']}")
PY

URL="$(PROJECT_ROOT="${PROJECT_ROOT}" PYTHONPATH="${REPO_ROOT}/src" python <<'PY'
import os
from pathlib import Path

from aios.core.instance_manager import project_id_for_root, instance_status

root = Path(os.environ["PROJECT_ROOT"]).expanduser().resolve()
runtime = instance_status(root, project_id_for_root(root))
print(runtime["url"] or "")
PY
)"

if [[ -n "${URL}" ]] && command -v open >/dev/null 2>&1; then
  open "${URL}" >/dev/null 2>&1 || true
fi
