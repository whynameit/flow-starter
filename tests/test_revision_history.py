import unittest

from flow_starter.cli import revision_history_from_payload


class RevisionHistoryTests(unittest.TestCase):
    def test_reads_new_revision_history(self) -> None:
        payload = {
            "revision_history": [
                {"changes": "first"},
                {"changes": "second"},
            ]
        }

        history = revision_history_from_payload(payload)

        self.assertEqual([item["changes"] for item in history], ["first", "second"])

    def test_wraps_legacy_single_revision(self) -> None:
        payload = {"revision": {"changes": "legacy"}}

        history = revision_history_from_payload(payload)

        self.assertEqual(history, [{"changes": "legacy"}])

    def test_ignores_invalid_items(self) -> None:
        payload = {"revision_history": [{"changes": "ok"}, "bad"]}

        history = revision_history_from_payload(payload)

        self.assertEqual(history, [{"changes": "ok"}])


if __name__ == "__main__":
    unittest.main()
