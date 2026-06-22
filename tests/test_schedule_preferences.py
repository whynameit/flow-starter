import unittest

from flow_starter.schedule_preferences import extract_schedule_preferences, merge_schedule_preferences


class SchedulePreferenceTests(unittest.TestCase):
    def test_extracts_not_before_and_overnight_end(self) -> None:
        preferences = extract_schedule_preferences("可以在凌晨3点前安排任务，不要在10点半前安排任务")

        self.assertEqual(preferences["working_day_start"], "10:30")
        self.assertEqual(preferences["working_day_end"], "03:00")

    def test_negative_start_phrase_is_not_taken_as_end(self) -> None:
        preferences = extract_schedule_preferences("不要在10:30前安排任务，可以到03:00前都可以")

        self.assertEqual(preferences["working_day_start"], "10:30")
        self.assertEqual(preferences["working_day_end"], "03:00")

    def test_later_preferences_override_earlier_preferences(self) -> None:
        preferences = merge_schedule_preferences(
            {"working_day_start": "08:30", "working_day_end": "23:00"},
            {"working_day_start": "10:30"},
        )

        self.assertEqual(preferences["working_day_start"], "10:30")
        self.assertEqual(preferences["working_day_end"], "23:00")


if __name__ == "__main__":
    unittest.main()
