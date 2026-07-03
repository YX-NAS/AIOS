"""Cross-model review workflow for AIOS.

Enables automatic creation of review tasks that use a different model
to review the output of a completed task. Supports structured review
conclusions and automatic re-routing on review failure.

Key concepts:
- Review task: A special subtask created after a primary task completes,
  routed to a model different from the one that executed the original.
- Review focus: What to review — correctness, code quality, security, etc.
- Review status flow: pending -> in_progress -> approved/changes_requested
"""

from __future__ import annotations

from pathlib import Path

from aios.core.tasks import (
    build_task_record,
    create_task,
    get_task,
    load_tasks,
    save_tasks,
    set_task_status,
    update_task_fields,
)
from aios.core.router import resolve_models_for_task, route_task
from aios.core.templates import DEFAULT_ROUTING
from aios.utils.json_utils import read_json, write_json
from aios.utils.text import now_iso

# Review focus definitions with their recommended model types
REVIEW_FOCUS_DEFINITIONS: dict[str, dict] = {
    "correctness": {
        "label": "功能正确性审查",
        "description": "验证实现是否满足需求，逻辑是否正确",
        "task_type": "code_review",
        "prompt_template": "请审查以下任务的实现是否正确：\n\n{task_summary}\n\n重点关注：\n- 功能是否符合验收标准\n- 边界条件是否正确处理\n- 是否存在逻辑错误",
    },
    "code_quality": {
        "label": "代码质量审查",
        "description": "审查代码风格、可维护性和最佳实践",
        "task_type": "code_review",
        "prompt_template": "请审查以下代码的质量：\n\n{task_summary}\n\n重点关注：\n- 命名是否清晰\n- 结构是否合理\n- 是否符合最佳实践\n- 是否有潜在的性能问题",
    },
    "security": {
        "label": "安全性审查",
        "description": "审查是否存在安全漏洞和风险",
        "task_type": "code_review",
        "prompt_template": "请审查以下实现的安全性：\n\n{task_summary}\n\n重点关注：\n- 是否存在注入风险\n- 权限控制是否正确\n- 敏感数据是否妥善处理",
    },
    "testing": {
        "label": "测试覆盖审查",
        "description": "审查测试是否充分覆盖关键路径",
        "task_type": "testing",
        "prompt_template": "请审查以下任务的测试覆盖：\n\n{task_summary}\n\n重点关注：\n- 主流程是否被测试\n- 边界和异常路径是否有测试\n- 测试断言是否充分",
    },
}

# Default review result structure
REVIEW_RESULT_STATUSES = ["approved", "changes_requested", "comment"]


def review_tasks_path(root: Path) -> Path:
    """Get the path to review tasks storage."""
    from aios.core.paths import require_aios
    return require_aios(root) / "reviews.json"


def load_reviews(root: Path) -> dict:
    """Load review records."""
    return read_json(review_tasks_path(root), {"reviews": {}})


def save_reviews(root: Path, reviews: dict) -> None:
    """Save review records."""
    write_json(review_tasks_path(root), reviews)


def create_review_task(
    root: Path,
    task_id: str,
    *,
    focus_areas: list[str] | None = None,
    reviewer_model: str | None = None,
    prompt_override: str | None = None,
) -> dict:
    """Create a review task for a completed primary task.

    The review task is automatically routed to a model different from
    the one used by the original task, following the principle that
    cross-model review catches issues the authoring model would miss.

    Args:
        root: Project root.
        task_id: ID of the completed primary task.
        focus_areas: List of review focus areas (e.g. ['correctness', 'code_quality']).
        reviewer_model: Explicit model to use for review (overrides auto-routing).
        prompt_override: Custom review prompt.

    Returns:
        Dict with 'review_task', 'review_record', and 'original_task'.
    """
    original = get_task(root, task_id)

    if original.get("status") != "done":
        raise ValueError(f"Task {task_id} is not completed. Only done tasks can be reviewed.")

    foci = focus_areas or ["correctness", "code_quality"]
    for focus in foci:
        if focus not in REVIEW_FOCUS_DEFINITIONS:
            raise ValueError(f"Unknown review focus: {focus}. Available: {', '.join(REVIEW_FOCUS_DEFINITIONS)}")

    # Determine review task type from focus areas
    review_type = "code_review"
    for focus in foci:
        defn = REVIEW_FOCUS_DEFINITIONS.get(focus, {})
        ft = defn.get("task_type")
        if ft:
            review_type = ft
            break

    # Select a reviewer model different from the original
    if reviewer_model:
        review_model = reviewer_model
    else:
        review_model = _select_reviewer_model(root, original, review_type)

    # Create the review task
    review_title = f"审查：{original['title']}"
    if len(foci) <= 2:
        focus_labels = "、".join(REVIEW_FOCUS_DEFINITIONS[f]["label"] for f in foci)
        review_title = f"{focus_labels}：{original['title']}"

    existing_tasks = load_tasks(root)
    review_task = build_task_record(
        root,
        existing_tasks,
        review_title,
        priority=original.get("priority", "medium"),
        task_type=review_type,
        description=f"对任务 {task_id} 的输出进行审查。审查范围：{'、'.join(foci)}",
        depends_on_task_ids=[task_id],
    )
    review_task["recommended_model"] = review_model
    review_task["fallback_models"] = _reviewer_fallback_models(root, review_model, review_type)
    review_task["is_review_task"] = True
    review_task["review_source_task_id"] = task_id
    review_task["review_focus_areas"] = foci

    existing_tasks.append(review_task)
    save_tasks(root, existing_tasks)

    # Build review record
    reviews = load_reviews(root)
    reviews_data = reviews.get("reviews", {})
    review_record = {
        "review_id": review_task["id"],
        "source_task_id": task_id,
        "source_task_title": original["title"],
        "reviewer_model": review_model,
        "focus_areas": foci,
        "status": "pending",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "result": None,
        "notes": None,
    }
    reviews_data[review_task["id"]] = review_record
    reviews["reviews"] = reviews_data
    save_reviews(root, reviews)

    # Update original task to mark it as under review
    update_task_fields(
        root,
        task_id,
        {
            "review_status": "pending",
            "review_task_id": review_task["id"],
        },
    )

    return {
        "review_task": review_task,
        "review_record": review_record,
        "original_task": get_task(root, task_id),
        "review_model": review_model,
        "review_prompt": prompt_override or _build_review_prompt(original, foci),
    }


