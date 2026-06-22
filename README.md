# 任务快速启动助手

面向 macOS 的本地学习、科研、项目任务快速启动助手。

它可以把一个有截止日期的目标拆成可执行任务块，结合课表生成排程，导入 Apple Calendar，写入 Obsidian，并用逐项弹窗帮助你开始、完成、记录实际用时。

## 主要功能

- 读取 WEMUST 导出的 Excel 课表。
- 使用 Claude API 拆解目标和修正任务。
- 自动生成多个排程方案，默认使用 `risk_first`。
- 导出 Apple Calendar `.ics` 提醒。
- 写入 Obsidian 学习笔记。
- 支持多轮修正任务顺序、合并、删减和时间偏好。
- 修正计划时可删除旧的 StudyFlow 日历块，避免新版旧版并列。
- 支持逐项任务弹窗，记录实际用时并改进以后估时。

## 配置

复制环境变量示例：

```bash
cp .env.example .env
```

编辑 `.env`，至少配置：

```bash
ANTHROPIC_API_KEY=你的 Anthropic API key
CLAUDE_MODEL=claude-sonnet-4-5
```

可选配置：

```bash
OBSIDIAN_VAULT=/Users/你的用户名/Documents/Obsidian Vault
BLOG_SITE_DIR=/Users/你的用户名/Documents/your-blog
BLOG_BASE_URL=https://example.github.io
STUDYFLOW_BUSY=/Users/你的用户名/Downloads/學生課表.xlsx
```

不要把 `.env` 提交到 GitHub。

## 使用

在 Finder 中双击：

```text
StudyFlow.app
```

如果 macOS 拦截，也可以双击：

```text
StudyFlow.command
```

启动后可以选择：

- `新建计划`
- `修正上一版计划`

新建计划会依次询问目标、补充说明、开始时间、截止时间和排程策略。目标和补充说明支持多行输入。

修正上一版计划时，可以直接写：

```text
把前两个任务合并，先跑 demo，再读论文，不要在 10 点半前安排任务，可以排到凌晨 3 点前
```

工具会记住多轮修正历史。除非你明确推翻前面的要求，否则后续修正会保留之前已经确认过的调整。

## 命令行备用入口

检查配置：

```bash
./sf doctor --claude
```

新建计划：

```bash
./sf start \
  --goal "学习一个算法并准备项目面试" \
  --deadline "2026-06-24 22:00" \
  --start "2026-06-22 09:00" \
  --open-claude
```

修正上一版计划：

```bash
./sf revise --changes "把前两个任务合并，先跑 demo，再读论文"
```

如果想保留旧的 Calendar 块用于对照：

```bash
./sf revise --changes "调整任务顺序" --keep-old-calendar
```

## 测试

```bash
python3 -m unittest discover -s tests
```
