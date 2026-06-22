from __future__ import annotations

import argparse
import json
import time
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

    complete = subparsers.add_parser("complete")
    complete.add_argument("--state", default=str(DEFAULT_STATE_PATH))
    complete.add_argument("--history", default=str(DEFAULT_HISTORY_PATH))
    complete.add_argument("--started-at", type=float, required=True)
    complete.add_argument("--note", default="")
    complete.add_argument("--status", default="done")
    complete.set_defaults(func=cmd_complete)

    args = parser.parse_args(argv)
    args.func(args)


def cmd_init(args: argparse.Namespace) -> None:
    payload = read_plan(Path(args.plan))
    option_id = args.option or payload.get("selected_option") or "risk_first"
    option = find_option(payload, option_id)
    sessions = option.get("sessions", [])
    state = {
        "plan": str(args.plan),
        "option": option_id,
        "goal": payload.get("goal", {}),
        "sessions": sessions,
        "current_index": 0,
        "completed": [],
    }
    write_state(Path(args.state), state)
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
        f"原计划：{format_dt(start)} - {end.strftime('%H:%M')}，{minutes} 分钟\n\n"
        f"{prompt}"
    )


def cmd_complete(args: argparse.Namespace) -> None:
    state_path = Path(args.state)
    state = read_state(state_path)
    session = require_current(state)
    planned = session_minutes(session)
    actual = max(1, int(round((time.time() - args.started_at) / 60)))

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
            "status": args.status,
            "note": args.note,
        }
    )
    state["completed"] = completed
    state["current_index"] = int(state.get("current_index", 0)) + 1
    write_state(state_path, state)

    remaining = len(state.get("sessions", [])) - int(state["current_index"])
    print(f"已记录：{session['title']}，实际 {actual} 分钟。剩余 {remaining} 个时间块。")


def read_state(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


if __name__ == "__main__":
    main()
