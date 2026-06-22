from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


WorkflowEventName = Literal[
    "GoalSubmitted",
    "TasksDecomposed",
    "ScheduleOptionsGenerated",
    "UserOptionSelected",
    "ScheduleCommitted",
    "ReminderTriggered",
    "ResultCaptured",
    "RescheduleRequested",
]


@dataclass
class WorkflowEvent:
    name: WorkflowEventName
    payload: dict


WORKFLOW_STEPS = [
    "GoalSubmitted",
    "ClarifyGoal",
    "DecomposeTasks",
    "EstimateDurations",
    "FindCalendarSlots",
    "GenerateScheduleOptions",
    "WaitForUserChoice",
    "CommitSchedule",
    "ReminderTriggered",
    "CaptureResult",
    "RescheduleIfNeeded",
]


def describe_workflow() -> str:
    return " -> ".join(WORKFLOW_STEPS)
