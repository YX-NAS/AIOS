#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

PROJECT_ROOT="${1:-}"
if [[ -z "${PROJECT_ROOT}" ]]; then
  echo "请输入要管理的项目目录路径："
  read -r PROJECT_ROOT
fi

if [[ -z "${PROJECT_ROOT}" || ! -d "${PROJECT_ROOT}" ]]; then
  echo "项目目录无效：${PROJECT_ROOT}"
  exit 1
fi

"${SCRIPT_DIR}/scripts/start_local_webui.sh" "${PROJECT_ROOT}"

