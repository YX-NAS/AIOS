from __future__ import annotations

from pathlib import Path

from aios.core.tasks import complete_task
from aios.utils.text import append_section, today


def finalize_task(root: Path, task_id: str, summary: str) -> dict:
    task = complete_task(root, task_id, summary)
    aios_dir = root / ".aios"
    body = f"""### {task['id']}

完成内容：

- {summary}

影响范围：

- 由执行模型或开发者在任务总结中补充。
"""
    append_section(aios_dir / "changelog.md", today(), body)
    append_section(aios_dir / "memory.md", f"{today()} {task['id']}", summary)
    return task
