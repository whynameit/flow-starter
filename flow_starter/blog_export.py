from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from .models import Goal, ScheduleOption, TaskBlock, format_dt
from .obsidian import slugify

BlogFormat = Literal["generic", "al-folio"]


def write_blog_draft(
    goal: Goal,
    tasks: list[TaskBlock],
    option: ScheduleOption,
    output_dir: Path,
    blog_format: BlogFormat = "generic",
) -> Path:
    if blog_format == "al-folio" and output_dir.name != "_posts":
        output_dir = output_dir / "_posts"

    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{datetime.now().strftime('%Y-%m-%d')}-{slugify(goal.title)}.md"
    path = output_dir / filename
    content = render_al_folio_draft(goal, tasks, option) if blog_format == "al-folio" else render_blog_draft(goal, tasks, option)
    path.write_text(content, encoding="utf-8")
    return path


def render_blog_draft(goal: Goal, tasks: list[TaskBlock], option: ScheduleOption) -> str:
    task_lines = "\n".join(f"- {task.title}：{task.outcome}" for task in tasks)
    sessions = "\n".join(
        f"- {format_dt(session.start)} - {session.end.strftime('%H:%M')}：{session.title}"
        for session in option.sessions
    )
    return f"""---
title: "{goal.title}"
date: {datetime.now().strftime('%Y-%m-%d')}
draft: true
tags:
  - learning
  - flow-starter
---

## 学习目标

{goal.title}

## 公开学习路径

{task_lines}

## 计划安排

{sessions}

## 理解摘要

这里写公开可分享的技术理解。不要直接复制私人 Obsidian 原文。

## 后续问题

- 还有哪些地方需要实验验证？
- 哪些内容适合补图、补代码、补参考资料？
"""


def render_al_folio_draft(goal: Goal, tasks: list[TaskBlock], option: ScheduleOption) -> str:
    title = goal.title.replace('"', '\\"')
    description = build_description(goal, tasks).replace('"', '\\"')
    slug = slugify(goal.title)
    year = datetime.now().year
    blog_author = os.environ.get("BLOG_AUTHOR", "whynameit")
    blog_title = os.environ.get("BLOG_TITLE", "rh's blog")
    blog_base_url = os.environ.get("BLOG_BASE_URL", "https://whynameit.github.io").rstrip("/")
    citation_key = f"flowstarter{year}{ascii_identifier(goal.title)}"
    task_lines = "\n".join(
        f"- **{task.title}**：{task.outcome}" for task in tasks
    )
    session_lines = "\n".join(
        f"- {format_dt(session.start)} - {session.end.strftime('%H:%M')}：{session.title}"
        for session in option.sessions
    )
    return f"""---
layout: post
title: "{title}"
date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
description: "{description}"
tags: [learning, flow-starter]
categories: [learning-notes]
featured: false
giscus_comments: false
toc:
  sidebar: left
---

> TL;DR: 这是一份从 flow-starter 生成的公开学习草稿。私人思考、课程细节和未整理内容仍保留在 Obsidian 中。

## 1. 学习目标

{goal.title}

## 2. 任务拆分

{task_lines}

## 3. 计划安排

{session_lines}

## 4. 理解摘要

这里写公开可分享的技术理解。建议只保留经过你确认的概念、实验过程和工程结论。

## 5. 问题与后续实验

- 哪些结论还需要代码或数据验证？
- 哪些地方适合补图、补公式、补参考资料？
- 这篇文章发布前需要删掉哪些私人信息？

## 参考文献

[1] 待补充

## 引用

如果您需要引用本文，请参考：

```bibtex
@article{{{citation_key},
  title={{{goal.title}}},
  author={{{blog_author}}},
  journal={{{blog_title}}},
  year={{{year}}},
  url={{{blog_base_url}/blog/{year}/{slug}/}}
}}
```
"""


def build_description(goal: Goal, tasks: list[TaskBlock]) -> str:
    if goal.description:
        return goal.description[:120]
    if tasks:
        return f"围绕{tasks[0].title}等任务整理的学习计划与技术理解草稿。"
    return "flow-starter 生成的学习计划与技术理解草稿。"


def ascii_identifier(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "", value.lower())
    if text:
        return text[:32]
    return "flowstarter" + hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
