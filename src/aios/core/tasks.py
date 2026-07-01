from __future__ import annotations

import re
from pathlib import Path

from aios.core.paths import require_aios
from aios.core.router import resolve_models_for_task
from aios.core.templates import DEFAULT_ROUTING
from aios.utils.json_utils import read_json, write_json
from aios.utils.text import now_iso


TYPE_KEYWORDS = [
    ("architecture", ["架构", "重构", "模块设计", "设计"]),
    ("bug_fix", ["修复", "bug", "报错", "错误", "异常"]),
    ("complex_coding", ["登录", "认证", "权限", "支付", "核心", "算法"]),
    ("testing", ["测试", "test", "pytest"]),
    ("documentation", ["文档", "README", "说明", "总结"]),
    ("batch_edit", ["批量", "替换", "格式化"]),
    ("ui_design", ["页面", "UI", "样式", "前端"]),
    ("deployment", ["部署", "docker", "nginx", "上线"]),
    ("data_processing", ["数据", "清洗", "导入", "处理"]),
]

BUG_SIGNAL_KEYWORDS = [
    "没有",
    "未",
    "不对",
    "仍然",
    "还是",
    "继续",
    "没有更新",
    "未更新",
    "不同步",
    "同步",
    "时间状态",
    "真实时间",
    "上下文",
    "承接",
    "出戏",
]

SYSTEM_BUILD_KEYWORDS = ["系统", "平台", "后台", "中台", "管理端", "管理后台"]
MODULE_HINT_KEYWORDS = ["包含", "包括", "支持", "提供", "具备", "实现"]

GOAL_TEMPLATES = {
    "bug_fix": [
        ("复现并定位：{goal}", "bug_fix", "high"),
        ("实施修复：{goal}", "bug_fix", "high"),
        ("回归测试：{goal}", "testing", "high"),
        ("更新记录与说明：{goal}", "documentation", "medium"),
    ],
    "deployment": [
        ("部署检查与发布方案：{goal}", "deployment", "high"),
        ("执行部署改动：{goal}", "deployment", "high"),
        ("上线验证与回滚确认：{goal}", "testing", "high"),
        ("更新部署记录：{goal}", "documentation", "medium"),
    ],
    "documentation": [
        ("梳理文档范围：{goal}", "documentation", "medium"),
        ("编写或更新文档：{goal}", "documentation", "medium"),
        ("校验示例与说明：{goal}", "testing", "medium"),
    ],
    "ui_design": [
        ("梳理交互与页面范围：{goal}", "ui_design", "medium"),
        ("实现界面改动：{goal}", "ui_design", "high"),
        ("补充交互验证：{goal}", "testing", "medium"),
        ("更新界面说明：{goal}", "documentation", "low"),
    ],
    "complex_coding": [
        ("拆解方案与影响范围：{goal}", "architecture", "high"),
        ("实现核心功能：{goal}", "complex_coding", "high"),
        ("补充测试与回归验证：{goal}", "testing", "high"),
        ("更新文档与项目记录：{goal}", "documentation", "medium"),
    ],
    "simple_coding": [
        ("确认实现范围：{goal}", "simple_coding", "medium"),
        ("完成代码实现：{goal}", "simple_coding", "medium"),
        ("验证结果并更新记录：{goal}", "testing", "medium"),
    ],
}


def task_plans_path(root: Path) -> Path:
    return require_aios(root) / "task-plans.json"


def load_tasks(root: Path) -> list[dict]:
    aios_dir = require_aios(root)
    return read_json(aios_dir / "tasks.json", {"tasks": []})["tasks"]


def save_tasks(root: Path, tasks: list[dict]) -> None:
    aios_dir = require_aios(root)
    write_json(aios_dir / "tasks.json", {"tasks": tasks})
    write_tasks_markdown(aios_dir / "tasks.md", tasks)


def load_task_plan_drafts(root: Path) -> list[dict]:
    payload = read_json(task_plans_path(root), {"drafts": []})
    drafts = payload.get("drafts")
    if isinstance(drafts, list):
        return drafts
    return []


def save_task_plan_drafts(root: Path, drafts: list[dict]) -> None:
    write_json(task_plans_path(root), {"drafts": drafts})


def create_task(root: Path, title: str, priority: str = "medium", acceptance: list[str] | None = None) -> dict:
    tasks = load_tasks(root)
    task = build_task_record(root, tasks, title, priority, acceptance=acceptance)
    tasks.append(task)
    save_tasks(root, tasks)
    return task


