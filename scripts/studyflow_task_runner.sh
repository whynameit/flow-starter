#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

OPTION="${1:-risk_first}"
PROMPT_BIN="$PROJECT_ROOT/scripts/studyflow_prompt"
PYTHON_BIN="$(command -v python3 || true)"

if [[ -z "$PYTHON_BIN" ]]; then
  exit 1
fi
if [[ ! -x "$PROMPT_BIN" ]]; then
  exit 1
fi

"$PYTHON_BIN" -m studyflow.focus_runner init --option "$OPTION" >/dev/null

while "$PYTHON_BIN" -m studyflow.focus_runner has-current >/dev/null 2>&1; do
  title="$("$PYTHON_BIN" -m studyflow.focus_runner current-title)"
  message="$("$PYTHON_BIN" -m studyflow.focus_runner current-message)"

  start_choice="$("$PROMPT_BIN" confirm --title "StudyFlow 当前任务" --message "$message" --yes "开始" --no "停下")" || exit 0
  if [[ "$start_choice" != "yes" ]]; then
    exit 0
  fi

  started_at="$(date +%s)"
  finish_message="$(printf '正在做：%s\n\n完成后点“完成 ✓”，我会自动记录实际用时。' "$title")"
  finish_choice="$("$PROMPT_BIN" confirm --title "StudyFlow 计时中" --message "$finish_message" --yes "完成 ✓" --no "暂停")" || exit 0
  if [[ "$finish_choice" != "yes" ]]; then
    exit 0
  fi

  note="$("$PROMPT_BIN" text --title "StudyFlow 完成记录" --message "这一步完成了什么？卡在哪里？可留空。" --default "" --rows 4)" || note=""
  summary="$("$PYTHON_BIN" -m studyflow.focus_runner complete --started-at "$started_at" --note "$note")"

  if "$PYTHON_BIN" -m studyflow.focus_runner has-current >/dev/null 2>&1; then
    continue_message="$(printf '%s\n\n继续下一个任务吗？' "$summary")"
    continue_choice="$("$PROMPT_BIN" confirm --title "StudyFlow" --message "$continue_message" --yes "继续" --no "先停")" || exit 0
    if [[ "$continue_choice" != "yes" ]]; then
      exit 0
    fi
  else
    done_message="$(printf '%s\n\n今天这组任务已经全部走完。' "$summary")"
    "$PROMPT_BIN" confirm --title "StudyFlow" --message "$done_message" --yes "好" --no "关闭" >/dev/null || true
    exit 0
  fi
done
