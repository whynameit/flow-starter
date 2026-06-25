#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

OPTION="${1:-risk_first}"
USE_POMOFOCUS="${2:-no}"
RUN_MODE="${3:-reset}"
POMOFOCUS_APP="${FLOW_STARTER_POMOFOCUS_APP:-/Users/rh/Applications/Chrome Apps.localized/Pomofocus.app}"
PROMPT_SRC="$PROJECT_ROOT/scripts/flow-starter-prompt.swift"
PROMPT_BIN="$PROJECT_ROOT/scripts/flow-starter-prompt"
BUILD_CACHE="$PROJECT_ROOT/.flow-starter/swift-cache"
PYTHON_BIN="$(command -v python3 || true)"
MINUTE_SECONDS="${FLOW_STARTER_MINUTE_SECONDS:-60}"
AUTO_START_NEXT="no"
timer_pids=()

if [[ -z "$PYTHON_BIN" ]]; then
  exit 1
fi

ensure_prompt_helper() {
  if [[ ! -x "$PROMPT_BIN" || "$PROMPT_SRC" -nt "$PROMPT_BIN" ]]; then
    if ! command -v swiftc >/dev/null 2>&1; then
      exit 1
    fi
    mkdir -p "$BUILD_CACHE"
    CLANG_MODULE_CACHE_PATH="$BUILD_CACHE" swiftc "$PROMPT_SRC" -o "$PROMPT_BIN"
    chmod +x "$PROMPT_BIN"
  fi
}

ensure_prompt_helper

if [[ "$RUN_MODE" == "resume" ]]; then
  if ! "$PYTHON_BIN" -m flow_starter.focus_runner init --resume-only >/dev/null 2>&1; then
    "$PROMPT_BIN" notice --title "flow-starter" --message "没有找到正在进行的逐项任务。可以先新建计划，或在生成计划后选择进入逐项任务弹窗。" --button "好" --duration 0 >/dev/null || true
    exit 0
  fi
else
  "$PYTHON_BIN" -m flow_starter.focus_runner init --option "$OPTION" >/dev/null
fi

open_pomofocus() {
  if [[ -e "$POMOFOCUS_APP" ]]; then
    open "$POMOFOCUS_APP" >/dev/null 2>&1 || true
  else
    open "https://pomofocus.io/app" >/dev/null 2>&1 || true
  fi
}

minute_seconds() {
  if [[ "$MINUTE_SECONDS" =~ ^[0-9]+$ ]]; then
    printf '%s' "$MINUTE_SECONDS"
  else
    printf '60'
  fi
}

seconds_for_minutes() {
  local minutes="$1"
  local unit
  unit="$(minute_seconds)"
  local seconds=$(( minutes * unit ))
  if (( seconds < 1 )); then
    seconds=1
  fi
  printf '%s' "$seconds"
}

cancel_timers() {
  local pid
  for pid in "${timer_pids[@]:-}"; do
    kill "$pid" >/dev/null 2>&1 || true
  done
  timer_pids=()
}

schedule_notice() {
  local delay_seconds="$1"
  local title="$2"
  local message="$3"
  local duration="$4"
  if (( delay_seconds <= 0 )); then
    return
  fi
  (
    sleep "$delay_seconds"
    "$PROMPT_BIN" notice --title "$title" --message "$message" --button "好" --duration "$duration" >/dev/null 2>&1 || true
  ) &
  timer_pids+=("$!")
}

schedule_task_reminders() {
  local title="$1"
  local planned_minutes="$2"
  local end_seconds
  cancel_timers
  if (( planned_minutes >= 10 )); then
    schedule_notice \
      "$(( $(seconds_for_minutes "$planned_minutes") / 2 ))" \
      "flow-starter 轻提醒" \
      "$(printf '我还在这个任务上吗？\n\n%s' "$title")" \
      "8"
  fi
  end_seconds="$(seconds_for_minutes "$planned_minutes")"
  schedule_notice \
    "$end_seconds" \
    "flow-starter 到时间" \
    "$(printf '这轮到时间了。\n\n%s\n\n可以完成、继续、休息，或者标记卡住。' "$title")" \
    "0"
}

pause_until_return() {
  "$PROMPT_BIN" notice --title "flow-starter 休息" --message "休息一下。回来后点“继续”。" --button "继续" --duration 0 >/dev/null || true
}

pause_current_task() {
  local pause_started
  local pause_ended
  pause_started="$(date +%s)"
  pause_until_return
  pause_ended="$(date +%s)"
  started_at=$(( started_at + pause_ended - pause_started ))
}

trap cancel_timers EXIT

