from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List

from .models import Goal, TaskBlock, tasks_from_dicts, to_jsonable


ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
PLACEHOLDER_API_KEYS = {
    "sk-ant-api03-your-key-here",
    "your-claude-api-key",
    "your-key-here",
}


class ClaudeConfigError(RuntimeError):
    pass


class ClaudeAPIError(RuntimeError):
    pass


class ClaudeResponseError(RuntimeError):
    pass


class ClaudeClient:
    def __init__(self, api_key: str = "", model: str = "", timeout_seconds: int = 90) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model or os.environ.get("CLAUDE_MODEL", "")
        self.timeout_seconds = timeout_seconds

    def is_configured(self) -> bool:
        return bool(self.api_key and self.model and not is_placeholder_api_key(self.api_key))

    def complete(self, prompt: str, max_tokens: int = 2500) -> str:
        if not self.api_key:
            raise ClaudeConfigError("Missing ANTHROPIC_API_KEY.")
        if is_placeholder_api_key(self.api_key):
            raise ClaudeConfigError(
                "ANTHROPIC_API_KEY still looks like a placeholder or incomplete key. "
                "Edit /Users/rh/Documents/Thinking & asking reminder/.env and paste the full key "
                "from Anthropic Console. Do not use your Claude Pro account password or Claude web session token."
            )
        if not self.model:
            raise ClaudeConfigError("Missing CLAUDE_MODEL.")

        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}],
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            ANTHROPIC_MESSAGES_URL,
            data=data,
            method="POST",
            headers={
                "content-type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": ANTHROPIC_VERSION,
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ClaudeAPIError(format_api_error(exc.code, detail)) from exc
        except urllib.error.URLError as exc:
            raise ClaudeAPIError(
                f"Could not reach Claude API. Check your network or proxy settings. Detail: {exc.reason}"
            ) from exc

        blocks = body.get("content") or []
        texts = [block.get("text", "") for block in blocks if block.get("type") == "text"]
        return "\n".join(texts).strip()


def format_api_error(status_code: int, detail: str) -> str:
    if status_code == 401:
        return (
            "Claude API authentication failed: ANTHROPIC_API_KEY is invalid. "
            "Claude Pro membership is not an API key; create an Anthropic API key, "
            "put it in /Users/rh/Documents/Thinking & asking reminder/.env, and run the command again."
        )
    if status_code == 400 and "credit balance is too low" in detail.lower():
        return (
            "Claude API key is valid, but the Anthropic API account has no available credits. "
            "Claude Pro membership is separate from API credits; add credits in Anthropic Console "
            "Plans & Billing, or run without --use-claude for now."
        )
    if status_code == 404:
        return (
            "Claude API request failed with 404. Check CLAUDE_MODEL in .env; "
            "the model name may be unavailable for this API account."
        )
    return f"Claude API error {status_code}: {detail}"


def is_placeholder_api_key(value: str) -> bool:
    key = value.strip().strip('"').strip("'")
    if not key:
        return True
    if key in PLACEHOLDER_API_KEYS:
        return True
    if "your-key" in key.lower() or "your_" in key.lower():
        return True
    return key.startswith("sk-ant-api") and len(key) < 40


def decompose_goal_with_claude(client: ClaudeClient, goal: Goal) -> List[TaskBlock]:
    prompt = build_decomposition_prompt(goal)
    text = client.complete(prompt, max_tokens=5000)
    try:
        payload = extract_json_object(text)
    except (ValueError, json.JSONDecodeError):
        repaired = client.complete(build_json_repair_prompt(text), max_tokens=5000)
        try:
            payload = extract_json_object(repaired)
        except (ValueError, json.JSONDecodeError) as exc:
            raise ClaudeResponseError("Claude returned task JSON that could not be parsed after one repair attempt.") from exc
    items = payload.get("tasks") or []
    if not isinstance(items, list) or not items:
        raise RuntimeError("Claude response did not contain a non-empty tasks list.")
    return tasks_from_dicts(items)


def revise_tasks_with_claude(
    client: ClaudeClient,
    goal: Goal,
    existing_tasks: List[TaskBlock],
    change_request: str,
    revision_history: List[Dict[str, Any]] | None = None,
) -> List[TaskBlock]:
    prompt = build_revision_prompt(goal, existing_tasks, change_request, revision_history=revision_history)
    text = client.complete(prompt, max_tokens=5000)
    try:
        payload = extract_json_object(text)
    except (ValueError, json.JSONDecodeError):
        repaired = client.complete(build_json_repair_prompt(text), max_tokens=5000)
        try:
            payload = extract_json_object(repaired)
        except (ValueError, json.JSONDecodeError) as exc:
            raise ClaudeResponseError("Claude returned revised task JSON that could not be parsed.") from exc
    items = payload.get("tasks") or []
    if not isinstance(items, list) or not items:
        raise RuntimeError("Claude revision response did not contain a non-empty tasks list.")
    return tasks_from_dicts(items)


def build_decomposition_prompt(goal: Goal) -> str:
    criteria = "\n".join(f"- {item}" for item in goal.success_criteria) or "- 用户能验收每个任务块是否完成"
    return f"""你是一个学习项目规划助手。请把用户目标拆成可以放进日程表的任务块。

目标：{goal.title}
补充说明：{goal.description or "无"}
截止时间：{goal.deadline.strftime("%Y-%m-%d %H:%M")}
成功标准：
{criteria}

请遵守：
1. 不要输出泛泛的“学习一下”，每个任务块必须有可验收产物。
2. 用 p50_minutes 和 p90_minutes 同时估时；用户的任务经常超时，所以 p90 要保守。
3. 标注 cognitive_load，只能是 low、medium、high。
4. 标注 depends_on，使用其他任务块的 id。
5. 如果任务适合拆开做，can_split=true。
6. 资源链接只放高可信来源或用户需要打开的资源。
7. 只输出 JSON，不要解释。

JSON 格式：
{{
  "tasks": [
    {{
      "id": "short_snake_case_id",
      "title": "任务块标题",
      "outcome": "完成后的具体产物",
      "p50_minutes": 60,
      "p90_minutes": 120,
      "cognitive_load": "high",
      "depends_on": [],
      "resources": ["https://example.com"],
      "acceptance_criteria": ["可以用一句话说清楚...", "本地跑通..."],
      "can_split": true
    }}
  ]
}}
"""


def build_revision_prompt(
    goal: Goal,
    existing_tasks: List[TaskBlock],
    change_request: str,
    revision_history: List[Dict[str, Any]] | None = None,
) -> str:
    tasks_json = json.dumps({"tasks": to_jsonable(existing_tasks)}, ensure_ascii=False, indent=2)
    history_json = json.dumps(revision_history or [], ensure_ascii=False, indent=2)
    return f"""你是一个学习项目规划助手。用户已经有一版任务拆解，现在想修正顺序、合并、删减或补充任务。

目标：{goal.title}
补充说明：{goal.description or "无"}
截止时间：{goal.deadline.strftime("%Y-%m-%d %H:%M")}

用户的修正要求：
{change_request}

此前已经确认过的修正历史，按时间从旧到新排列：
{history_json}

当前任务 JSON：
{tasks_json}

请输出修正后的完整任务列表，而不是只输出差异。

请遵守：
1. 本轮修正要求优先级最高；如果和历史修正冲突，以本轮为准。
2. 如果本轮没有明确推翻某条历史修正，必须保留此前每轮已经确认过的调整意图。
3. 可以根据用户要求调整顺序、合并任务、删除任务、拆分任务或补充任务。
4. 没变的任务尽量保留原 id；合并/新增任务使用新的 short_snake_case id。
5. depends_on 必须只引用最终列表中存在的 id。
6. 用 p50_minutes 和 p90_minutes 同时估时；合并任务要重新估时。
7. cognitive_load 只能是 low、medium、high。
8. 只输出 JSON，不要解释。

JSON 格式：
{{
  "tasks": [
    {{
      "id": "short_snake_case_id",
      "title": "任务块标题",
      "outcome": "完成后的具体产物",
      "p50_minutes": 60,
      "p90_minutes": 120,
      "cognitive_load": "high",
      "depends_on": [],
      "resources": ["https://example.com"],
      "acceptance_criteria": ["可以检查的验收标准"],
      "can_split": true
    }}
  ]
}}
"""


def build_json_repair_prompt(text: str) -> str:
    return f"""下面这段内容本应是 JSON，但解析失败了。请把它修复为合法 JSON。

要求：
1. 只输出 JSON，不要解释。
2. 保留 tasks 数组。
3. 不要添加 Markdown 代码块。
4. 所有字符串必须正确转义，不能有注释或尾随逗号。

待修复内容：
{text}
"""


def extract_json_object(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model response.")
    return json.loads(stripped[start : end + 1])


def fallback_decompose(goal: Goal) -> List[TaskBlock]:
    text = f"{goal.title} {goal.description}".lower()
    if "vggt" in text:
        return [
            TaskBlock(
                id="frame_problem",
                title="定位 VGGT 要解决的问题",
                outcome="写出 VGGT 的输入、输出、相比传统 SfM/COLMAP 的定位",
                p50_minutes=45,
                p90_minutes=90,
                cognitive_load="medium",
                resources=[
                    "https://github.com/facebookresearch/vggt",
                    "https://arxiv.org/abs/2503.11651",
                ],
                acceptance_criteria=[
                    "能用 3 句话解释 VGGT 是什么",
                    "能说清它和多视图三维重建/SfM 的关系",
                ],
            ),
            TaskBlock(
                id="read_architecture",
                title="理解 VGGT 架构和核心输出",
                outcome="整理一页架构笔记，覆盖相机参数、深度、点图、点轨迹",
                p50_minutes=75,
                p90_minutes=150,
                cognitive_load="high",
                depends_on=["frame_problem"],
                resources=["https://github.com/facebookresearch/vggt"],
                acceptance_criteria=[
                    "能画出从多张图像到 3D 输出的流程",
                    "能解释每类输出在工程里怎么用",
                ],
            ),
            TaskBlock(
                id="run_demo",
                title="跑通 VGGT demo 或最小推理脚本",
                outcome="本地获得一次可复现运行记录，包括环境、命令、输入、输出",
                p50_minutes=90,
                p90_minutes=240,
                cognitive_load="high",
                depends_on=["frame_problem"],
                resources=["https://github.com/facebookresearch/vggt"],
                acceptance_criteria=[
                    "记录安装步骤和报错解决",
                    "保存一次 demo 输出截图或日志",
                ],
            ),
            TaskBlock(
                id="engineering_notes",
                title="整理工程级操作笔记",
                outcome="形成一份可复用 runbook：环境、数据准备、推理、导出、常见坑",
                p50_minutes=60,
                p90_minutes=150,
                cognitive_load="medium",
                depends_on=["run_demo"],
                acceptance_criteria=[
                    "别人照着笔记能复现你的流程",
                    "明确哪些步骤还没验证",
                ],
            ),
            TaskBlock(
                id="mining_scenario_transfer",
                title="迁移到智能挖掘机场景",
                outcome="列出矿山/挖掘机场景三维重建的风险、适配点和面试表达",
                p50_minutes=60,
                p90_minutes=120,
                cognitive_load="high",
                depends_on=["read_architecture"],
                acceptance_criteria=[
                    "覆盖低纹理、粉尘、遮挡、动态物体、尺度和标定问题",
                    "能说明 VGGT 在该场景的优势和限制",
                ],
            ),
            TaskBlock(
                id="interview_drill",
                title="准备面试问答并自测",
                outcome="生成 10 个可能问题和自己的回答，补齐答不上来的点",
                p50_minutes=60,
                p90_minutes=120,
                cognitive_load="medium",
                depends_on=["engineering_notes", "mining_scenario_transfer"],
                acceptance_criteria=[
                    "每个回答都包含工程动作或具体例子",
                    "能自然回答为什么这个方法适合/不适合项目",
                ],
            ),
        ]

    return [
        TaskBlock(
            id="define_success",
            title="明确验收标准",
            outcome="把模糊目标改写成 3-5 条可检查标准",
            p50_minutes=25,
            p90_minutes=45,
            cognitive_load="medium",
            acceptance_criteria=["知道完成和未完成的边界"],
        ),
        TaskBlock(
            id="collect_sources",
            title="收集关键资料",
            outcome="列出需要阅读/运行/询问的核心资料",
            p50_minutes=40,
            p90_minutes=80,
            cognitive_load="medium",
            depends_on=["define_success"],
            acceptance_criteria=["资料不超过 5 个，且每个有用途"],
        ),
        TaskBlock(
            id="deep_work_block",
            title="完成核心理解或实现",
            outcome="产出一个可以演示或解释的核心成果",
            p50_minutes=90,
            p90_minutes=210,
            cognitive_load="high",
            depends_on=["collect_sources"],
            acceptance_criteria=["能向别人复述或展示核心成果"],
        ),
        TaskBlock(
            id="write_notes",
            title="写 Obsidian 理解笔记",
            outcome="沉淀一份后续可以修改的结构化笔记",
            p50_minutes=45,
            p90_minutes=90,
            cognitive_load="medium",
            depends_on=["deep_work_block"],
            acceptance_criteria=["笔记包含问题、理解、证据和下一步"],
        ),
        TaskBlock(
            id="self_test",
            title="自测和查漏补缺",
            outcome="用问题清单检验理解，标出剩余风险",
            p50_minutes=45,
            p90_minutes=90,
            cognitive_load="medium",
            depends_on=["write_notes"],
            acceptance_criteria=["至少答完 5 个检验问题"],
        ),
    ]
