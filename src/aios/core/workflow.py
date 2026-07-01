from __future__ import annotations

from pathlib import Path

from aios.core.tasks import complete_task
from aios.utils.text import append_section, today


def finalize_task(
    root: Path,
    task_id: str,
    summary: str,
    actual_model: str | None = None,
    test_command: str | None = None,
    test_result: str | None = None,
) -> dict:
    task = complete_task(root, task_id, summary)
    aios_dir = root / ".aios"
    details = []
    if actual_model:
        details.append(f"- 实际执行模型：{actual_model}")
    if test_command:
        details.append(f"- 测试命令：{test_command}")
    if test_result:
        details.append(f"- 测试结果：{test_result}")
    detail_block = "\n".join(details) if details else "- 由执行模型或开发者在任务总结中补充。"
    body = f"""### {task['id']}

完成内容：

- {summary}

影响范围：

{detail_block}
"""
    append_section(aios_dir / "changelog.md", today(), body)
    append_section(aios_dir / "memory.md", f"{today()} {task['id']}", summary)
    return task