while "$PYTHON_BIN" -m flow_starter.focus_runner has-current >/dev/null 2>&1; do
  title="$("$PYTHON_BIN" -m flow_starter.focus_runner current-title)"
  message="$("$PYTHON_BIN" -m flow_starter.focus_runner current-message)"
  planned_minutes="$("$PYTHON_BIN" -m flow_starter.focus_runner current-minutes)"
  if [[ ! "$planned_minutes" =~ ^[0-9]+$ ]]; then
    planned_minutes=25
  fi

  if [[ "$AUTO_START_NEXT" == "yes" ]]; then
    AUTO_START_NEXT="no"
  else
    start_choice="$("$PROMPT_BIN" confirm --title "flow-starter 当前任务" --message "$message" --yes "开始" --no "停下")" || exit 0
    if [[ "$start_choice" != "yes" ]]; then
      exit 0
    fi
  fi

  started_at="$(date +%s)"
  opened_pomofocus="no"
  status="done"

  while true; do
    if [[ "$USE_POMOFOCUS" == "yes" && "$opened_pomofocus" == "no" ]]; then
      printf '%s' "$title" | pbcopy >/dev/null 2>&1 || true
      open_pomofocus
      opened_pomofocus="yes"
    fi

    if [[ "$USE_POMOFOCUS" == "yes" ]]; then
      finish_message="$(printf '正在做：%s\n\n已打开 Pomofocus，并把任务名复制到剪贴板。到计划时间会弹一次提醒；中途轻提醒会自动消失。' "$title")"
    else
      finish_message="$(printf '正在做：%s\n\n到计划时间会弹一次提醒；中途轻提醒会自动消失。' "$title")"
    fi

    schedule_task_reminders "$title" "$planned_minutes"
    finish_choice="$("$PROMPT_BIN" choice --title "flow-starter 计时中" --message "$finish_message" --choices "完成并记录|继续当前任务|休息一下|标记卡住|先停" --default "完成并记录")" || {
      cancel_timers
      "$PROMPT_BIN" notice --title "flow-starter" --message "这个窗口不会因为点“取消”而结束任务。要暂停流程，请在下拉框里选“先停”。" --button "继续" --duration 4 >/dev/null || true
      continue
    }
    cancel_timers

    case "$finish_choice" in
      "完成并记录")
        status="done"
        break
        ;;
      "标记卡住")
        status="blocked"
        break
        ;;
      "继续当前任务")
        continue
        ;;
      "休息一下")
        pause_current_task
        continue
        ;;
      *)
        exit 0
        ;;
    esac
  done

  kind_choice="$("$PROMPT_BIN" choice --title "flow-starter 记录方式" --message "这轮想怎么记？轻番茄可以很松，深番茄适合重要理解/产出。" --choices "轻番茄|深番茄|跳过记录" --default "轻番茄")" || kind_choice="轻番茄"
  case "$kind_choice" in
    "深番茄")
      kind="deep"
      note_message="$(printf '本轮想留下什么？\n实际留下什么？\n下轮怎么办？\n\n可留空。')"
      rows=6
      ;;
    "跳过记录")
      kind="light"
      note=""
      rows=0
      ;;
    *)
      kind="light"
      note_message="$(printf '刚才主要在做什么？\n下一步：继续 / 休息 / 换任务。\n\n可留空。')"
      rows=4
      ;;
  esac

  if (( rows > 0 )); then
    note="$("$PROMPT_BIN" text --title "flow-starter 完成记录" --message "$note_message" --default "" --rows "$rows")" || note=""
  fi

  summary="$("$PYTHON_BIN" -m flow_starter.focus_runner complete --started-at "$started_at" --note "$note" --status "$status" --kind "$kind" --adjust-remaining)"

  if "$PYTHON_BIN" -m flow_starter.focus_runner has-current >/dev/null 2>&1; then
    next_message="$(printf '%s\n\n下一步做什么？' "$summary")"
    while true; do
      next_choice="$("$PROMPT_BIN" choice --title "flow-starter 任务结算" --message "$next_message" --choices "开始下一个任务|休息一下|重估后续任务|先停" --default "开始下一个任务")" || {
        "$PROMPT_BIN" notice --title "flow-starter" --message "要退出流程，请在下拉框里选“先停”。点“取消”会回到任务结算。" --button "继续" --duration 4 >/dev/null || true
        continue
      }
      break
    done
    case "$next_choice" in
      "开始下一个任务")
        AUTO_START_NEXT="yes"
        ;;
      "休息一下")
        pause_until_return
        AUTO_START_NEXT="yes"
        ;;
      "重估后续任务")
        "$PYTHON_BIN" -m flow_starter.focus_runner shift-remaining >/dev/null || true
        "$PROMPT_BIN" notice --title "flow-starter" --message "已把剩余任务从此刻重新顺延。更细的内容重估，可以之后用“修正上一版计划”继续改。" --button "继续" --duration 0 >/dev/null || true
        AUTO_START_NEXT="yes"
        ;;
      *)
        exit 0
        ;;
    esac
  else
    done_message="$(printf '%s\n\n今天这组任务已经全部走完。' "$summary")"
    "$PROMPT_BIN" notice --title "flow-starter" --message "$done_message" --button "好" --duration 0 >/dev/null || true
    exit 0
  fi
done
