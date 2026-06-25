import csv
import contextlib
import io
import json
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

from flow_starter.focus_runner import main as focus_main


class FocusRunnerTests(unittest.TestCase):
    def write_plan(self, path: Path, sessions: list[dict[str, object]]) -> None:
        path.write_text(
            json.dumps(
                {
                    "selected_option": "risk_first",
                    "goal": {"title": "Goal"},
                    "options": [
                        {
                            "id": "risk_first",
                            "label": "Risk first",
                            "strategy": "risk_first",
                            "sessions": sessions,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def test_focus_runner_records_actual_time_and_advances(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "plan.json"
            state = root / "state.json"
            history = root / "history.csv"
            self.write_plan(
                plan,
                [
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

    def test_focus_runner_shifts_remaining_sessions_after_actual_finish(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "plan.json"
            state = root / "state.json"
            history = root / "history.csv"
            self.write_plan(
                plan,
                [
                    {
                        "task_id": "task_1",
                        "title": "Task 1",
                        "start": "2026-06-22 09:00",
                        "end": "2026-06-22 09:30",
                        "option_id": "risk_first",
                        "sequence": 1,
                        "resources": [],
                        "prompt": "Do it",
                    },
                    {
                        "task_id": "task_2",
                        "title": "Task 2",
                        "start": "2026-06-22 09:40",
                        "end": "2026-06-22 10:10",
                        "option_id": "risk_first",
                        "sequence": 2,
                        "resources": [],
                        "prompt": "Do next",
                    },
                ],
            )

            completed_at = datetime(2026, 6, 22, 9, 50).timestamp()
            started_at = datetime(2026, 6, 22, 9, 0).timestamp()

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
                        str(started_at),
                        "--completed-at",
                        str(completed_at),
                        "--adjust-remaining",
                    ]
                )

            saved = json.loads(state.read_text(encoding="utf-8"))
            next_session = saved["sessions"][1]
            self.assertEqual(next_session["original_start"], "2026-06-22 09:40")
            self.assertEqual(next_session["start"], "2026-06-22 09:50")
            self.assertEqual(next_session["end"], "2026-06-22 10:20")
            self.assertEqual(saved["completed"][0]["deviation_minutes"], 20)

    def test_resume_only_keeps_existing_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "plan.json"
            state = root / "state.json"
            self.write_plan(
                plan,
                [
                    {
                        "task_id": "task_1",
                        "title": "Task 1",
                        "start": "2026-06-22 09:00",
                        "end": "2026-06-22 09:30",
                        "option_id": "risk_first",
                        "sequence": 1,
                        "resources": [],
                        "prompt": "Do it",
                    },
                    {
                        "task_id": "task_2",
                        "title": "Task 2",
                        "start": "2026-06-22 09:30",
                        "end": "2026-06-22 10:00",
                        "option_id": "risk_first",
                        "sequence": 2,
                        "resources": [],
                        "prompt": "Do next",
                    },
                ],
            )

            with contextlib.redirect_stdout(io.StringIO()):
                focus_main(["init", "--plan", str(plan), "--state", str(state)])

            saved = json.loads(state.read_text(encoding="utf-8"))
            saved["current_index"] = 1
            state.write_text(json.dumps(saved), encoding="utf-8")

            with contextlib.redirect_stdout(io.StringIO()):
                focus_main(["init", "--plan", str(plan), "--state", str(state), "--resume-only"])

            resumed = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(resumed["current_index"], 1)
            self.assertEqual(resumed["sessions"][1]["task_id"], "task_2")

    def test_resume_only_without_current_task_exits(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state = Path(tmpdir) / "state.json"
            with self.assertRaises(SystemExit) as caught:
                focus_main(["init", "--state", str(state), "--resume-only"])
            self.assertNotEqual(caught.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
