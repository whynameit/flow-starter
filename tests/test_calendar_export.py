import unittest
from datetime import datetime

from flow_starter.calendar_export import option_to_ics
from flow_starter.models import ScheduleOption, ScheduledSession


class CalendarExportTests(unittest.TestCase):
    def test_batch_label_marks_revision_events(self) -> None:
        option = ScheduleOption(
            id="risk_first",
            label="Risk first",
            strategy="risk_first",
            sessions=[
                ScheduledSession(
                    task_id="task_1",
                    title="Read paper",
                    start=datetime(2026, 6, 22, 9, 0),
                    end=datetime(2026, 6, 22, 10, 0),
                    option_id="risk_first",
                    sequence=1,
                )
            ],
        )

        text = option_to_ics(option, batch_label="修正 20260622-2200")

        self.assertIn("SUMMARY:flow-starter 修正：Read paper", text)
        self.assertIn("UID:20260622-2200-risk_first-1-task_1@flow-starter.local", text)

    def test_revision_summary_uses_short_overdue_title(self) -> None:
        option = ScheduleOption(
            id="risk_first",
            label="Risk first",
            strategy="risk_first",
            sessions=[
                ScheduledSession(
                    task_id="task_1",
                    title="超出截止: Read paper",
                    start=datetime(2026, 6, 22, 9, 0),
                    end=datetime(2026, 6, 22, 10, 0),
                    option_id="risk_first",
                    sequence=1,
                )
            ],
        )

        text = option_to_ics(option, batch_label="修正 20260622-223641")

        self.assertIn("SUMMARY:flow-starter 修正：超出截止：Read paper", text)
        self.assertNotIn("flow-starter 修正 20260622-223641", text)


if __name__ == "__main__":
    unittest.main()
