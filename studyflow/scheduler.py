from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Dict, Iterable, List, Sequence, Tuple

from .models import BusySlot, ScheduleOption, ScheduledSession, TaskBlock

Interval = Tuple[datetime, datetime]


class SchedulePlanner:
    def __init__(
        self,
        working_day_start: str = "08:30",
        working_day_end: str = "23:00",
        break_minutes: int = 10,
        max_session_minutes: int = 90,
        min_session_minutes: int = 25,
        risk_multiplier: float = 2.0,
        buffer_before_deadline_minutes: int = 60,
        allow_overflow: bool = False,
        overflow_days: int = 14,
    ) -> None:
        self.working_day_start = parse_clock(working_day_start)
        self.working_day_end = parse_clock(working_day_end)
        self.break_minutes = break_minutes
        self.max_session_minutes = max_session_minutes
        self.min_session_minutes = min_session_minutes
        self.risk_multiplier = risk_multiplier
        self.buffer_before_deadline_minutes = buffer_before_deadline_minutes
        self.allow_overflow = allow_overflow
        self.overflow_days = overflow_days

    def generate_options(
        self,
        tasks: Sequence[TaskBlock],
        busy_slots: Sequence[BusySlot],
        start: datetime,
        deadline: datetime,
    ) -> List[ScheduleOption]:
        schedule_deadline = deadline - timedelta(minutes=self.buffer_before_deadline_minutes)
        free = compute_free_intervals(
            start=start,
            deadline=schedule_deadline,
            busy_slots=busy_slots,
            day_start=self.working_day_start,
            day_end=self.working_day_end,
        )
        if self.allow_overflow:
            overflow_start = max(start, schedule_deadline)
            overflow_end = deadline + timedelta(days=self.overflow_days)
            free.extend(
                compute_free_intervals(
                    start=overflow_start,
                    deadline=overflow_end,
                    busy_slots=busy_slots,
                    day_start=self.working_day_start,
                    day_end=self.working_day_end,
                )
            )
        options = [
            self._schedule_order(
                option_id="core_order",
                label="核心路径：按依赖和原始顺序推进",
                strategy="dependency_first",
                tasks=self._dependency_order(tasks, list(tasks)),
                free_intervals=free,
                deadline=deadline,
            ),
            self._schedule_order(
                option_id="risk_first",
                label="低风险：先处理最可能超时的任务",
                strategy="risk_first",
                tasks=self._dependency_order(
                    tasks,
                    sorted(tasks, key=lambda task: task.p90_minutes - task.p50_minutes, reverse=True),
                ),
                free_intervals=free,
                deadline=deadline,
            ),
            self._schedule_order(
                option_id="quick_wins",
                label="启动友好：先完成较小任务建立动量",
                strategy="quick_wins",
                tasks=self._dependency_order(
                    tasks,
                    sorted(tasks, key=lambda task: task.planned_minutes(self.risk_multiplier)),
                ),
                free_intervals=free,
                deadline=deadline,
            ),
        ]
        return options

    def _dependency_order(self, tasks: Sequence[TaskBlock], ranked_tasks: Sequence[TaskBlock]) -> List[TaskBlock]:
        by_id: Dict[str, TaskBlock] = {task.id: task for task in tasks}
        ranked_ids = [task.id for task in ranked_tasks]
        remaining = set(by_id)
        ordered: List[TaskBlock] = []

        while remaining:
            progressed = False
            for task_id in ranked_ids:
                if task_id not in remaining:
                    continue
                task = by_id[task_id]
                deps = [dep for dep in task.depends_on if dep in by_id]
                if all(dep not in remaining for dep in deps):
                    ordered.append(task)
                    remaining.remove(task_id)
                    progressed = True
            if not progressed:
                task_id = ranked_ids[0] if ranked_ids else next(iter(remaining))
                ordered.append(by_id[task_id])
                remaining.remove(task_id)
                ranked_ids = [item for item in ranked_ids if item != task_id]
        return ordered

    def _schedule_order(
        self,
        option_id: str,
        label: str,
        strategy: str,
        tasks: Sequence[TaskBlock],
        free_intervals: Sequence[Interval],
        deadline: datetime,
    ) -> ScheduleOption:
        intervals = [[start, end] for start, end in free_intervals]
        sessions: List[ScheduledSession] = []
        warnings: List[str] = []
        sequence = 1

        for task in tasks:
            remaining = task.planned_minutes(self.risk_multiplier)
            part = 1
            while remaining > 0:
                requested = remaining if not task.can_split else min(remaining, self.max_session_minutes)
                placement = self._find_interval(intervals, requested, task.can_split)
                if placement is None:
                    warnings.append(
                        f"未能完整安排：{task.title} 还剩 {remaining} 分钟。请降低范围、增加时间或提高截止风险。"
                    )
                    break

                interval_index, session_start, session_end = placement
                title = task.title if part == 1 and remaining <= requested else f"{task.title} ({part})"
                if session_start >= deadline:
                    title = f"超出截止: {title}"
                sessions.append(
                    ScheduledSession(
                        task_id=task.id,
                        title=title,
                        start=session_start,
                        end=session_end,
                        option_id=option_id,
                        sequence=sequence,
                        resources=task.resources,
                        prompt=build_session_prompt(task),
                    )
                )
                sequence += 1
                part += 1
                used_minutes = int((session_end - session_start).total_seconds() // 60)
                remaining -= used_minutes
                intervals[interval_index][0] = session_end + timedelta(minutes=self.break_minutes)

        if any(session.start >= deadline for session in sessions):
            warnings.insert(0, "时间不够：部分任务已排到截止时间之后，日历中用“超出截止”标出。")
        return ScheduleOption(id=option_id, label=label, strategy=strategy, sessions=sessions, warnings=warnings)

    def _find_interval(
        self,
        intervals: List[List[datetime]],
        requested_minutes: int,
        can_split: bool,
    ) -> Tuple[int, datetime, datetime] | None:
        for index, (start, end) in enumerate(intervals):
            available = int((end - start).total_seconds() // 60)
            if available < self.min_session_minutes:
                continue
            if available >= requested_minutes:
                return index, start, start + timedelta(minutes=requested_minutes)
            if can_split and available >= self.min_session_minutes:
                session_minutes = min(available, self.max_session_minutes)
                return index, start, start + timedelta(minutes=session_minutes)
        return None


def parse_clock(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(hour=int(hour), minute=int(minute))


def compute_free_intervals(
    start: datetime,
    deadline: datetime,
    busy_slots: Sequence[BusySlot],
    day_start: time,
    day_end: time,
) -> List[Interval]:
    intervals = working_intervals(start, deadline, day_start, day_end)
    busy_intervals = sorted(
        [(slot.start, slot.end) for slot in busy_slots if slot.end > start and slot.start < deadline],
        key=lambda item: item[0],
    )
    for busy_start, busy_end in busy_intervals:
        intervals = subtract_interval(intervals, busy_start, busy_end)
    return [(left, right) for left, right in intervals if right > left]


def working_intervals(start: datetime, deadline: datetime, day_start: time, day_end: time) -> List[Interval]:
    intervals: List[Interval] = []
    cursor = start.date()
    if day_end <= day_start:
        cursor = cursor - timedelta(days=1)
    while datetime.combine(cursor, time.min) <= deadline:
        left = datetime.combine(cursor, day_start)
        right = datetime.combine(cursor, day_end)
        if day_end <= day_start:
            right = right + timedelta(days=1)
        left = max(left, start)
        right = min(right, deadline)
        if right > left:
            intervals.append((left, right))
        cursor = cursor + timedelta(days=1)
    return intervals


def subtract_interval(intervals: Sequence[Interval], busy_start: datetime, busy_end: datetime) -> List[Interval]:
    result: List[Interval] = []
    for start, end in intervals:
        if busy_end <= start or busy_start >= end:
            result.append((start, end))
            continue
        if busy_start > start:
            result.append((start, min(busy_start, end)))
        if busy_end < end:
            result.append((max(busy_end, start), end))
    return result


def build_session_prompt(task: TaskBlock) -> str:
    criteria = "\n".join(f"- {item}" for item in task.acceptance_criteria) or "- 完成任务块产物"
    return f"""现在只做这个任务块：{task.title}

目标产物：{task.outcome}

验收标准：
{criteria}

请先用 3 分钟写下：
1. 我现在已经知道什么？
2. 我这一个时间块最小可交付物是什么？
3. 如果卡住，下一步问 Claude/ChatGPT 的具体问题是什么？
"""
