import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from flow_starter.models import ScheduleOption, ScheduledSession
from flow_starter.pomofocus import (
    find_pomofocus_app,
    option_to_pomofocus_text,
    pomodoro_count,
)


class PomofocusTests(unittest.TestCase):
    def test_pomodoro_count_rounds_up(self) -> None:
        self.assertEqual(pomodoro_count(1), 1)
        self.assertEqual(pomodoro_count(25), 1)
        self.assertEqual(pomodoro_count(26), 2)
        self.assertEqual(pomodoro_count(90), 4)

    def test_option_text_uses_clean_task_titles(self) -> None:
        option = ScheduleOption(
            id="risk_first",
            label="Risk first",
            strategy="risk_first",
            sessions=[
                ScheduledSession(
                    task_id="task_1",
                    title="flow-starter 修正：超出截止：Read paper",
                    start=datetime(2026, 6, 22, 9, 0),
                    end=datetime(2026, 6, 22, 10, 0),
                    option_id="risk_first",
                    sequence=1,
                )
            ],
        )

        text = option_to_pomofocus_text(option)

        self.assertIn("Read paper (60 分钟 / 3 个番茄)", text)
        self.assertNotIn("flow-starter", text)
        self.assertNotIn("超出截止", text)

    def test_find_pomofocus_app_uses_configured_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            app = Path(tmpdir) / "Pomofocus.app"
            app.mkdir()

            self.assertEqual(find_pomofocus_app(str(app)), app)


if __name__ == "__main__":
    unittest.main()
