"""Adaptive context management for AIOS.

Handles token budget control, context quality scoring, and layered
compaction strategies for Context Pack content.

Features:
- Token budget estimation against model context windows
- Layered trimming strategy (file layer first, then module layer)
- Context quality scoring (relevance, completeness, redundancy)
- Pack content validation and warnings
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aios.core.models import get_model
from aios.core.context_builder import estimate_tokens

# Default context window utilization ratio (80% to leave room for conversation)
DEFAULT_WINDOW_RATIO = 0.8

# Minimum token budget — never trim below this
MIN_TOKEN_BUDGET = 2000

# Default model context windows when not configured
DEFAULT_CONTEXT_WINDOW = 128000

# Content layers in priority order (highest = trim last)
LAYER_PRIORITY = [
    "task_goal",       # Never trim
    "acceptance",      # Never trim
    "handoff_steps",   # Trim last
    "core_config",     # Trim if needed
    "file_contents",   # Trim first
    "scan_summary",    # Trim first
    "architecture",    # Keep if possible
]


@dataclass
class LayerInfo:
    """Information about a content layer in a Context Pack."""
    name: str
    content: str
    token_count: int
    priority: int  # Higher = trim later


def calculate_token_budget(
    root: Path,
    model_id: str | None = None,
    manual_budget: int | None = None,
) -> int:
    """Calculate the token budget for a Context Pack.

    Priority: manual_budget > model context window * 0.8 > default

    Args:
        root: Project root.
        model_id: Target model ID for context window lookup.
        manual_budget: Explicit token budget override.

    Returns:
        Token budget integer.
    """
    if manual_budget is not None and manual_budget > 0:
        return manual_budget

    if model_id:
        model = get_model(root, model_id)
        if model and model.get("context_window"):
            return max(int(model["context_window"] * DEFAULT_WINDOW_RATIO), MIN_TOKEN_BUDGET)

    return int(DEFAULT_CONTEXT_WINDOW * DEFAULT_WINDOW_RATIO)


def token_budget_report(
    root: Path,
    content: str,
    model_id: str | None = None,
    manual_budget: int | None = None,
) -> dict:
    """Generate a token budget report for content.

    Args:
        root: Project root.
        content: Content string to analyze.
        model_id: Target model ID.
        manual_budget: Explicit budget.

    Returns:
        Report dict with estimated tokens, budget, and status.
    """
    estimated = estimate_tokens(content)
    budget = calculate_token_budget(root, model_id=model_id, manual_budget=manual_budget)
    within_budget = estimated <= budget
    utilization_pct = round(estimated / max(budget, 1) * 100, 1)

    status = "ok"
    warning = None
    if not within_budget:
        excess = estimated - budget
        status = "over_budget"
        warning = f"Content is {excess} tokens over the {budget} token budget ({utilization_pct}%)."
    elif utilization_pct > 90:
        status = "near_limit"
        warning = f"Content is at {utilization_pct}% of budget. Limited room for conversation context."

    return {
        "estimated_tokens": estimated,
        "budget": budget,
        "within_budget": within_budget,
        "utilization_pct": utilization_pct,
        "status": status,
        "warning": warning,
        "model_id": model_id,
        "model_context_window": get_model(root, model_id).get("context_window") if model_id and get_model(root, model_id) else None,
    }


def trim_content_to_budget(
    content: str,
    budget: int,
    *,
    layers: list[LayerInfo] | None = None,
) -> dict:
    """Trim content to fit within a token budget.

    Uses a layered approach: layers with lower priority are trimmed first.
    If no layer information is provided, trims from the end of the content.

    Args:
        content: Full content string.
        budget: Maximum token count.
        layers: Optional list of LayerInfo for structured trimming.

    Returns:
        Dict with 'content' (trimmed), 'original_tokens', 'trimmed_tokens',
        'removed_sections', and 'within_budget'.
    """
    current_tokens = estimate_tokens(content)
    if current_tokens <= budget:
        return {
            "content": content,
            "original_tokens": current_tokens,
            "trimmed_tokens": current_tokens,
            "removed_sections": [],
            "within_budget": True,
            "trimmed": False,
        }

    if layers:
        return _trim_layered_content(content, layers, budget, current_tokens)

    # Fallback: trim from end with ~ token-aware chunking
    removed_sections = ["(trimmed from end)"]
    # Approximate: 1 token ~ 4 characters for English, 2 for other
    chars_per_token = 4
    excess_tokens = current_tokens - budget
    chars_to_remove = min(excess_tokens * chars_per_token, len(content) // 2)
    keep_chars = max(MIN_TOKEN_BUDGET * chars_per_token, len(content) - chars_to_remove)

    trimmed = content[:keep_chars].rstrip()
    trimmed_tokens = estimate_tokens(trimmed)

    return {
        "content": trimmed,
        "original_tokens": current_tokens,
        "trimmed_tokens": trimmed_tokens,
        "removed_sections": removed_sections,
        "within_budget": trimmed_tokens <= budget,
        "trimmed": True,
    }


def _trim_layered_content(
    content: str,
    layers: list[LayerInfo],
    budget: int,
    current_tokens: int,
) -> dict:
    """Trim content by removing lower-priority layers."""
    sorted_layers = sorted(layers, key=lambda layer: layer.priority)
    removed_sections: list[str] = []
    kept_layers: list[str] = []
    kept_tokens = 0

    # Always keep the highest priority layers
    for layer in sorted_layers:
        if kept_tokens + layer.token_count <= budget:
            kept_layers.append(layer.content)
            kept_tokens += layer.token_count
        else:
            removed_sections.append(f"Removed layer: {layer.name} ({layer.token_count} tokens)")

    result_content = "\n\n".join(kept_layers)
    trimmed_tokens = estimate_tokens(result_content)

    return {
        "content": result_content,
        "original_tokens": current_tokens,
        "trimmed_tokens": trimmed_tokens,
        "removed_sections": removed_sections,
        "within_budget": trimmed_tokens <= budget,
        "trimmed": True,
    }


def score_context_quality(
    selected_files: list[dict],
    task: dict,
    quality_assessment: dict | None = None,
) -> dict:
    """Score the quality of a context selection for a task.

    Evaluates:
    - Relevance: How well the files match the task content
    - Completeness: Whether critical project areas are covered
    - Redundancy: How many low-relevance files are included

    Args:
        selected_files: List of selected file dicts with 'score' and 'path'.
        task: Task dict with 'type', 'title'.
        quality_assessment: Pre-computed quality assessment from smart_selection.

    Returns:
        Quality report with scores and recommendations.
    """
    if quality_assessment:
        return quality_assessment

    if not selected_files:
        return {
            "status": "critical",
            "message": "No files selected — Context Pack will be empty.",
            "scores": {"relevance": 0.0, "completeness": 0.0, "redundancy": 1.0},
            "recommendations": ["Add manual file annotations", "Check if project has source files"],
        }

    score_values = [f.get("score", 0) for f in selected_files]
    avg_score = sum(score_values) / len(score_values)
    high_count = sum(1 for s in score_values if s >= 5.0)
    low_count = sum(1 for s in score_values if s < 2.0)

    relevance = min(1.0, avg_score / 10.0)
    completeness = min(1.0, high_count / max(len(selected_files), 1) + 0.3)
    redundancy = low_count / max(len(selected_files), 1)

    # Determine overall status
    if relevance < 0.2:
        status = "critical"
    elif relevance < 0.4 or redundancy > 0.4:
        status = "warning"
    else:
        status = "ok"

    recommendations: list[str] = []
    if relevance < 0.4:
        recommendations.append("Consider refining task title for better keyword matching")
    if redundancy > 0.3:
        recommendations.append("Too many low-relevance files — reduce scope or add exclusions")
    if completeness < 0.5:
        recommendations.append("Key project areas may be missing — check manual annotations")

    return {
        "status": status,
        "scores": {
            "relevance": round(relevance, 2),
            "completeness": round(completeness, 2),
            "redundancy": round(redundancy, 2),
        },
        "high_relevance_count": high_count,
        "low_relevance_count": low_count,
        "average_score": round(avg_score, 2),
        "total_files": len(selected_files),
        "recommendations": recommendations,
    }


def validate_context_pack(
    content: str,
    task: dict,
    model_id: str | None = None,
) -> dict:
    """Validate a Context Pack for common issues.

    Checks: empty content, missing acceptance criteria, excessive length,
    missing key sections.

    Args:
        content: Full Context Pack content string.
        task: Task dict.
        model_id: Target model ID for budget check.

    Returns:
        Validation report with 'status' and 'issues'.
    """
    issues: list[dict] = []

    # Check for empty content
    if not content.strip():
        issues.append({
            "severity": "critical",
            "type": "empty_content",
            "message": "Context Pack is empty.",
        })

    # Check for acceptance criteria
    acceptance = task.get("acceptance_criteria") or []
    if not acceptance:
        issues.append({
            "severity": "warning",
            "type": "missing_acceptance",
            "message": "Task has no acceptance criteria defined.",
        })

    # Check for minimum length
    estimated = estimate_tokens(content)
    if estimated < 100:
        issues.append({
            "severity": "warning",
            "type": "minimal_content",
            "message": f"Context Pack is very short ({estimated} tokens). May lack sufficient context.",
        })

    # Check budget
    if model_id:
        model = get_model(None, model_id)
        context_window = model.get("context_window") if model else None
        if context_window and estimated > context_window:
            issues.append({
                "severity": "critical",
                "type": "exceeds_window",
                "message": f"Context Pack ({estimated} tokens) exceeds model context window ({context_window} tokens).",
            })

    # Check for key sections
    key_sections = ["任务目标", "验收标准", "相关文件", "###", "## "]
    for section in key_sections:
        if section not in content:
            issues.append({
                "severity": "info",
                "type": "missing_section",
                "message": f"May be missing section containing '{section}'.",
            })

    # Determine overall status
    has_critical = any(i["severity"] == "critical" for i in issues)
    has_warning = any(i["severity"] == "warning" for i in issues)

    if has_critical:
        status = "invalid"
    elif has_warning:
        status = "warning"
    else:
        status = "ok"

    return {
        "status": status,
        "issues": issues,
        "issue_count": len(issues),
        "critical_count": sum(1 for i in issues if i["severity"] == "critical"),
        "warning_count": sum(1 for i in issues if i["severity"] == "warning"),
        "token_estimate": estimated,
        "model_context_window": get_model(None, model_id).get("context_window") if model_id and get_model(None, model_id) else None,
    }
