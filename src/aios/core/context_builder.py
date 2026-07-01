from __future__ import annotations

from pathlib import Path

from aios.core.paths import require_aios
from aios.core.router import route_task
from aios.utils.json_utils import read_json
from aios.utils.text import now_iso


MODEL_STYLE = {
    "gpt": "完整背景、决策、约束和验收标准",
    "claude": "长上下文，包含更多设计说明和文件索引",
    "deepseek": "精简代码任务、相关文件和明确验收标准",
    "minimax": "偏文档、总结和低成本执行说明",
}


def build_context_pack(root: Path, task: dict, model: str) -> Path:
    aios_dir = require_aios(root)
    route = route_task(task, root)
    model_key = model.lower()
    style = next((value for key, value in MODEL_STYLE.items() if key in model_key), MODEL_STYLE["gpt"])
    file_index = read_json(aios_dir / "file-index.json", {"files": [], "summary": {}})
    relevant_files = choose_relevant_files(file_index.get("files", []), task["type"])

    parts = [
        "# AIOS Context Pack",
        "",
        f"- 生成时间：{now_iso()}",
        f"- 任务 ID：{task['id']}",
        f"- 目标任务：{task['title']}",
        f"- 任务类型：{task['type']}",
        f"- 复杂度：{task['complexity']}",
        f"- 推荐模型：{route['recommended_model']}",
        f"- 当前模型：{model}",
        f"- Pack 策略：{style}",
        "",
        "## 路由理由",
        "",
        *[f"- {item}" for item in route["reason"]],
        "",
        "## 必读规则",
        "",
        _read_text(aios_dir / "rules.md", "暂无规则。"),
        "",
        "## 项目背景",
        "",
        _read_text(aios_dir / "context.md", "暂无项目上下文。"),
        "",
        "## 架构说明",
        "",
        _read_text(aios_dir / "architecture.md", "暂无架构说明。"),
        "",
        "## 相关文件",
        "",
    ]
    if relevant_files:
        parts.extend(f"- `{item['path']}`：{item['summary']}" for item in relevant_files)
    else:
        parts.append("暂无扫描结果。请先运行 `aios scan`。")
    parts.extend(["", "## 验收标准", ""])
    parts.extend(f"- {item}" for item in task["acceptance_criteria"])

    if "deepseek" not in model_key and "minimax" not in model_key:
        parts.extend(["", "## 架构决策", "", _read_text(aios_dir / "decisions.md", "暂无决策。")])

    target = aios_dir / "context-packs" / f"{task['id']}-{safe_model_name(model)}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
    return target


def choose_relevant_files(files: list[dict], task_type: str) -> list[dict]:
    if task_type == "documentation":
        preferred = {"documentation", "config"}
    elif task_type == "testing":
        preferred = {"test", "source", "backend"}
    elif task_type == "ui_design":
        preferred = {"frontend", "documentation"}
    else:
        preferred = {"backend", "source", "config", "test"}
    selected = [item for item in files if item["type"] in preferred]
    return selected[:20]


def safe_model_name(model: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in model)


def _read_text(path: Path, default: str) -> str:
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8").strip() or default
