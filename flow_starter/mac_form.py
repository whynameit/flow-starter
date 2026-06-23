from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

from .models import parse_dt


FIELDS = ["目标", "补充说明", "开始时间", "截止时间", "排程策略", "使用Claude", "完成后打开Claude"]
FIELD_RE = re.compile(r"^(目标|补充说明|开始时间|截止时间|排程策略|使用Claude|完成后打开Claude)\s*:\s*(.*)$")


class FormError(ValueError):
    pass


def render_form(now: datetime | None = None) -> str:
    value = now or datetime.now()
    start = value.replace(second=0, microsecond=0).strftime("%Y-%m-%d %H:%M")
    deadline = (value + timedelta(days=2)).replace(hour=22, minute=0, second=0, microsecond=0)
    return f"""# flow-starter 启动表单
# 填完后按 Command-S 保存，再回到弹窗点“保存并继续”。
# 排程策略可填：risk_first、core_order、quick_wins。
# 使用Claude / 完成后打开Claude 可填：是 或 否。

目标:

补充说明:

开始时间: {start}
截止时间: {deadline.strftime("%Y-%m-%d %H:%M")}
排程策略: risk_first
使用Claude: 是
完成后打开Claude: 是
"""


def parse_form(text: str) -> Dict[str, str]:
    values: Dict[str, List[str]] = {field: [] for field in FIELDS}
    current = ""
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        match = FIELD_RE.match(line)
        if match:
            current = match.group(1)
            values[current].append(match.group(2))
            continue
        if line.startswith("#"):
            continue
        if current:
            values[current].append(line)

    return {field: clean_value("\n".join(lines)) for field, lines in values.items()}


def clean_value(value: str) -> str:
    lines = value.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines).strip()


def bool_value(value: str, default: bool = True) -> bool:
    text = value.strip().lower()
    if not text:
        return default
    return text.startswith(("是", "使用", "打开", "yes", "y", "true", "1"))


def normalize_option(value: str) -> str:
    text = value.strip().lower()
    if not text:
        return "risk_first"
    if "core" in text or "核心" in text:
        return "core_order"
    if "quick" in text or "启动" in text or "小任务" in text:
        return "quick_wins"
    if "risk" in text or "风险" in text:
        return "risk_first"
    return text


def build_start_argv(values: Dict[str, str]) -> List[str]:
    goal = values.get("目标", "").strip()
    description = values.get("补充说明", "").strip()
    start = values.get("开始时间", "").strip()
    deadline = values.get("截止时间", "").strip()
    option = normalize_option(values.get("排程策略", "risk_first"))

    if not goal:
        raise FormError("还没有填写目标。")
    try:
        parse_dt(start)
        parse_dt(deadline)
    except (TypeError, ValueError) as exc:
        raise FormError("时间格式不对，请用 YYYY-MM-DD HH:MM。") from exc
    if option not in {"risk_first", "core_order", "quick_wins"}:
        raise FormError("排程策略只能是 risk_first、core_order 或 quick_wins。")

    argv = ["start", "--goal", goal, "--deadline", deadline, "--start", start, "--option", option]
    if description:
        argv.extend(["--description", description])
    if not bool_value(values.get("使用Claude", "是")):
        argv.append("--no-claude")
    if bool_value(values.get("完成后打开Claude", "是")):
        argv.append("--open-claude")
    return argv


def summarize_error(text: str) -> str:
    lowered = text.lower()
    if "anthropic_api_key is invalid" in lowered or "authentication failed" in lowered:
        return "Claude API key 无效，请检查 .env。"
    if "credit balance is too low" in lowered or "no available credits" in lowered:
        return "Anthropic API 余额不足。"
    if "could not reach claude api" in lowered:
        return "连不上 Claude API，请检查网络或代理。"
    if "missing anthropic_api_key" in lowered:
        return "缺少 ANTHROPIC_API_KEY。"
    if "missing claude_model" in lowered:
        return "缺少 CLAUDE_MODEL。"
    if "time data" in lowered or "unsupported datetime format" in lowered:
        return "时间格式不对，请用 YYYY-MM-DD HH:MM。"
    if "filenotfounderror" in lowered or "no such file" in lowered:
        return "找不到需要的文件，请检查课表或目录路径。"
    if "option not found" in lowered:
        return "排程策略没有找到，请换成 risk_first、core_order 或 quick_wins。"
    if "无法删除旧 flow-starter 日历块" in lowered or "calendar" in lowered and "permission" in lowered:
        return "无法删除旧日历块。请给 flow-starter/Terminal 访问 Calendar 的权限，或修正时选择保留旧块。"
    if "apple 事件 javascript" in lowered or "apple event" in lowered and "javascript" in lowered:
        return "Chrome 还没允许自动创建 Pomofocus 任务。请在 Chrome 菜单“查看 > 开发者 > 允许 Apple 事件中的 JavaScript”打开一次。"

    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped and not stripped.startswith(("Traceback", "File ")):
            return stripped[:160]
    return "运行失败，请打开日志查看完整信息。"


def run_form(path: Path) -> int:
    from .cli import main as cli_main

    try:
        values = parse_form(path.read_text(encoding="utf-8"))
        cli_main(build_start_argv(values))
        return 0
    except FormError as exc:
        print(str(exc))
        return 2
    except SystemExit as exc:
        if exc.code in (None, 0):
            return 0
        if isinstance(exc.code, str):
            print(exc.code)
            return 1
        return int(exc.code)
    except Exception as exc:
        print(str(exc) or exc.__class__.__name__)
        return 1


def main(argv: List[str] | None = None) -> None:
    args = argv or sys.argv[1:]
    if len(args) < 2 or args[0] not in {"write", "run", "summarize-error"}:
        raise SystemExit("Usage: python -m flow_starter.mac_form write|run|summarize-error PATH")

    command = args[0]
    path = Path(args[1])
    if command == "write":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_form(), encoding="utf-8")
        return
    if command == "run":
        raise SystemExit(run_form(path))
    if command == "summarize-error":
        print(summarize_error(path.read_text(encoding="utf-8", errors="replace")))


if __name__ == "__main__":
    main()
