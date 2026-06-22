import unittest
from datetime import datetime

from flow_starter.mac_form import build_start_argv, parse_form, render_form, summarize_error


class MacFormTests(unittest.TestCase):
    def test_parse_form_keeps_multiline_values(self) -> None:
        form = """# comment
目标:
读 VGGT 论文
做面试准备

补充说明:
先跑 demo
再写 runbook

开始时间: 2026-06-22 09:00
截止时间: 2026-06-24 22:00
排程策略: risk_first
使用Claude: 否
完成后打开Claude: 是
"""

        values = parse_form(form)
        argv = build_start_argv(values)

        self.assertIn("读 VGGT 论文\n做面试准备", argv)
        self.assertIn("先跑 demo\n再写 runbook", argv)
        self.assertIn("--no-claude", argv)
        self.assertIn("--open-claude", argv)

    def test_render_form_uses_predictable_defaults(self) -> None:
        text = render_form(datetime(2026, 6, 22, 9, 30, 1))

        self.assertIn("开始时间: 2026-06-22 09:30", text)
        self.assertIn("截止时间: 2026-06-24 22:00", text)

    def test_summarize_error_prefers_key_reason(self) -> None:
        text = """
Traceback (most recent call last):
  File "x", line 1
Claude API key is valid, but the Anthropic API account has no available credits.
"""

        self.assertEqual(summarize_error(text), "Anthropic API 余额不足。")

    def test_summarize_error_handles_calendar_permission(self) -> None:
        text = "无法删除旧 flow-starter 日历块。请检查 Calendar 权限。"

        self.assertIn("无法删除旧日历块", summarize_error(text))


if __name__ == "__main__":
    unittest.main()
