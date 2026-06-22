from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from math import ceil
from typing import Any, Dict, Iterable, List, Optional


DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
)


def parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise TypeError(f"Expected datetime or str, got {type(value)!r}")

    text = value.strip()
    for fmt in DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    raise ValueError(f"Unsupported datetime format: {value!r}")


def format_dt(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M")


def ceil_to_five(minutes: float) -> int:
    return int(ceil(minutes / 5.0) * 5)


@dataclass
class Goal:
    title: str
    deadline: datetime
    description: str = ""
    success_criteria: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class TaskBlock:
    id: str
    title: str
    outcome: str
    p50_minutes: int
    p90_minutes: int
    cognitive_load: str = "medium"
    depends_on: List[str] = field(default_factory=list)
    resources: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    can_split: bool = True
    project: str = ""

    def planned_minutes(self, risk_multiplier: float = 2.0) -> int:
        return max(25, ceil_to_five(max(self.p90_minutes, self.p50_minutes * risk_multiplier)))


@dataclass
class BusySlot:
    title: str
    start: datetime
    end: datetime
    source: str = "manual"

    def overlaps(self, start: datetime, end: datetime) -> bool:
        return self.start < end and start < self.end


@dataclass
class ScheduledSession:
    task_id: str
    title: str
    start: datetime
    end: datetime
    option_id: str
    sequence: int
    resources: List[str] = field(default_factory=list)
    prompt: str = ""

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


@dataclass
class ScheduleOption:
    id: str
    label: str
    strategy: str
    sessions: List[ScheduledSession]
    warnings: List[str] = field(default_factory=list)

    @property
    def scheduled_minutes(self) -> int:
        return sum(session.minutes for session in self.sessions)


def to_jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return format_dt(value)
    if is_dataclass(value):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    return value


def tasks_from_dicts(items: Iterable[Dict[str, Any]]) -> List[TaskBlock]:
    tasks: List[TaskBlock] = []
    for index, item in enumerate(items, start=1):
        task_id = str(item.get("id") or f"task_{index}")
        tasks.append(
            TaskBlock(
                id=task_id,
                title=str(item.get("title") or f"Task {index}"),
                outcome=str(item.get("outcome") or ""),
                p50_minutes=int(item.get("p50_minutes") or item.get("estimate_minutes") or 45),
                p90_minutes=int(item.get("p90_minutes") or item.get("p50_minutes") or 90),
                cognitive_load=str(item.get("cognitive_load") or "medium"),
                depends_on=list(item.get("depends_on") or []),
                resources=list(item.get("resources") or []),
                acceptance_criteria=list(item.get("acceptance_criteria") or []),
                can_split=bool(item.get("can_split", True)),
                project=str(item.get("project") or ""),
            )
        )
    return tasks


def busy_slots_from_dicts(items: Iterable[Dict[str, Any]]) -> List[BusySlot]:
    slots: List[BusySlot] = []
    for item in items:
        slots.append(
            BusySlot(
                title=str(item.get("title") or "Busy"),
                start=parse_dt(item["start"]),
                end=parse_dt(item["end"]),
                source=str(item.get("source") or "manual"),
            )
        )
    return slots
