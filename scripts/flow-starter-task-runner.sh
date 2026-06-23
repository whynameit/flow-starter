#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

OPTION="${1:-risk_first}"
USE_POMOFOCUS="${2:-no}"
POMOFOCUS_APP="${FLOW_STARTER_POMOFOCUS_APP:-/Users/rh/Applications/Chrome Apps.localized/Pomofocus.app}"
PROMPT_BIN="$PROJECT_ROOT/scripts/flow-starter-prompt"
PYTHON_BIN="$(command -v python3 || true)"

if [[ -z "$PYTHON_BIN" ]]; then
  exit 1
fi
if [[ ! -x "$PROMPT_BIN" ]]; then
  exit 1
fi

"$PYTHON_BIN" -m flow_starter.focus_runner init --option "$OPTION" >/dev/null

open_pomofocus() {
  if [[ -e "$POMOFOCUS_APP" ]]; then
    open "$POMOFOCUS_APP" >/dev/null 2>&1 || true
  else
    open "https://pomofocus.io/app" >/dev/null 2>&1 || true
  fi
}

while "$PYTHON_BIN" -m flow_starter.focus_runner has-current >/dev/null 2>&1; do
  title="$("$PYTHON_BIN" -m flow_starter.focus_runner current-title)"
  message="$("$PYTHON_BIN" -m flow_starter.focus_runner current-message)"

  start_choice="$("$PROMPT_BIN" confirm --title "flow-starter 当前任务" --message "$message" --yes "开始" --no "停下")" || exit 0
  if [[ "$start_choice" != "yes" ]]; then
    exit 0
  fi

  started_at="$(date +%s)"
  if [[ "$USE_POMOFOCUS" == "yes" ]]; then
    printf '%s' "$title" | pbcopy >/dev/null 2>&1 || true
    open_pomofocus
    finish_message="$(printf '正在做：%s\n\n已打开 Pomofocus，并把任务名复制到剪贴板。请在 Pomofocus 里开始计时：做一会，短休息一会。这个任务完成后回到这里点“完成 ✓”，我会记录实际用时。' "$title")"
  else
    finish_message="$(printf '正在做：%s\n\n完成后点“完成 ✓”，我会自动记录实际用时。' "$title")"
  fi
  finish_choice="$("$PROMPT_BIN" confirm --title "flow-starter 计时中" --message "$finish_message" --yes "完成 ✓" --no "暂停")" || exit 0
  if [[ "$finish_choice" != "yes" ]]; then
    exit 0
  fi

  note="$("$PROMPT_BIN" text --title "flow-starter 完成记录" --message "这一步完成了什么？卡在哪里？可留空。" --default "" --rows 4)" || note=""
  summary="$("$PYTHON_BIN" -m flow_starter.focus_runner complete --started-at "$started_at" --note "$note")"

  if "$PYTHON_BIN" -m flow_starter.focus_runner has-current >/dev/null 2>&1; then
    continue_message="$(printf '%s\n\n继续下一个任务吗？' "$summary")"
    continue_choice="$("$PROMPT_BIN" confirm --title "flow-starter" --message "$continue_message" --yes "继续" --no "先停")" || exit 0
    if [[ "$continue_choice" != "yes" ]]; then
      exit 0
    fi
  else
    done_message="$(printf '%s\n\n今天这组任务已经全部走完。' "$summary")"
    "$PROMPT_BIN" confirm --title "flow-starter" --message "$done_message" --yes "好" --no "关闭" >/dev/null || true
    exit 0
  fi
done
