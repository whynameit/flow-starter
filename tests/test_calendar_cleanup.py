import unittest

from studyflow.calendar_cleanup import build_delete_events_command


class CalendarCleanupTests(unittest.TestCase):
    def test_delete_command_targets_future_studyflow_events(self) -> None:
        command = build_delete_events_command(prefix="StudyFlow", lookahead_days=21)
        joined = "\n".join(command)

        self.assertEqual(command[0], "/usr/bin/osascript")
        self.assertIn("eventSummary starts with prefixText", joined)
        self.assertIn("start date is greater than or equal to nowDate", joined)
        self.assertEqual(command[-2], "StudyFlow")
        self.assertEqual(command[-1], "21")


if __name__ == "__main__":
    unittest.main()
