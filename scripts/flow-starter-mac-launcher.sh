#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

LOG_DIR="$PROJECT_ROOT/.flow-starter"
LOG_FILE="$LOG_DIR/last-app-run.log"
PROMPT_SRC="$PROJECT_ROOT/scripts/flow-starter-prompt.swift"
PROMPT_BIN="$PROJECT_ROOT/scripts/flow-starter-prompt"
BUILD_CACHE="$PROJECT_ROOT/.flow-starter/swift-cache"
mkdir -p "$LOG_DIR"

alert() {
  /usr/bin/osascript -e 'on run argv' \
    -e 'display alert (item 1 of argv) message (item 2 of argv) as warning' \
    -e 'end run' \
    "$1" "$2" >/dev/null
}

notify() {
  /usr/bin/osascript -e 'on run argv' \
    -e 'display notification (item 2 of argv) with title (item 1 of argv)' \
    -e 'end run' \
    "$1" "$2" >/dev/null || true
}

show_log_choice() {
  /usr/bin/osascript -e 'on run argv' \
    -e 'set response to display dialog (item 2 of argv) with title (item 1 of argv) buttons {"打开日志", "好"} default button "好"' \
    -e 'return button returned of response' \
    -e 'end run' \
    "$1" "$2"
}

ensure_prompt_helper() {
  if [[ ! -x "$PROMPT_BIN" || "$PROMPT_SRC" -nt "$PROMPT_BIN" ]]; then
    if ! command -v swiftc >/dev/null 2>&1; then
      alert "flow-starter" "缺少 Swift 编译器，无法打开多行输入弹窗。请先安装 Xcode Command Line Tools。"
      exit 1
    fi
    mkdir -p "$BUILD_CACHE"
    CLANG_MODULE_CACHE_PATH="$BUILD_CACHE" swiftc "$PROMPT_SRC" -o "$PROMPT_BIN"
    chmod +x "$PROMPT_BIN"
  fi
}

ask_text() {
  "$PROMPT_BIN" text --title "flow-starter" --message "$1" --default "${2:-}" --rows "${3:-3}"
}

ask_choice() {
  "$PROMPT_BIN" choice --title "flow-starter" --message "$1" --choices "$2" --default "$3"
}

ask_confirm() {
  "$PROMPT_BIN" confirm --title "flow-starter" --message "$1" --yes "${2:-是}" --no "${3:-否}"
}

PYTHON_BIN="$(command -v python3 || true)"
if [[ -z "$PYTHON_BIN" ]]; then
  alert "flow-starter" "没有找到 python3。可以先安装 Xcode Command Line Tools，或继续用已配置好的 Terminal 入口。"
  exit 1
fi

ensure_prompt_helper

DEFAULT_START="$(date '+%Y-%m-%d %H:%M')"
DEFAULT_DEADLINE="$(date -v+2d -v22H -v0M -v0S '+%Y-%m-%d %H:%M' 2>/dev/null || date '+%Y-%m-%d 22:00')"

mode="$(ask_choice "要做什么？" "新建计划|修正上一版计划" "新建计划")" || exit 0
option="$(ask_choice "选择排程策略" "risk_first|core_order|quick_wins" "risk_first")" || exit 0

if [[ "$mode" == "修正上一版计划" ]]; then
  changes="$(ask_text "想怎么修正上一版计划？可以写多行，比如调整顺序、合并、删减、补充。" "" 6)" || exit 0
  replace_calendar_choice="$(ask_confirm "导入修正版前，删除未来 21 天内旧的 flow-starter 日历块吗？建议删除，避免旧版和新版并列。" "删除旧块" "保留旧块")" || exit 0
  pomofocus_choice="$(ask_confirm "同时把任务交给 Pomofocus？会复制任务清单并打开 Pomofocus。" "发送" "不发送")" || exit 0
  open_claude_choice="$(ask_confirm "完成后打开 Claude？" "打开" "不打开")" || exit 0
  run_focus_choice="$(ask_confirm "生成修正版后，立即进入逐项任务弹窗？" "进入" "暂不")" || exit 0
  args=(
    "revise"
    "--changes" "$changes"
    "--option" "$option"
  )
  if [[ "$replace_calendar_choice" != "yes" ]]; then
    args+=("--keep-old-calendar")
  fi
else
  goal="$(ask_text "这次要完成什么目标？可以写多行。" "" 4)" || exit 0
  description="$(ask_text "补充说明，可留空。" "" 5)" || exit 0
  start_time="$(ask_text "从什么时候开始？格式：YYYY-MM-DD HH:MM" "$DEFAULT_START" 1)" || exit 0
  deadline="$(ask_text "截止时间是什么？格式：YYYY-MM-DD HH:MM" "$DEFAULT_DEADLINE" 1)" || exit 0
  claude_choice="$(ask_confirm "使用 Claude API 拆任务？" "使用" "不用")" || exit 0
  pomofocus_choice="$(ask_confirm "同时把任务交给 Pomofocus？会复制任务清单并打开 Pomofocus。" "发送" "不发送")" || exit 0
  open_claude_choice="$(ask_confirm "完成后打开 Claude？" "打开" "不打开")" || exit 0
  run_focus_choice="$(ask_confirm "生成计划后，立即进入逐项任务弹窗？" "进入" "暂不")" || exit 0

  args=(
    "start"
    "--goal" "$goal"
    "--deadline" "$deadline"
    "--start" "$start_time"
    "--option" "$option"
  )

  if [[ -n "${description//[[:space:]]/}" ]]; then
    args+=("--description" "$description")
  fi

  if [[ "$claude_choice" != "yes" ]]; then
    args+=("--no-claude")
  fi
fi

if [[ "$open_claude_choice" == "yes" ]]; then
  args+=("--open-claude")
fi
if [[ "${pomofocus_choice:-no}" == "yes" ]]; then
  args+=("--pomofocus")
fi

notify "flow-starter" "正在生成计划、日历提醒和 Obsidian 笔记。"
set +e
{
  echo "flow-starter app run"
  date
  printf 'Project: %s\n\n' "$PROJECT_ROOT"
  "$PYTHON_BIN" -m flow_starter "${args[@]}"
} >"$LOG_FILE" 2>&1
status=$?
set -e

if [[ "$status" -eq 0 ]]; then
  notify "flow-starter" "完成。Calendar、Obsidian、Pomofocus 和 Claude 已按设置处理。"
  if [[ "$run_focus_choice" == "yes" ]]; then
    "$PROJECT_ROOT/scripts/flow-starter-task-runner.sh" "$option" "${pomofocus_choice:-no}" >>"$LOG_FILE" 2>&1 || true
  fi
  success_message="$(printf '完成：计划、提醒、笔记和 Pomofocus 已经处理。\n\n日志：%s' "$LOG_FILE")"
  button="$(show_log_choice "flow-starter" "$success_message")" || true
  if [[ "$button" == "打开日志" ]]; then
    open "$LOG_FILE"
  fi
  exit 0
fi

simple_error="$("$PYTHON_BIN" -m flow_starter.mac_form summarize-error "$LOG_FILE" 2>/dev/null || echo "运行失败，请打开日志查看完整信息。")"
failure_message="$(printf '%s\n\n完整日志：%s' "$simple_error" "$LOG_FILE")"
button="$(show_log_choice "flow-starter" "$failure_message")" || true
if [[ "$button" == "打开日志" ]]; then
  open "$LOG_FILE"
fi
exit 0
