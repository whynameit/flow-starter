from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from .cli import find_option, read_plan
from .history import append_record
from .models import format_dt, parse_dt


DEFAULT_PLAN_PATH = Path(".flow-starter/plans/latest.json")
DEFAULT_STATE_PATH = Path(".flow-starter/focus-state.json")
DEFAULT_HISTORY_PATH = Path(".flow-starter/history.csv")


def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="flow-starter-focus")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init")
    init.add_argument("--plan", default=str(DEFAULT_PLAN_PATH))
    init.add_argument("--option", default="")
    init.add_argument("--state", default=str(DEFAULT_STATE_PATH))
    init.add_argument("--resume", action="store_true")
    init.add_argument("--resume-only", action="store_true")
    init.set_defaults(func=cmd_init)

    has_current = subparsers.add_parser("has-current")
    has_current.add_argument("--state", default=str(DEFAULT_STATE_PATH))
    has_current.set_defaults(func=cmd_has_current)

    current_title = subparsers.add_parser("current-title")
    current_title.add_argument("--state", default=str(DEFAULT_STATE_PATH))
    current_title.set_defaults(func=cmd_current_title)

    current_message = subparsers.add_parser("current-message")
    current_message.add_argument("--state", default=str(DEFAULT_STATE_PATH))
    current_message.set_defaults(func=cmd_current_message)

    current_minutes = subparsers.add_parser("current-minutes")
    current_minutes.add_argument("--state", default=str(DEFAULT_STATE_PATH))
    current_minutes.set_defaults(func=cmd_current_minutes)

    complete = subparsers.add_parser("complete")
    complete.add_argument("--state", default=str(DEFAULT_STATE_PATH))
    complete.add_argument("--history", default=str(DEFAULT_HISTORY_PATH))
    complete.add_argument("--started-at", type=float, required=True)
    complete.add_argument("--completed-at", type=float, default=0)
    complete.add_argument("--note", default="")
    complete.add_argument("--status", default="done")
    complete.add_argument("--kind", default="light")
    complete.add_argument("--adjust-remaining", action="store_true")
    complete.set_defaults(func=cmd_complete)

    shift = subparsers.add_parser("shift-remaining")
    shift.add_argument("--state", default=str(DEFAULT_STATE_PATH))
    shift.add_argument("--from-at", type=float, default=0)
    shift.set_defaults(func=cmd_shift_remaining)

    args = parser.parse_args(argv)
    args.func(args)


def cmd_init(args: argparse.Namespace) -> None:
    state_path = Path(args.state)
    if args.resume or args.resume_only:
        state = read_existing_state(state_path)
        if state and current_session(state):
            print(f"Resumed {len(state.get('sessions', []))} sessions.")
            return
        if args.resume_only:
            raise SystemExit("没有正在进行的逐项任务。")

    payload = read_plan(Path(args.plan))
    option_id = args.option or payload.get("selected_option") or "risk_first"
    option = find_option(payload, option_id)
    sessions = [normalize_session(dict(session)) for session in option.get("sessions", [])]
    state = {
        "plan": str(args.plan),
        "option": option_id,
        "goal": payload.get("goal", {}),
        "sessions": sessions,
        "current_index": 0,
        "completed": [],
    }
    write_state(state_path, state)
    print(f"Loaded {len(sessions)} sessions.")


def cmd_has_current(args: argparse.Namespace) -> None:
    state = read_state(Path(args.state))
    raise SystemExit(0 if current_session(state) else 1)


def cmd_current_title(args: argparse.Namespace) -> None:
    session = require_current(read_state(Path(args.state)))
    print(session["title"])