def complete_review(
    root: Path,
    review_task_id: str,
    status: str,
    *,
    issues: list[dict] | None = None,
    notes: str | None = None,
) -> dict:
    """Complete a review task and update the source task accordingly.

    Args:
        root: Project root.
        review_task_id: ID of the review task.
        status: Review result — 'approved', 'changes_requested', or 'comment'.
        issues: List of issue dicts with 'severity', 'description', 'suggestion'.
        notes: Free-form review notes.

    Returns:
        Dict with updated review record and source task.
    """
    if status not in REVIEW_RESULT_STATUSES:
        raise ValueError(f"Invalid review status: {status}. Must be one of: {', '.join(REVIEW_RESULT_STATUSES)}")

    review_task = get_task(root, review_task_id)
    if not review_task.get("is_review_task"):
        raise ValueError(f"Task {review_task_id} is not a review task.")

    source_task_id = review_task.get("review_source_task_id")
    if not source_task_id:
        raise ValueError(f"Review task {review_task_id} has no source task.")

    # Update review record
    reviews = load_reviews(root)
    reviews_data = reviews.get("reviews", {})

    if review_task_id not in reviews_data:
        raise ValueError(f"Review record not found for {review_task_id}")

    review_record = reviews_data[review_task_id]
    review_record["status"] = status
    review_record["result"] = {
        "issues": issues or [],
        "notes": notes,
    }
    review_record["completed_at"] = now_iso()
    review_record["updated_at"] = now_iso()
    reviews_data[review_task_id] = review_record
    reviews["reviews"] = reviews_data
    save_reviews(root, reviews)

    # Update review task status
    set_task_status(root, review_task_id, "done")
    update_task_fields(
        root,
        review_task_id,
        {
            "completion_summary": f"审查结论：{status}",
            "review_result_status": status,
            "review_issues_count": len(issues or []),
        },
    )

    # Update source task based on review result
    if status == "changes_requested":
        issue_descriptions = [i.get("description", "") for i in (issues or [])]
        update_task_fields(
            root,
            source_task_id,
            {
                "review_status": "changes_requested",
                "status": "todo",
                "review_feedback": notes or "; ".join(issue_descriptions[:3]),
            },
        )
    elif status == "approved":
        update_task_fields(
            root,
            source_task_id,
            {
                "review_status": "approved",
            },
        )
    else:  # comment
        update_task_fields(
            root,
            source_task_id,
            {
                "review_status": "reviewed",
                "review_feedback": notes,
            },
        )

    return {
        "review_record": review_record,
        "review_task": get_task(root, review_task_id),
        "source_task": get_task(root, source_task_id),
    }


def get_review_for_task(root: Path, task_id: str) -> dict | None:
    """Get the review record associated with a task."""
    task = get_task(root, task_id)
    review_task_id = task.get("review_task_id")
    if not review_task_id:
        return None

    reviews = load_reviews(root)
    reviews_data = reviews.get("reviews", {})
    return reviews_data.get(review_task_id)


def _select_reviewer_model(root: Path, task: dict, review_type: str) -> str:
    """Select a reviewer model different from the task's recommended model."""
    original_model = task.get("recommended_model") or ""
    task_type = task.get("type") or "simple_coding"
    rule = DEFAULT_ROUTING.get(review_type, DEFAULT_ROUTING["code_review"])
    preferred, fallback = resolve_models_for_task(
        root,
        review_type,
        list(rule["preferred_models"]),
        list(rule["fallback_models"]),
    )

    # Try to pick a model different from the original
    candidates = preferred + fallback
    for model_id in candidates:
        if model_id != original_model:
            return model_id

    # If all match, pick the first fallback, or the first available
    if fallback and fallback[0] != original_model:
        return fallback[0]
    return candidates[0] if candidates else "gpt-5.5"


def _reviewer_fallback_models(root: Path, reviewer_model: str, review_type: str) -> list[str]:
    """Get fallback models for a reviewer, excluding the selected reviewer."""
    rule = DEFAULT_ROUTING.get(review_type, DEFAULT_ROUTING["code_review"])
    _, fallback = resolve_models_for_task(
        root,
        review_type,
        list(rule["preferred_models"]),
        list(rule["fallback_models"]),
    )
    return [m for m in fallback if m != reviewer_model]


def _build_review_prompt(task: dict, focus_areas: list[str]) -> str:
    """Build a review prompt based on task details and focus areas."""
    parts: list[str] = []
    parts.append(f"## 任务审查\n\n审查任务：{task['title']}")
    if task.get("completion_summary"):
        parts.append(f"\n完成总结：{task['completion_summary']}")

    for focus in focus_areas:
        defn = REVIEW_FOCUS_DEFINITIONS.get(focus)
        if defn:
            parts.append(f"\n### {defn['label']}\n{defn['description']}")

    parts.append("\n## 审查输出\n请提供结构化的审查结论，包括：")
    parts.append("- 审查状态：approved / changes_requested / comment")
    parts.append("- 发现的问题列表（如有）")
    parts.append("- 改进建议")

    return "\n".join(parts)
