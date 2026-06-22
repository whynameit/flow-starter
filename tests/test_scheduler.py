import unittest
from datetime import datetime

from flow_starter.models import BusySlot, TaskBlock
from flow_starter.scheduler import SchedulePlanner


class SchedulerTests(unittest.TestCase):
    def test_scheduler_respects_busy_slots(self) -> None:
        tasks = [
            TaskBlock(
                id="t1",
                title="Task 1",
                outcome="Done",
                p50_minutes=30,
                p90_minutes=45,
            )
        ]
        busy = [
            BusySlot(
                title="Class",
                start=datetime(2026, 6, 19, 9, 0),
                end=datetime(2026, 6, 19, 10, 0),
            )
        ]
        planner = SchedulePlanner(
            working_day_start="09:00",
            working_day_end="12:00",
            risk_multiplier=1.0,
            buffer_before_deadline_minutes=0,
        )

        options = planner.generate_options(
            tasks,
            busy,
            start=datetime(2026, 6, 19, 9, 0),
            deadline=datetime(2026, 6, 19, 12, 0),
        )

        first_session = options[0].sessions[0]
        self.assertEqual(first_session.start, datetime(2026, 6, 19, 10, 0))
        self.assertEqual(first_session.end, datetime(2026, 6, 19, 10, 45))

    def test_scheduler_splits_large_tasks(self) -> None:
        tasks = [
            TaskBlock(
                id="t1",
                title="Large Task",
                outcome="Done",
                p50_minutes=120,
                p90_minutes=180,
            )
        ]
        planner = SchedulePlanner(
            working_day_start="09:00",
            working_day_end="14:00",
            max_session_minutes=90,
            risk_multiplier=1.0,
            buffer_before_deadline_minutes=0,
        )

        options = planner.generate_options(
            tasks,
            [],
            start=datetime(2026, 6, 19, 9, 0),
            deadline=datetime(2026, 6, 19, 14, 0),
        )

        self.assertEqual(len(options[0].sessions), 2)
        self.assertEqual(options[0].scheduled_minutes, 180)

    def test_scheduler_can_continue_after_deadline(self) -> None:
        tasks = [
            TaskBlock(
                id="t1",
                title="Task 1",
                outcome="Done",
                p50_minutes=60,
                p90_minutes=60,
            ),
            TaskBlock(
                id="t2",
                title="Task 2",
                outcome="Done",
                p50_minutes=60,
                p90_minutes=60,
            ),
        ]
        planner = SchedulePlanner(
            working_day_start="09:00",
            working_day_end="10:00",
            risk_multiplier=1.0,
            buffer_before_deadline_minutes=0,
            allow_overflow=True,
        )

        options = planner.generate_options(
            tasks,
            [],
            start=datetime(2026, 6, 19, 9, 0),
            deadline=datetime(2026, 6, 19, 10, 0),
        )

        self.assertEqual(len(options[0].sessions), 2)
        self.assertEqual(options[0].sessions[1].start, datetime(2026, 6, 20, 9, 0))
        self.assertIn("超出截止", options[0].sessions[1].title)
        self.assertTrue(options[0].warnings)

    def test_scheduler_supports_overnight_working_window(self) -> None:
        tasks = [
            TaskBlock(
                id="t1",
                title="Night Task",
                outcome="Done",
                p50_minutes=60,
                p90_minutes=60,
            )
        ]
        planner = SchedulePlanner(
            working_day_start="10:30",
            working_day_end="03:00",
            risk_multiplier=1.0,
            buffer_before_deadline_minutes=0,
        )

        options = planner.generate_options(
            tasks,
            [],
            start=datetime(2026, 6, 22, 8, 0),
            deadline=datetime(2026, 6, 23, 3, 0),
        )

        first_session = options[0].sessions[0]
        self.assertEqual(first_session.start, datetime(2026, 6, 22, 10, 30))
        self.assertEqual(first_session.end, datetime(2026, 6, 22, 11, 30))

    def test_scheduler_can_use_early_morning_part_of_overnight_window(self) -> None:
        tasks = [
            TaskBlock(
                id="t1",
                title="Early Task",
                outcome="Done",
                p50_minutes=60,
                p90_minutes=60,
            )
        ]
        planner = SchedulePlanner(
            working_day_start="10:30",
            working_day_end="03:00",
            risk_multiplier=1.0,
            buffer_before_deadline_minutes=0,
        )

        options = planner.generate_options(
            tasks,
            [],
            start=datetime(2026, 6, 23, 1, 0),
            deadline=datetime(2026, 6, 23, 3, 0),
        )

        first_session = options[0].sessions[0]
        self.assertEqual(first_session.start, datetime(2026, 6, 23, 1, 0))
        self.assertEqual(first_session.end, datetime(2026, 6, 23, 2, 0))


if __name__ == "__main__":
    unittest.main()
