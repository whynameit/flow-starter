from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from .models import Goal, ScheduleOption, TaskBlock, format_dt


def slugify(value: str, max_length: int = 60) -> str:
    text = value.lower().strip()
    text = re.sub(r"[^\w\u4e00-\u9fff]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return (text[:max_length].strip("-") or "studyflow-note")


def write_goal_note(
    goal: Goal,
    tasks: list[TaskBlock],
    option: ScheduleOption,
    vault_path: Path,
    folder: str = "StudyFlow",
) -> Path:
    note_dir = vault_path.expanduser() / folder
    note_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{datetime.now().strftime('%Y-%m-%d')}-{slugify(goal.title)}.md"
    path = note_dir / filename
    path.write_text(render_goal_note(goal, tasks, option), encoding="utf-8")
    return path


def render_goal_note(goal: Goal, tasks: list[TaskBlock], option: ScheduleOption) -> str:
    task_lines = []
    for task in tasks:
        criteria = "\n".join(f"    - {item}" for item in task.acceptance_criteria)
        task_lines.append(
            f"- [ ] **{task.title}** `{task.p50_minutes}/{task.p90_minutes}min`\n"
            f"  - 产物：{task.outcome}\n"
            f"  - 验收：\n{criteria or '    - 待补充'}"
        )

    session_lines = []
    for session in option.sessions:
        session_lines.append(
            f"- [ ] {format_dt(session.start)} - {session.end.strftime('%H:%M')} "
            f"**{session.title}**"
        )

    return f"""---
type: studyflow-goal
status: active
deadline: {format_dt(goal.deadline)}
created: {format_dt(goal.created_at)}
schedule_option: {option.id}
---

# {goal.title}

## 成功标准

{render_bullets(goal.success_criteria) or "- 待补充"}

## 任务块

{chr(10).join(task_lines)}

## 已选择日程

{chr(10).join(session_lines)}

## 课后/任务后记录

每个时间块结束后写：

- 实际用了多久：
- 完成了什么：
- 卡在哪里：
- 下一步是否需要重排：

## Claude 追问区

把自己的复述贴给 Claude，让它只问问题，不要直接长篇讲解。
"""


def render_bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def build_obsidian_uri(vault_path: Path, note_path: Path) -> str:
    vault_name = vault_path.expanduser().name
    relative = note_path.relative_to(vault_path.expanduser())
    return f"obsidian://open?vault={quote(vault_name)}&file={quote(str(relative))}"
