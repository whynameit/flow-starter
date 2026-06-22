from __future__ import annotations

import re
from typing import Dict


SchedulePreferences = Dict[str, str]


def extract_schedule_preferences(text: str) -> SchedulePreferences:
    preferences: SchedulePreferences = {}
    start = extract_not_before(text)
    end = extract_can_work_until(text)
    if start:
        preferences["working_day_start"] = start
    if end:
        preferences["working_day_end"] = end
    return preferences


def merge_schedule_preferences(*items: SchedulePreferences | None) -> SchedulePreferences:
    merged: SchedulePreferences = {}
    for item in items:
        if not item:
            continue
        for key in ("working_day_start", "working_day_end"):
            value = item.get(key, "").strip()
            if value:
                merged[key] = value
    return merged


def extract_not_before(text: str) -> str:
    patterns = [
        r"(?:不要|别|不想|不)\s*(?:在)?\s*(?P<time>[^，。,.\n]{1,12}?)(?:之前|前)\s*(?:安排|排|开始|做)",
        r"(?P<time>[^，。,.\n]{1,12}?)(?:之前|前)\s*(?:不要|别|不)\s*(?:安排|排|开始|做)",
    ]
    return first_time_match(text, patterns, default_period="")


def extract_can_work_until(text: str) -> str:
    patterns = [
        r"(?:可以|能|允许|接受|愿意)?\s*(?:安排|排|做|工作|学习)?\s*(?:到|至|直到)?\s*(?P<time>凌晨[^，。,.\n]{1,8}|早上[^，。,.\n]{1,8}|上午[^，。,.\n]{1,8}|下午[^，。,.\n]{1,8}|晚上[^，。,.\n]{1,8}|[0-9零一二两三四五六七八九十]{1,3}(?:[:：点时][0-9零一二两三四五六七八九十半]{0,3})?)\s*(?:之前|前|以前|前都可以)",
        r"(?:可以|能|允许|接受|愿意)\s*(?:安排|排|做|工作|学习)?\s*(?:到|至|直到)\s*(?P<time>[^，。,.\n]{1,12})",
    ]
    return first_time_match(text, patterns, default_period="", skip_negative=True)


def first_time_match(text: str, patterns: list[str], default_period: str, skip_negative: bool = False) -> str:
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            context = text[max(0, match.start() - 8) : match.end()]
            if skip_negative and re.search(r"(不要|别|不想)", context):
                continue
            value = parse_time_phrase(match.group("time"), default_period=default_period)
            if value:
                return value
    return ""


def parse_time_phrase(value: str, default_period: str = "") -> str:
    text = clean_time_phrase(value)
    if not text:
        return ""

    period = default_period
    for candidate in ("凌晨", "早上", "上午", "中午", "下午", "晚上"):
        if candidate in text:
            period = candidate
            text = text.replace(candidate, "")
            break

    hour = minute = None
    colon = re.search(r"(?P<hour>\d{1,2})\s*[:：]\s*(?P<minute>\d{1,2})", text)
    if colon:
        hour = int(colon.group("hour"))
        minute = int(colon.group("minute"))
    else:
        half = "半" in text
        compact = re.search(r"(?P<hour>[0-9零一二两三四五六七八九十]{1,3})\s*(?:点|時|时)?\s*(?P<minute>[0-9零一二两三四五六七八九十]{1,3})?", text)
        if not compact:
            return ""
        hour = parse_number(compact.group("hour"))
        minute_text = compact.group("minute") or ""
        minute = 30 if half else parse_number(minute_text, default=0)

    if hour is None or minute is None:
        return ""
    if period in {"下午", "晚上"} and 1 <= hour <= 11:
        hour += 12
    if period in {"凌晨", "早上", "上午"} and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return ""
    return f"{hour:02d}:{minute:02d}"


def clean_time_phrase(value: str) -> str:
    text = value.strip()
    text = re.sub(r"(?:可以|能|允许|接受|愿意|安排|排|做|工作|学习|任务|时间|在|到|至|直到)", "", text)
    text = text.replace("鐘", "点").replace("钟", "点")
    return text.strip()


def parse_number(value: str, default: int | None = None) -> int | None:
    if not value:
        return default
    if value.isdigit():
        return int(value)
    digits = {
        "零": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    if value == "十":
        return 10
    if value.startswith("十"):
        suffix = value[1:]
        return 10 + digits.get(suffix, 0)
    if "十" in value:
        prefix, suffix = value.split("十", 1)
        return digits.get(prefix, 0) * 10 + digits.get(suffix, 0)
    if value in digits:
        return digits[value]
    return default