def build_task_record(
    root: Path,
    existing_tasks: list[dict],
    title: str,
    priority: str = "medium",
    task_type: str | None = None,
    acceptance: list[str] | None = None,
    description: str = "",
    source_goal: str | None = None,
    parent_task_id: str | None = None,
    depends_on_task_ids: list[str] | None = None,
    plan_draft_id: str | None = None,
    plan_node_id: str | None = None,
) -> dict:
    resolved_type = task_type or classify_task(title)
    rule = DEFAULT_ROUTING.get(resolved_type, DEFAULT_ROUTING["simple_coding"])
    preferred_models, fallback_models = resolve_models_for_task(
        root,
        resolved_type,
        list(rule["preferred_models"]),
        list(rule["fallback_models"]),
    )
    task = {
        "id": next_task_id(existing_tasks),
        "title": title,
        "description": description,
        "type": resolved_type,
        "status": "todo",
        "priority": priority,
        "complexity": complexity_for(resolved_type),
        "recommended_model": preferred_models[0],
        "fallback_models": fallback_models,
        "acceptance_criteria": acceptance or default_acceptance(resolved_type),
        "parent_task_id": parent_task_id,
        "depends_on_task_ids": depends_on_task_ids or [],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    if source_goal:
        task["source_goal"] = source_goal
    if plan_draft_id:
        task["plan_draft_id"] = plan_draft_id
    if plan_node_id:
        task["plan_node_id"] = plan_node_id
    return task


def plan_goal(root: Path, goal: str, priority: str = "high", create: bool = True) -> list[dict]:
    nodes = build_goal_nodes(goal, priority)
    tasks = load_tasks(root)
    planned = materialize_plan_nodes(root, tasks, nodes, goal)
    if create:
        tasks.extend(planned)
        save_tasks(root, tasks)
    return planned


def create_plan_draft(root: Path, goal: str, priority: str = "high") -> dict:
    drafts = load_task_plan_drafts(root)
    draft_id = next_plan_draft_id(drafts)
    nodes = build_goal_nodes(goal, priority)
    draft = {
        "draft_id": draft_id,
        "goal": goal,
        "priority": priority,
        "status": "draft",
        "tasks": build_preview_tasks(root, goal, nodes),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    drafts.append(draft)
    save_task_plan_drafts(root, drafts)
    return draft


def list_plan_drafts(root: Path) -> list[dict]:
    return sorted(load_task_plan_drafts(root), key=lambda item: item.get("updated_at") or item.get("created_at") or "", reverse=True)


def get_plan_draft(root: Path, draft_id: str) -> dict:
    for draft in load_task_plan_drafts(root):
        if draft.get("draft_id") == draft_id:
            return draft
    raise ValueError(f"Plan draft not found: {draft_id}")


def delete_plan_draft(root: Path, draft_id: str) -> None:
    drafts = load_task_plan_drafts(root)
    remaining = [draft for draft in drafts if draft.get("draft_id") != draft_id]
    if len(remaining) == len(drafts):
        raise ValueError(f"Plan draft not found: {draft_id}")
    save_task_plan_drafts(root, remaining)


def confirm_plan_draft(root: Path, draft_id: str) -> list[dict]:
    drafts = load_task_plan_drafts(root)
    target = None
    for draft in drafts:
        if draft.get("draft_id") == draft_id:
            target = draft
            break
    if target is None:
        raise ValueError(f"Plan draft not found: {draft_id}")
    tasks = load_tasks(root)
    planned = materialize_plan_nodes(root, tasks, target["tasks"], target["goal"], plan_draft_id=draft_id)
    tasks.extend(planned)
    save_tasks(root, tasks)
    target["status"] = "confirmed"
    target["confirmed_at"] = now_iso()
    target["updated_at"] = now_iso()
    save_task_plan_drafts(root, drafts)
    return planned


def get_task(root: Path, task_id: str) -> dict:
    for task in load_tasks(root):
        if task["id"] == task_id:
            return task
    raise ValueError(f"Task not found: {task_id}")


def complete_task(root: Path, task_id: str, summary: str) -> dict:
    tasks = load_tasks(root)
    for task in tasks:
        if task["id"] == task_id:
            task["status"] = "done"
            task["completed_at"] = now_iso()
            task["updated_at"] = now_iso()
            task["completion_summary"] = summary
            save_tasks(root, tasks)
            return task
    raise ValueError(f"Task not found: {task_id}")


def set_task_status(root: Path, task_id: str, status: str) -> dict:
    if status not in {"todo", "running", "done"}:
        raise ValueError(f"Unsupported task status: {status}")
    tasks = load_tasks(root)
    for task in tasks:
        if task["id"] == task_id:
            task["status"] = status
            task["updated_at"] = now_iso()
            save_tasks(root, tasks)
            return task
    raise ValueError(f"Task not found: {task_id}")


def build_preview_tasks(root: Path, goal: str, nodes: list[dict]) -> list[dict]:
    previews: list[dict] = []
    for node in nodes:
        preview = build_task_record(
            root,
            previews,
            node["title"],
            priority=node["priority"],
            task_type=node["type"],
            acceptance=node["acceptance_criteria"],
            description=goal,
            source_goal=goal,
            parent_task_id=node.get("parent_node_id"),
            depends_on_task_ids=node.get("depends_on_node_ids", []),
            plan_node_id=node["node_id"],
        )
        preview["id"] = node["node_id"]
        preview["parent_task_id"] = node.get("parent_node_id")
        preview["depends_on_task_ids"] = list(node.get("depends_on_node_ids", []))
        previews.append(preview)
    return previews


def materialize_plan_nodes(
    root: Path,
    existing_tasks: list[dict],
    nodes: list[dict],
    goal: str,
    plan_draft_id: str | None = None,
) -> list[dict]:
    planned: list[dict] = []
    node_to_task_id: dict[str, str] = {}
    for node in nodes:
        node_id = node.get("node_id") or node.get("id")
        record = build_task_record(
            root,
            existing_tasks + planned,
            node["title"],
            priority=node["priority"],
            task_type=node["type"],
            acceptance=node.get("acceptance_criteria"),
            description=goal,
            source_goal=goal,
            plan_draft_id=plan_draft_id,
            plan_node_id=node_id,
        )
        planned.append(record)
        node_to_task_id[node_id] = record["id"]
    for record, node in zip(planned, nodes):
        parent_node_id = node.get("parent_node_id") or node.get("parent_task_id")
        record["parent_task_id"] = node_to_task_id.get(parent_node_id) if parent_node_id else None
        dependency_ids = node.get("depends_on_node_ids") or node.get("depends_on_task_ids") or []
        record["depends_on_task_ids"] = [node_to_task_id[item] for item in dependency_ids if item in node_to_task_id]
    return planned


def build_goal_nodes(goal: str, priority: str) -> list[dict]:
    base_type = classify_task(goal)
    lowered = goal.lower()
    if base_type == "bug_fix" and any(keyword in lowered for keyword in ["时间", "状态", "上下文", "承接", "同步"]):
        return attach_plan_relations(
            summarize_goal(goal),
            [
                plan_node("scope", "梳理现象与影响范围：{goal}", "bug_fix", priority, ["明确错误表现", "列出受影响的状态或文案", "确认需要保持不变的既有行为"]),
                plan_node("root_cause", "排查时间锚点与承接逻辑：{goal}", "bug_fix", priority, ["定位真实时间来源", "定位旧上下文继续承接的入口", "确认根因链路"]),
                plan_node("fix", "修复时间状态同步：{goal}", "bug_fix", priority, ["状态根据当前真实时间更新", "动作、内容、语言与时间一致", "避免沿用数小时前的状态"]),
                plan_node("regression", "补充跨时段回归验证：{goal}", "testing", priority, ["覆盖同小时、跨小时、隔夜场景", "验证旧会话不会污染当前时间状态", "给出验证步骤或测试结果"]),
                plan_node("record", "更新记录与验收说明：{goal}", "documentation", "medium", ["记录根因和修复点", "记录验证范围", "补充后续观察项"]),
            ],
        )
    if base_type == "complex_coding" and looks_like_system_build_goal(goal):
        return build_system_goal_nodes(goal, priority)
    return attach_plan_relations(summarize_goal(goal), build_generic_goal_nodes(goal, base_type, priority))


def build_generic_goal_nodes(goal: str, base_type: str, priority: str) -> list[dict]:
    template = GOAL_TEMPLATES.get(base_type, GOAL_TEMPLATES["complex_coding"])
    nodes: list[dict] = []
    for index, item in enumerate(template, start=1):
        title_template, task_type, default_priority = item[:3]
        acceptance = item[3] if len(item) > 3 else None
        task_priority = priority if default_priority == "high" else default_priority
        nodes.append(plan_node(f"step_{index}", title_template, task_type, task_priority, acceptance))
    return nodes


def attach_plan_relations(goal_summary: str, nodes: list[dict]) -> list[dict]:
    if not nodes:
        return []
    root_node_id = nodes[0]["node_id"]
    previous_node_id = None
    adjusted: list[dict] = []
    for index, node in enumerate(nodes):
        item = dict(node)
        item["title"] = item["title"].replace("{goal}", goal_summary)
        if index == 0:
            item["parent_node_id"] = None
            item["depends_on_node_ids"] = []
        else:
            item["parent_node_id"] = root_node_id
            item["depends_on_node_ids"] = [previous_node_id] if previous_node_id else []
        adjusted.append(item)
        previous_node_id = item["node_id"]
    return adjusted


def plan_node(
    node_id: str,
    title: str,
    task_type: str,
    priority: str,
    acceptance: list[str] | None = None,
    parent_node_id: str | None = None,
    depends_on_node_ids: list[str] | None = None,
) -> dict:
    return {
        "node_id": node_id,
        "title": title,
        "type": task_type,
        "priority": priority,
        "acceptance_criteria": acceptance or default_acceptance(task_type),
        "parent_node_id": parent_node_id,
        "depends_on_node_ids": depends_on_node_ids or [],
    }


def classify_task(title: str) -> str:
    lowered = title.lower()
    for task_type, keywords in TYPE_KEYWORDS:
        if any(keyword.lower() in lowered for keyword in keywords):
            return task_type
    if looks_like_bug_report(lowered):
        return "bug_fix"
    if looks_like_system_build_goal(title):
        return "complex_coding"
    if any(word in lowered for word in ["实现", "开发", "新增", "功能"]):
        return "complex_coding" if len(title) >= 14 else "simple_coding"
    return "simple_coding"


def complexity_for(task_type: str) -> str:
    if task_type in {"architecture", "complex_coding", "bug_fix", "deployment", "code_review"}:
        return "high"
    if task_type in {"testing", "ui_design", "data_processing"}:
        return "medium"
    return "low"


def default_acceptance(task_type: str) -> list[str]:
    if task_type == "documentation":
        return ["文档内容准确", "示例命令可执行", "边界和限制说明清楚"]
    if task_type == "testing":
        return ["新增或更新测试用例", "测试命令通过", "覆盖核心成功和失败路径"]
    if task_type == "bug_fix":
        return ["说明根因", "修复问题", "补充回归测试或验证步骤"]
    return ["实现目标功能", "更新必要文档或记录", "通过相关测试或给出验证结果"]


def looks_like_bug_report(text: str) -> bool:
    return sum(1 for keyword in BUG_SIGNAL_KEYWORDS if keyword in text) >= 2


def summarize_goal(goal: str, max_length: int = 26) -> str:
    normalized = " ".join(goal.split())
    parts = [part.strip(" ，。；：,.") for part in re.split(r"[，。；：\n]", normalized) if part.strip(" ，。；：,.")]
    summary = parts[0] if parts else normalized
    if len(summary) <= max_length:
        return summary
    return summary[: max_length - 1].rstrip() + "…"


def looks_like_system_build_goal(text: str) -> bool:
    return any(keyword in text for keyword in SYSTEM_BUILD_KEYWORDS) and any(
        keyword in text for keyword in ["开发", "做", "搭建", "建立", "实现"]
    )


def build_system_goal_nodes(goal: str, priority: str) -> list[dict]:
    system_name = extract_system_name(goal)
    modules = extract_goal_modules(goal)
    nodes: list[dict] = [
        plan_node("scope", "梳理系统范围与模块边界：{goal}", "architecture", priority, ["明确系统目标", "列出核心模块", "说明本阶段不做的范围"]),
        plan_node("design", "设计核心数据与接口：{goal}", "architecture", priority, ["明确核心数据结构", "明确模块之间的接口", "说明关键约束和异常处理"], parent_node_id="scope", depends_on_node_ids=["scope"]),
    ]
    if modules:
        module_node_ids: list[str] = []
        for module in modules:
            node_id = f"module_{len(module_node_ids) + 1}"
            module_node_ids.append(node_id)
            nodes.append(
                plan_node(
                    node_id,
                    f"实现{module}：{{goal}}",
                    infer_module_task_type(module),
                    priority,
                    module_acceptance(module),
                    parent_node_id="scope",
                    depends_on_node_ids=["design"],
                )
            )
        testing_deps = module_node_ids
    else:
        nodes.append(
            plan_node(
                "core",
                "实现核心能力：{goal}",
                "complex_coding",
                priority,
                ["完成核心业务流程", "保留后续扩展空间", "给出可验证的阶段成果"],
                parent_node_id="scope",
                depends_on_node_ids=["design"],
            )
        )
        testing_deps = ["core"]
    nodes.extend(
        [
            plan_node(
                "testing",
                "补充测试与验收：{goal}",
                "testing",
                priority,
                ["覆盖主流程", "覆盖关键失败路径", "给出测试结果或验证步骤"],
                parent_node_id="scope",
                depends_on_node_ids=testing_deps,
            ),
            plan_node(
                "record",
                "更新文档与交付记录：{goal}",
                "documentation",
                "medium",
                ["更新使用说明或接口说明", "记录验收结论", "记录后续待办"],
                parent_node_id="scope",
                depends_on_node_ids=["testing"],
            ),
        ]
    )
    return [dict(node, title=node["title"].replace("{goal}", system_name)) for node in nodes]


def extract_system_name(goal: str) -> str:
    normalized = " ".join(goal.split())
    match = re.search(r"(?:开发|搭建|建立|实现|做一个|做一套|做)(.+?(?:系统|平台|后台|中台|管理端|管理后台))", normalized)
    if match:
        return match.group(1).strip(" ，。；：,.")
    return summarize_goal(goal)


def extract_goal_modules(goal: str) -> list[str]:
    normalized = " ".join(goal.split())
    for keyword in MODULE_HINT_KEYWORDS:
        if keyword not in normalized:
            continue
        section = normalized.split(keyword, 1)[1]
        section = re.split(r"[。；;!！?？]", section, 1)[0]
        modules = split_modules(section)
        if modules:
            return modules[:4]
    return []


def split_modules(section: str) -> list[str]:
    text = section.strip(" ：:,，。；;")
    if not text:
        return []
    text = re.sub(r"^(例如|比如|像|主要是)", "", text).strip(" ：:,，。；;")
    parts = re.split(r"[、,，/]|以及|及|和|并且|并|还有", text)
    cleaned: list[str] = []
    for part in parts:
        item = part.strip(" ：:,，。；;")
        if not item or len(item) > 18:
            continue
        if item not in cleaned:
            cleaned.append(item)
    return cleaned


def infer_module_task_type(module: str) -> str:
    if any(keyword in module for keyword in ["页面", "后台", "管理", "前端", "界面"]):
        return "ui_design"
    if any(keyword in module for keyword in ["文档", "说明"]):
        return "documentation"
    if any(keyword in module for keyword in ["测试", "验证"]):
        return "testing"
    return "complex_coding"


def module_acceptance(module: str) -> list[str]:
    if infer_module_task_type(module) == "ui_design":
        return [f"{module}可用", "主流程交互清楚", "与现有系统风格一致或说明差异"]
    if infer_module_task_type(module) == "testing":
        return [f"{module}覆盖主流程", "覆盖关键异常路径", "输出验证结果"]
    if infer_module_task_type(module) == "documentation":
        return [f"{module}内容完整", "示例或说明准确", "与当前实现一致"]
    return [f"{module}实现完成", f"{module}支持核心业务场景", "给出必要的验证方式或测试结果"]


def next_task_id(tasks: list[dict]) -> str:
    from aios.utils.text import today

    date_part = today().replace("-", "")
    pattern = re.compile(rf"^TASK-{date_part}-(\d{{3}})$")
    max_number = 0
    for task in tasks:
        match = pattern.match(task.get("id", ""))
        if match:
            max_number = max(max_number, int(match.group(1)))
    return f"TASK-{date_part}-{max_number + 1:03d}"


def next_plan_draft_id(drafts: list[dict]) -> str:
    from aios.utils.text import today

    date_part = today().replace("-", "")
    pattern = re.compile(rf"^DRAFT-{date_part}-(\d{{3}})$")
    max_number = 0
    for draft in drafts:
        match = pattern.match(draft.get("draft_id", ""))
        if match:
            max_number = max(max_number, int(match.group(1)))
    return f"DRAFT-{date_part}-{max_number + 1:03d}"


def write_tasks_markdown(path: Path, tasks: list[dict]) -> None:
    lines = ["# 任务列表", ""]
    for status, title in [("todo", "待处理"), ("running", "进行中"), ("done", "已完成")]:
        grouped = [task for task in tasks if task["status"] == status]
        lines.extend([f"## {title}", ""])
        if not grouped:
            lines.extend(["暂无。", ""])
            continue
        for task in grouped:
            checked = "x" if status == "done" else " "
            lines.append(f"- [{checked}] {task['id']} {task['title']}")
            lines.append(f"  - 类型：{task['type']}")
            lines.append(f"  - 优先级：{task['priority']}")
            lines.append(f"  - 推荐模型：{task['recommended_model']}")
            if task.get("parent_task_id"):
                lines.append(f"  - 父任务：{task['parent_task_id']}")
            if task.get("depends_on_task_ids"):
                lines.append(f"  - 依赖任务：{', '.join(task['depends_on_task_ids'])}")
            lines.append("  - 验收标准：")
            lines.extend(f"    - {item}" for item in task["acceptance_criteria"])
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
