from __future__ import annotations

import subprocess
from typing import List


def delete_future_flow_starter_events(prefix: str = "flow-starter", lookahead_days: int = 21) -> int:
    result = subprocess.run(
        build_delete_events_command(prefix=prefix, lookahead_days=lookahead_days),
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(
            "无法删除旧 flow-starter 日历块。请检查 Calendar 权限，或在修正时选择保留旧块。"
            + (f" 详情：{detail}" if detail else "")
        )

    text = result.stdout.strip()
    try:
        return int(text)
    except ValueError:
        return 0


def build_delete_events_command(prefix: str, lookahead_days: int) -> List[str]:
    return [
        "/usr/bin/osascript",
        "-e",
        "on run argv",
        "-e",
        "set prefixText to item 1 of argv",
        "-e",
        "set lookaheadDays to (item 2 of argv) as integer",
        "-e",
        "set nowDate to current date",
        "-e",
        "set endDate to nowDate + (lookaheadDays * days)",
        "-e",
        "set deletedCount to 0",
        "-e",
        'tell application "Calendar"',
        "-e",
        "repeat with cal in calendars",
        "-e",
        "try",
        "-e",
        "set matchedEvents to every event of cal whose start date is greater than or equal to nowDate and start date is less than or equal to endDate",
        "-e",
        "repeat with eventItem in matchedEvents",
        "-e",
        "try",
        "-e",
        "set eventRef to contents of eventItem",
        "-e",
        "set eventSummary to summary of eventRef",
        "-e",
        "if eventSummary starts with prefixText then",
        "-e",
        "delete eventRef",
        "-e",
        "set deletedCount to deletedCount + 1",
        "-e",
        "end if",
        "-e",
        "end try",
        "-e",
        "end repeat",
        "-e",
        "end try",
        "-e",
        "end repeat",
        "-e",
        "end tell",
        "-e",
        "return deletedCount",
        "-e",
        "end run",
        prefix,
        str(max(1, lookahead_days)),
    ]
