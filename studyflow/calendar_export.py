from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Iterable

from .models import ScheduleOption, ScheduledSession


def write_option_ics(option: ScheduleOption, path: Path, batch_label: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = option_to_ics(option, batch_label=batch_label)
    path.write_text(content, encoding="utf-8")
    return path


def option_to_ics(option: ScheduleOption, batch_label: str = "") -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//StudyFlow//Learning Workflow//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for session in option.sessions:
        lines.extend(session_to_event(session, batch_label=batch_label))
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def session_to_event(session: ScheduledSession, batch_label: str = "") -> Iterable[str]:
    uid_parts = [session.option_id, str(session.sequence), session.task_id]
    if batch_label:
        uid_parts.insert(0, safe_uid_part(batch_label))
    uid = f"{'-'.join(uid_parts)}@studyflow.local"
    description = escape_ics_text(session.prompt)
    prefix = display_prefix(batch_label)
    return [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{format_ics_datetime(datetime.utcnow())}",
        f"DTSTART:{format_ics_datetime(session.start)}",
        f"DTEND:{format_ics_datetime(session.end)}",
        f"SUMMARY:{escape_ics_text(prefix + '：' + display_title(session.title))}",
        f"DESCRIPTION:{description}",
        "BEGIN:VALARM",
        "TRIGGER:PT0M",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{escape_ics_text('开始：' + session.title)}",
        "END:VALARM",
        "END:VEVENT",
    ]


def format_ics_datetime(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S")


def safe_uid_part(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip())
    return text.strip("-") or "revision"


def display_prefix(batch_label: str = "") -> str:
    if batch_label.strip().startswith("修正"):
        return "StudyFlow 修正"
    return "StudyFlow"


def display_title(value: str) -> str:
    return value.replace("超出截止: ", "超出截止：")


def escape_ics_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )
