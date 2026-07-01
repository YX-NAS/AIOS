from __future__ import annotations

from pathlib import Path

from aios.core.paths import aios_path, require_aios
from aios.utils.json_utils import read_json, write_json
from aios.utils.text import now_iso

SCORES_FILE = "model-scores.json"


def save_score(root: Path, task_id: str, model: str, score: int, note: str | None = None, task_type: str | None = None) -> dict:
    require_aios(root)
    if not 1 <= score <= 5:
        raise ValueError("Score must be between 1 and 5.")
    path = aios_path(root) / SCORES_FILE
    entries = read_json(path, [])
    entry = {
        "task_id": task_id,
        "model": model,
        "task_type": task_type or "unknown",
        "score": score,
        "note": note or "",
        "scored_at": now_iso(),
    }
    entries.append(entry)
    write_json(path, entries)
    return entry


def load_scores(root: Path) -> list[dict]:
    try:
        path = aios_path(root) / SCORES_FILE
    except FileNotFoundError:
        return []
    return read_json(path, [])


def model_score_summary(root: Path, model_id: str | None = None) -> dict:
    scores = load_scores(root)
    if not scores:
        return {"models": [], "total_entries": 0}

    grouped: dict[str, dict] = {}
    for entry in scores:
        key = entry["model"]
        if model_id and key != model_id:
            continue
        if key not in grouped:
            grouped[key] = {"model": key, "total": 0, "sum": 0, "by_type": {}}
        grouped[key]["total"] += 1
        grouped[key]["sum"] += entry["score"]
        task_type = entry.get("task_type", "unknown")
        if task_type not in grouped[key]["by_type"]:
            grouped[key]["by_type"][task_type] = {"count": 0, "sum": 0}
        grouped[key]["by_type"][task_type]["count"] += 1
        grouped[key]["by_type"][task_type]["sum"] += entry["score"]

    result = []
    for data in grouped.values():
        avg = round(data["sum"] / data["total"], 2) if data["total"] else 0
        by_type = {}
        for tt, tt_data in data["by_type"].items():
            tt_avg = round(tt_data["sum"] / tt_data["count"], 2) if tt_data["count"] else 0
            by_type[tt] = {"count": tt_data["count"], "avg_score": tt_avg}
        result.append({
            "model": data["model"],
            "total_scores": data["total"],
            "avg_score": avg,
            "by_task_type": by_type,
        })

    return {"models": result, "total_entries": len(scores)}
