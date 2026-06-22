import csv
import contextlib
import io
import json
import tempfile
import time
import unittest
from pathlib import Path

from studyflow.focus_runner import main as focus_main


class FocusRunnerTests(unittest.TestCase):
    def test_focus_runner_records_actual_time_and_advances(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "plan.json"
            state = root / "state.json"
            history = root / "history.csv"
            plan.write_text(
                json.dumps(
                    {
                        "selected_option": "risk_first",
                        "goal": {"title": "Goal"},
                        "options": [
                            {
                                "id": "risk_first",
                                "label": "Risk first",
                                "strategy": "risk_first",
                                "sessions": [
                                    {
                                        "task_id": "task_1",
                                        "title": "Task 1",
                                        "start": "2026-06-22 09:00",
                                        "end": "2026-06-22 09:30",
                                        "option_id": "risk_first",
                                        "sequence": 1,
                                        "resources": [],
                                        "prompt": "Do it",
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with contextlib.redirect_stdout(io.StringIO()):
                focus_main(["init", "--plan", str(plan), "--state", str(state)])
                focus_main(
                    [
                        "complete",
                        "--state",
                        str(state),
                        "--history",
                        str(history),
                        "--started-at",
                        str(time.time() - 60),
                        "--note",
                        "done",
                    ]
                )

            saved = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(saved["current_index"], 1)
            self.assertEqual(saved["completed"][0]["task_id"], "task_1")
            with history.open("r", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["task_id"], "task_1")
            self.assertGreaterEqual(int(rows[0]["actual_minutes"]), 1)


if __name__ == "__main__":
    unittest.main()