def cmd_current_message(args: argparse.Namespace) -> None:
    state = read_state(Path(args.state))
    session = require_current(state)
    total = len(state.get("sessions", []))
    index = int(state.get("current_index", 0)) + 1
    start = parse_dt(session["start"])
    end = parse_dt(session["end"])
    minutes = int((end - start).total_seconds() // 60)
    prompt = session.get("prompt", "").strip()
    print(
        f"{index}/{total}  {session['title']}\n\n"
        f"{format_time_line(session, start, end, minutes)}\n\n"
        f"这轮可以是不完美番茄：只要把注意力往这个方向放一段时间就算有用。\n"
        f"结束时可以只留一句刚才主要在做什么。\n\n"
        f"{prompt}"
    )


def cmd_current_minutes(args: argparse.Namespace) -> None:
    session = require_current(read_state(Path(args.state)))
    print(session_minutes(session))


def cmd_complete(args: argparse.Namespace) -> None:
    state_path = Path(args.state)
    state = read_state(state_path)
    session = require_current(state)
    planned = session_minutes(session)
    completed_at = float(args.completed_at or time.time())
    actual = max(1, int(round((completed_at - args.started_at) / 60)))

    append_record(
        Path(args.history),
        task_id=session["task_id"],
        planned_minutes=planned,
        actual_minutes=actual,
        status=args.status,
        note=args.note,
    )

    completed = list(state.get("completed") or [])
    completed.append(
        {
            "task_id": session["task_id"],
            "title": session["title"],
            "planned_minutes": planned,
            "actual_minutes": actual,
            "deviation_minutes": actual - planned,
            "status": args.status,
            "kind": args.kind,
            "note": args.note,
            "started_at": datetime.fromtimestamp(args.started_at).strftime("%Y-%m-%d %H:%M:%S"),
            "completed_at": datetime.fromtimestamp(completed_at).strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    state["completed"] = completed
    state["current_index"] = int(state.get("current_index", 0)) + 1
    if args.adjust_remaining:
        shift_remaining(state, datetime.fromtimestamp(completed_at))
    write_state(state_path, state)

    remaining = len(state.get("sessions", [])) - int(state["current_index"])
    print(build_completion_summary(session["title"], planned, actual, remaining, bool(args.adjust_remaining)))


def cmd_shift_remaining(args: argparse.Namespace) -> None:
    state_path = Path(args.state)
    state = read_state(state_path)
    start_at = datetime.fromtimestamp(float(args.from_at or time.time()))
    shift_remaining(state, start_at)
    write_state(state_path, state)
    print("已把剩余任务从当前时间顺延。")


def read_state(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_existing_state(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return read_state(path)
    except (OSError, json.JSONDecodeError):
        return None


def write_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def current_session(state: Dict[str, Any]) -> Dict[str, Any] | None:
    sessions = state.get("sessions", [])
    index = int(state.get("current_index", 0))
    if 0 <= index < len(sessions):
        return sessions[index]
    return None


def require_current(state: Dict[str, Any]) -> Dict[str, Any]:
    session = current_session(state)
    if not session:
        raise SystemExit("没有剩余任务。")
    return session


def session_minutes(session: Dict[str, Any]) -> int:
    start = parse_dt(session["start"])
    end = parse_dt(session["end"])
    return int((end - start).total_seconds() // 60)


def normalize_session(session: Dict[str, Any]) -> Dict[str, Any]:
    session.setdefault("original_start", session.get("start", ""))
    session.setdefault("original_end", session.get("end", ""))
    return session


def format_time_line(session: Dict[str, Any], start: datetime, end: datetime, minutes: int) -> str:
    current_line = f"当前建议：{format_dt(start)} - {end.strftime('%H:%M')}，{minutes} 分钟"
    original_start = session.get("original_start") or session.get("start")
    original_end = session.get("original_end") or session.get("end")
    if original_start == session.get("start") and original_end == session.get("end"):
        return f"原计划：{format_dt(start)} - {end.strftime('%H:%M')}，{minutes} 分钟"

    try:
        original_start_dt = parse_dt(original_start)
        original_end_dt = parse_dt(original_end)
        original_minutes = int((original_end_dt - original_start_dt).total_seconds() // 60)
        original_line = (
            f"原计划：{format_dt(original_start_dt)} - {original_end_dt.strftime('%H:%M')}，"
            f"{original_minutes} 分钟"
        )
    except (TypeError, ValueError):
        original_line = f"原计划：{original_start} - {original_end}"
    return f"{original_line}\n{current_line}"


def build_completion_summary(
    title: str,
    planned: int,
    actual: int,
    remaining: int,
    adjusted_remaining: bool,
) -> str:
    delta = actual - planned
    if delta > 0:
        delta_text = f"比计划多 {delta} 分钟"
    elif delta < 0:
        delta_text = f"比计划少 {abs(delta)} 分钟"
    else:
        delta_text = "和计划一致"

    lines = [
        f"已记录：{title}",
        f"计划 {planned} 分钟，实际 {actual} 分钟，{delta_text}。",
        f"剩余 {remaining} 个时间块。",
    ]
    if abs(delta) >= max(10, int(planned * 0.25)):
        lines.append("这轮偏差比较大，后面可以按实际节奏重估。")
    if adjusted_remaining and remaining > 0:
        lines.append("剩余任务已在逐项弹窗里从当前时间顺延；Apple Calendar 和 Pomofocus 不会自动改。")
    return "\n".join(lines)


def shift_remaining(state: Dict[str, Any], start_at: datetime) -> None:
    sessions = state.get("sessions", [])
    index = int(state.get("current_index", 0))
    cursor = start_at.replace(second=0, microsecond=0)
    if start_at.second or start_at.microsecond:
        cursor += timedelta(minutes=1)

    for session in sessions[index:]:
        normalize_session(session)
        minutes = session_minutes(session)
        session["start"] = format_dt(cursor)
        cursor = cursor + timedelta(minutes=minutes)
        session["end"] = format_dt(cursor)


if __name__ == "__main__":
    main()
