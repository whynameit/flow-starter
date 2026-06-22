import unittest
from datetime import datetime

from flow_starter.claude_client import build_json_repair_prompt, build_revision_prompt, format_api_error, is_placeholder_api_key
from flow_starter.models import Goal, TaskBlock


class ClaudeClientTests(unittest.TestCase):
    def test_auth_error_is_actionable(self) -> None:
        message = format_api_error(401, '{"error":"invalid x-api-key"}')

        self.assertIn("ANTHROPIC_API_KEY is invalid", message)
        self.assertIn("Claude Pro membership is not an API key", message)

    def test_placeholder_key_is_detected(self) -> None:
        self.assertTrue(is_placeholder_api_key("sk-ant-api03-your-key-here"))
        self.assertTrue(is_placeholder_api_key("sk-ant-api03-short"))
        self.assertFalse(is_placeholder_api_key("sk-ant-api03-" + "x" * 60))

    def test_low_credit_error_is_actionable(self) -> None:
        message = format_api_error(400, '{"message":"Your credit balance is too low"}')

        self.assertIn("key is valid", message)
        self.assertIn("no available credits", message)
        self.assertIn("run without --use-claude", message)

    def test_repair_prompt_requires_json_only(self) -> None:
        prompt = build_json_repair_prompt('{"tasks": [')

        self.assertIn("只输出 JSON", prompt)
        self.assertIn("tasks", prompt)
        self.assertIn('{"tasks": [', prompt)

    def test_revision_prompt_requests_complete_task_list(self) -> None:
        goal = Goal(title="Prepare interview", deadline=datetime(2026, 6, 24, 22, 0))
        tasks = [
            TaskBlock(
                id="task_1",
                title="Read",
                outcome="Notes",
                p50_minutes=30,
                p90_minutes=60,
            )
        ]

        prompt = build_revision_prompt(
            goal,
            tasks,
            "先合并前两个任务",
            revision_history=[
                {"changes": "先跑 demo 再读论文", "created_at": "2026-06-22 21:00"},
                {"changes": "删掉博客草稿", "created_at": "2026-06-22 21:30"},
            ],
        )

        self.assertIn("修正后的完整任务列表", prompt)
        self.assertIn("先合并前两个任务", prompt)
        self.assertIn("先跑 demo 再读论文", prompt)
        self.assertIn("删掉博客草稿", prompt)
        self.assertIn("必须保留此前每轮已经确认过的调整意图", prompt)
        self.assertIn('"id": "task_1"', prompt)


if __name__ == "__main__":
    unittest.main()
