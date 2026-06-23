from __future__ import annotations

import math
import os
import subprocess
from pathlib import Path
from typing import Iterable

from .calendar_export import display_title
from .models import ScheduleOption, ScheduledSession


DEFAULT_POMOFOCUS_APP = Path("/Users/rh/Applications/Chrome Apps.localized/Pomofocus.app")
DEFAULT_POMOFOCUS_TASKS = Path(".flow-starter/pomofocus-tasks.txt")
POMOFOCUS_URL = "https://pomofocus.io/app"


def option_to_pomofocus_text(option: ScheduleOption, pomodoro_minutes: int = 25) -> str:
    lines = [session_to_pomofocus_line(session, pomodoro_minutes=pomodoro_minutes) for session in option.sessions]
    return "\n".join(lines).rstrip() + "\n"


def session_to_pomofocus_line(session: ScheduledSession, pomodoro_minutes: int = 25) -> str:
    title = display_title(session.title)
    count = pomodoro_count(session.minutes, pomodoro_minutes=pomodoro_minutes)
    return f"{title} ({session.minutes} 分钟 / {count} 个番茄)"


def pomodoro_count(minutes: int, pomodoro_minutes: int = 25) -> int:
    return max(1, math.ceil(max(1, minutes) / pomodoro_minutes))


def write_pomofocus_tasks(option: ScheduleOption, path: Path = DEFAULT_POMOFOCUS_TASKS) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(option_to_pomofocus_text(option), encoding="utf-8")
    return path


def copy_to_clipboard(text: str) -> bool:
    try:
        result = subprocess.run(["pbcopy"], input=text, text=True, check=False, capture_output=True)
    except OSError:
        return False
    return result.returncode == 0


def find_pomofocus_app(configured_path: str = "") -> Path | None:
    candidates = list(candidate_app_paths(configured_path))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def candidate_app_paths(configured_path: str = "") -> Iterable[Path]:
    configured = configured_path or os.environ.get("FLOW_STARTER_POMOFOCUS_APP") or os.environ.get("POMOFOCUS_APP") or ""
    if configured:
        yield from app_path_variants(Path(configured).expanduser())

    home = Path.home()
    yield DEFAULT_POMOFOCUS_APP
    yield home / "Applications" / "Chrome Apps.localized" / "Pomofocus.app"
    yield home / "Applications" / "Chrome Apps.localized" / "pomofocus.app"
    yield Path("/Applications/Pomofocus.app")
    yield Path("/Applications/pomofocus.app")


def app_path_variants(path: Path) -> Iterable[Path]:
    yield path
    if path.suffix != ".app":
        yield Path(f"{path}.app")
        if path.name.lower() == "pomofocus":
            yield path.with_name("Pomofocus.app")


def open_pomofocus(configured_path: str = "") -> str:
    app = find_pomofocus_app(configured_path)
    target = str(app) if app else POMOFOCUS_URL
    subprocess.run(["open", target], check=False)
    return target
