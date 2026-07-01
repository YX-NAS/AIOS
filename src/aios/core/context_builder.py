from __future__ import annotations

from pathlib import Path
import math
import re

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

KEYWORD_ALIASES = {
    "登录": ["login", "auth", "signin"],
    "认证": ["auth", "login"],
    "支付": ["payment", "pay", "billing"],
    "后台": ["admin", "dashboard", "backend"],
    "管理": ["admin", "manage"],
    "接口": ["api", "endpoint"],
    "测试": ["test", "spec"],
    "文档": ["readme", "docs", "document"],
}


def estimate_tokens(text: str) -> int:
    """Estimate token count. Chinese ~1.5 tok/char, English/code ~0.25 tok/char."""
    chinese_chars = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other_chars = len(text) - chinese_chars
    return int(chinese_chars * 1.5 + other_chars * 0.25) or 1


def _get_context_window(root: Path, model: str) -> int:
    from aios.core.models import load_model_library
    models = load_model_library(root)
    for m in models:
        if m["id"] == model:
            return m.get("context_window") or 128000
    return 128000


def build_context_pack(root: Path, task: dict, model: str) -> dict:
    aios_dir = require_aios(root)
    route = route_task(task, root)
    model_key = model.lower()
    style = next((value for key, value in MODEL_STYLE.items() if key in model_key), MODEL_STYLE["gpt"])
    file_index = read_json(aios_dir / "file-index.json", {"files": [], "summary": {}})
    relevant_files = choose_relevant_files(file_index.get("files", []), task["type"], task["title"])
    context_text = _read_text(aios_dir / "context.md", "暂无项目上下文。")
    architecture_text = _read_text(aios_dir / "architecture.md", "暂无架构说明。")
    rules_text = _read_text(aios_dir / "rules.md", "暂无规则。")
    decisions_text = _read_text(aios_dir / "decisions.md", "暂无决策。")
    warnings = build_pack_warnings(task, relevant_files, file_index, context_text, architecture_text)
    severe_warnings = [item for item in warnings if is_severe_warning(item)]
    dependency_lines = [
        f"- 父任务：{task.get('parent_task_id') or '无'}",
        f"- 依赖任务：{', '.join(task.get('depends_on_task_ids') or []) or '无'}",
    ]
    risk_lines = [f"- {item}" for item in warnings] if warnings else ["- 未发现明显上下文风险。"]
    summary_lines = [
        f"- 生成时间：{now_iso()}",
        f"- 任务 ID：{task['id']}",
        f"- 目标任务：{task['title']}",
        f"- 任务类型：{task['type']}",
        f"- 复杂度：{task['complexity']}",
        f"- 推荐模型：{route['recommended_model']}",
        f"- 当前模型：{model}",
        f"- Pack 策略：{style}",
    ]

    parts = [
        "# AIOS Context Pack",
        "",
        "## 任务层",
        "",
        *summary_lines,
        *dependency_lines,
        "",
        "## 路由理由",
        "",
        *[f"- {item}" for item in route["reason"]],
        "",
        "## 验收标准",
        "",
        *[f"- {item}" for item in task["acceptance_criteria"]],
        "",
        "## 风险与校验",
        "",
        *risk_lines,
        "",
        "## 项目层",
        "",
        "### 必读规则",
        "",
        rules_text,
        "",
        "### 项目背景",
        "",
        context_text,
        "",
        "### 架构说明",
        "",
        architecture_text,
        "",
        "## 文件层",
        "",
        "### 相关文件",
        "",
    ]
    if relevant_files:
        parts.extend(
            f"- `{item['path']}`：{item['summary']} | 类型={item['type']} | 重要度={item.get('importance', '-')}"
            + (f" | git={item['git_status']}" if item.get("git_status") else "")
            for item in relevant_files
        )
    else:
        parts.append("暂无扫描结果。请先运行 `aios scan`。")
    parts.extend(["", "### 文件筛选说明", ""])
    parts.extend(
        [
            "- 优先纳入和任务关键词匹配的文件。",
            "- 优先纳入最近有 git 变更的文件。",
            "- 兼顾重要入口文件、配置文件和测试文件。",
        ]
    )

    if "deepseek" not in model_key and "minimax" not in model_key:
        parts.extend(["", "### 架构决策", "", decisions_text])

    target = aios_dir / "context-packs" / f"{task['id']}-{safe_model_name(model)}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(parts).rstrip() + "\n"
    target.write_text(content, encoding="utf-8")

    token_estimate = estimate_tokens(content)
    context_window = _get_context_window(root, model)
    window_usage_pct = round(token_estimate / context_window * 100, 1)
    warning = severe_warnings[0] if severe_warnings else None
    if token_estimate > context_window * 0.9:
        warnings.append("Context pack exceeds 90% of model context window")
        severe_warnings.append("Context pack exceeds 90% of model context window")
        warning = warning or "Context pack exceeds 90% of model context window"

    return {
        "path": target,
        "token_estimate": token_estimate,
        "context_window": context_window,
        "window_usage_pct": window_usage_pct,
        "warning": warning,
        "warnings": warnings,
        "relevant_files": relevant_files,
        "quality": "warning" if severe_warnings else "ok",
    }


def choose_relevant_files(files: list[dict], task_type: str, task_title: str = "", limit: int = 20) -> list[dict]:
    if task_type == "documentation":
        preferred = {"documentation", "config"}
    elif task_type == "testing":
        preferred = {"test", "source", "backend"}
    elif task_type == "ui_design":
        preferred = {"frontend", "documentation"}
    else:
        preferred = {"backend", "source", "config", "test"}
    keywords = extract_task_keywords(task_title)
    selected = [item for item in files if item["type"] in preferred]
    selected.sort(
        key=lambda item: (
            -file_relevance_score(item, keywords),
            0 if item.get("git_status") else 1,
            importance_rank(item.get("importance", "low")),
            item["path"],
        )
    )
    return selected[:limit]


def extract_task_keywords(task_title: str) -> list[str]:
    normalized = re.sub(r"[：:，,。；;（）()\-_/]+", " ", task_title.lower())
    words = [word.strip() for word in normalized.split() if len(word.strip()) >= 2]
    expanded: list[str] = []
    for word in words:
        expanded.append(word)
        for alias in KEYWORD_ALIASES.get(word, []):
            expanded.append(alias.lower())
    compact = normalized.replace(" ", "")
    for keyword, aliases in KEYWORD_ALIASES.items():
        if keyword in compact:
            expanded.append(keyword.lower())
            expanded.extend(alias.lower() for alias in aliases)
    return list(dict.fromkeys(expanded))


def file_relevance_score(item: dict, keywords: list[str]) -> int:
    score = 0
    text = f"{item.get('path', '')} {item.get('summary', '')}".lower()
    if item.get("git_status"):
        score += 40
    score += {"high": 20, "medium": 10, "low": 0}.get(item.get("importance"), 0)
    score += {"backend": 8, "source": 6, "test": 5, "frontend": 5, "config": 4, "documentation": 3}.get(item.get("type"), 0)
    for keyword in keywords:
        if keyword and keyword in text:
            score += 15
    return score


def importance_rank(level: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(level, 3)


def build_pack_warnings(task: dict, relevant_files: list[dict], file_index: dict, context_text: str, architecture_text: str) -> list[str]:
    warnings: list[str] = []
    if not task.get("acceptance_criteria"):
        warnings.append("Task acceptance criteria are missing.")
    if not file_index.get("files"):
        warnings.append("Project has not been scanned yet; file index is empty.")
    if file_index.get("files") and not relevant_files:
        warnings.append("No relevant files were selected for this task.")
    if contains_placeholder(context_text):
        warnings.append("Project context is still placeholder content.")
    if contains_placeholder(architecture_text):
        warnings.append("Architecture description is still placeholder content.")
    return warnings


def contains_placeholder(text: str) -> bool:
    lowered = (text or "").strip()
    if not lowered:
        return True
    placeholder_signals = ["待补充", "暂无", "mvp 开发阶段", "项目目标待补充", "总体架构", "模块划分"]
    return any(signal in lowered for signal in placeholder_signals)


def is_severe_warning(warning: str) -> bool:
    severe_signals = [
        "No relevant files",
        "Context pack exceeds 90%",
        "Task acceptance criteria are missing",
    ]
    return any(signal in warning for signal in severe_signals)


def safe_model_name(model: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in model)


def _read_text(path: Path, default: str) -> str:
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8").strip() or default
