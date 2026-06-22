from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .blog_export import write_blog_draft
from .calendar_cleanup import delete_future_studyflow_events
from .calendar_export import write_option_ics
from .calendar_import import read_busy_slots
from .claude_client import (
    ClaudeAPIError,
    ClaudeClient,
    ClaudeConfigError,
    ClaudeResponseError,
    decompose_goal_with_claude,
    fallback_decompose,
    is_placeholder_api_key,
    revise_tasks_with_claude,
)
from .config import DEFAULT_OBSIDIAN_VAULT, DEFAULT_PLANS_DIR, env_path, load_dotenv
from .history import append_record, estimate_personal_multiplier
from .models import Goal, ScheduleOption, ScheduledSession, TaskBlock, parse_dt, tasks_from_dicts, to_jsonable
from .obsidian import build_obsidian_uri, write_goal_note
from .schedule_preferences import extract_schedule_preferences, merge_schedule_preferences
from .scheduler import SchedulePlanner

DEFAULT_BUSY_PATH = Path("/Users/rh/Downloads/學生課表20260619232245.xlsx")
DEFAULT_CALENDAR_ICS = Path(".studyflow/selected-plan.ics")


def main(argv: List[str] | None = None) -> None:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="studyflow")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="Decompose a goal and generate schedule options.")
    plan.add_argument("--goal", required=True)
    plan.add_argument("--description", default="")
    plan.add_argument("--deadline", required=True)
    plan.add_argument("--start", default="")
    plan.add_argument("--busy", action="append", default=[])
    plan.add_argument("--use-claude", action="store_true")
    plan.add_argument("--risk-multiplier", type=float, default=0.0)
    plan.add_argument("--working-day-start", default="08:30")
    plan.add_argument("--working-day-end", default="23:00")
    plan.add_argument("--allow-overflow", action="store_true", help="Keep scheduling remaining tasks after the deadline.")
    plan.add_argument("--out", default=str(DEFAULT_PLANS_DIR / "latest.json"))
    plan.set_defaults(func=cmd_plan)

    start = subparsers.add_parser("start", help="One-command workflow: plan, export reminders, write Obsidian, and open them.")
    start.add_argument("--goal", required=True)
    start.add_argument("--description", default="")
    start.add_argument("--deadline", required=True)
    start.add_argument("--start", default="")
    start.add_argument("--busy", action="append", default=[])
    start.add_argument("--no-claude", action="store_true")
    start.add_argument("--option", default="risk_first")
    start.add_argument("--risk-multiplier", type=float, default=0.0)
    start.add_argument("--working-day-start", default="08:30")
    start.add_argument("--working-day-end", default="23:00")
    start.add_argument("--no-overflow", action="store_true", help="Do not schedule tasks after the deadline.")
    start.add_argument("--out", default=str(DEFAULT_PLANS_DIR / "latest.json"))
    start.add_argument("--calendar-ics", default=str(DEFAULT_CALENDAR_ICS))
    start.add_argument("--no-calendar", action="store_true")
    start.add_argument("--no-obsidian", action="store_true")
    start.add_argument("--obsidian-vault", default=str(DEFAULT_OBSIDIAN_VAULT))
    start.add_argument("--obsidian-folder", default="StudyFlow")
    start.add_argument("--no-open", action="store_true")
    start.add_argument("--open-claude", action="store_true", help="Open Claude after exporting Calendar and Obsidian.")
    start.set_defaults(func=cmd_start)

    revise = subparsers.add_parser("revise", help="Revise the latest plan with Claude and replace old StudyFlow calendar blocks.")
    revise.add_argument("--changes", required=True)
    revise.add_argument("--plan", default=str(DEFAULT_PLANS_DIR / "latest.json"))
    revise.add_argument("--option", default="")
    revise.add_argument("--start", default="")
    revise.add_argument("--deadline", default="")
    revise.add_argument("--busy", action="append", default=[])
    revise.add_argument("--risk-multiplier", type=float, default=0.0)
    revise.add_argument("--working-day-start", default="")
    revise.add_argument("--working-day-end", default="")
    revise.add_argument("--no-overflow", action="store_true")
    revise.add_argument("--out", default=str(DEFAULT_PLANS_DIR / "latest.json"))
    revise.add_argument("--calendar-ics", default="")
    revise.add_argument("--keep-old-calendar", action="store_true", help="Do not delete old future StudyFlow calendar events before import.")
    revise.add_argument("--replace-calendar-days", type=int, default=21)
    revise.add_argument("--no-open", action="store_true")
    revise.add_argument("--open-claude", action="store_true")
    revise.set_defaults(func=cmd_revise)

    app = subparsers.add_parser("app", help="Open the native Mac helper dialogs.")
    app.set_defaults(func=cmd_app)

    doctor = subparsers.add_parser("doctor", help="Check local configuration and optionally ping Claude API.")
    doctor.add_argument("--claude", action="store_true", help="Make a tiny Claude API request to verify credits and model access.")
    doctor.set_defaults(func=cmd_doctor)

    commit = subparsers.add_parser("commit", help="Choose one schedule option and export reminders/notes.")
    commit.add_argument("--plan", required=True)
    commit.add_argument("--option", required=True)
    commit.add_argument("--calendar-ics", default="")
    commit.add_argument("--write-obsidian", action="store_true")
    commit.add_argument("--obsidian-vault", default=str(DEFAULT_OBSIDIAN_VAULT))
    commit.add_argument("--obsidian-folder", default="StudyFlow")
    commit.set_defaults(func=cmd_commit)

    export_blog = subparsers.add_parser("export-blog", help="Export a public blog draft from a plan.")
    export_blog.add_argument("--plan", required=True)
    export_blog.add_argument("--option", required=True)
    export_blog.add_argument("--out", default="")
    export_blog.add_argument("--site-dir", default="")
    export_blog.add_argument("--format", choices=["generic", "al-folio"], default="generic")
    export_blog.set_defaults(func=cmd_export_blog)

    show_calendar = subparsers.add_parser("show-calendar", help="Print imported busy slots from CSV/ICS/XLSX.")
    show_calendar.add_argument("paths", nargs="+")
    show_calendar.set_defaults(func=cmd_show_calendar)

    record = subparsers.add_parser("record", help="Record actual time to improve future estimates.")
    record.add_argument("--task-id", required=True)
    record.add_argument("--planned-minutes", type=int, required=True)
    record.add_argument("--actual-minutes", type=int, required=True)
    record.add_argument("--status", default="done")
    record.add_argument("--note", default="")
    record.add_argument("--history", default=".studyflow/history.csv")
    record.set_defaults(func=cmd_record)

    return parser


def cmd_plan(args: argparse.Namespace) -> None:
    start = parse_dt(args.start) if args.start else parse_dt_now_minute()
    goal = build_goal(args)
    payload, options = generate_plan_payload(
        goal=goal,
        start=start,
        busy_paths=args.busy,
        use_claude=args.use_claude,
        risk_multiplier=args.risk_multiplier,
        working_day_start=args.working_day_start,
        working_day_end=args.working_day_end,
        allow_overflow=args.allow_overflow,
    )
    out_path = Path(args.out)
    write_plan_payload(payload, out_path)

    print(f"Plan written: {out_path}")
    print_plan_summary(options)


def cmd_start(args: argparse.Namespace) -> None:
    start = parse_dt(args.start) if args.start else parse_dt_now_minute()
    goal = build_goal(args)
    busy_paths = resolve_busy_paths(args.busy)
    use_claude = not args.no_claude

    payload, options = generate_plan_payload(
        goal=goal,
        start=start,
        busy_paths=busy_paths,
        use_claude=use_claude,
        risk_multiplier=args.risk_multiplier,
        working_day_start=args.working_day_start,
        working_day_end=args.working_day_end,
        allow_overflow=not args.no_overflow,
    )
    payload["selected_option"] = args.option
    plan_path = Path(args.out)
    write_plan_payload(payload, plan_path)

    print(f"Plan written: {plan_path}")
    print_plan_summary(options)

    option = load_option(find_option(payload, args.option))
    print(f"Selected option: {option.id} ({option.label})")

    calendar_path: Optional[Path] = None
    if not args.no_calendar:
        calendar_path = write_option_ics(option, Path(args.calendar_ics))
        print(f"Calendar ICS written: {calendar_path}")

    obsidian_uri = ""
    if not args.no_obsidian:
        tasks = tasks_from_dicts(payload["tasks"])
        vault = env_path("OBSIDIAN_VAULT", Path(args.obsidian_vault))
        note_path = write_goal_note(goal, tasks, option, vault, folder=args.obsidian_folder)
        obsidian_uri = build_obsidian_uri(vault, note_path)
        print(f"Obsidian note written: {note_path}")
        print(f"Obsidian URI: {obsidian_uri}")

    if not args.no_open:
        if calendar_path:
            open_target(str(calendar_path))
        if obsidian_uri:
            open_target(obsidian_uri)
        if args.open_claude:
            open_claude()


def cmd_revise(args: argparse.Namespace) -> None:
    source_plan = Path(args.plan)
    payload = read_plan(source_plan)
    goal = load_goal(payload["goal"])
    if args.deadline:
        goal.deadline = parse_dt(args.deadline)
    start = parse_dt(args.start) if args.start else parse_dt_now_minute()
    source_tasks = tasks_from_dicts(payload["tasks"])
    previous_preferences = schedule_preferences_from_payload(payload)
    change_preferences = extract_schedule_preferences(args.changes)
    schedule_preferences = merge_schedule_preferences(previous_preferences, change_preferences)
    working_day_start = args.working_day_start or schedule_preferences.get("working_day_start") or "08:30"
    working_day_end = args.working_day_end or schedule_preferences.get("working_day_end") or "23:00"
    option_id = args.option or payload.get("selected_option") or "risk_first"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    batch_label = f"修正 {stamp}"
    existing_history = revision_history_from_payload(payload)
    current_revision = {
        "source_plan": str(source_plan),
        "changes": args.changes,
        "schedule_preferences": change_preferences,
        "batch_label": batch_label,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    revision_history = [*existing_history, current_revision]

    client = ClaudeClient()
    try:
        revised_tasks = revise_tasks_with_claude(
            client,
            goal,
            source_tasks,
            args.changes,
            revision_history=revision_history,
        )
    except (ClaudeConfigError, ClaudeAPIError, ClaudeResponseError) as exc:
        raise SystemExit(str(exc)) from exc

    busy_paths = resolve_busy_paths(args.busy)
    busy_slots = read_busy_slots(busy_paths)
    effective_risk_multiplier = args.risk_multiplier or estimate_personal_multiplier(Path(".studyflow/history.csv"))
    planner = SchedulePlanner(
        working_day_start=working_day_start,
        working_day_end=working_day_end,
        risk_multiplier=effective_risk_multiplier,
        allow_overflow=not args.no_overflow,
    )
    options = planner.generate_options(revised_tasks, busy_slots, start=start, deadline=goal.deadline)
    revised_payload = {
        "goal": to_jsonable(goal),
        "tasks": to_jsonable(revised_tasks),
        "busy_slots": to_jsonable(busy_slots),
        "risk_multiplier": effective_risk_multiplier,
        "allow_overflow": not args.no_overflow,
        "schedule_preferences": {
            "working_day_start": working_day_start,
            "working_day_end": working_day_end,
        },
        "selected_option": option_id,
        "revision": current_revision,
        "revision_history": revision_history,
        "options": to_jsonable(options),
    }

    out_path = Path(args.out)
    write_plan_payload(revised_payload, out_path)
    copy_path = DEFAULT_PLANS_DIR / f"revision-{stamp}.json"
    if copy_path != out_path:
        write_plan_payload(revised_payload, copy_path)
    print(f"Revised plan written: {out_path}")
    print(f"Revision copy written: {copy_path}")
    print_plan_summary(options)

    option = load_option(find_option(revised_payload, option_id))
    calendar_path = Path(args.calendar_ics) if args.calendar_ics else Path(f".studyflow/revised-plan-{stamp}.ics")
    calendar_path = write_option_ics(option, calendar_path, batch_label=batch_label)
    print(f"Revision Calendar ICS written: {calendar_path}")

    if not args.no_open:
        if not args.keep_old_calendar:
            deleted = delete_future_studyflow_events(lookahead_days=args.replace_calendar_days)
            print(f"Deleted old future StudyFlow calendar events: {deleted}")
        else:
            print("Kept old future StudyFlow calendar events.")
        open_target(str(calendar_path))
        if args.open_claude:
            open_claude()


def cmd_app(args: argparse.Namespace) -> None:
    launcher = Path(__file__).resolve().parent.parent / "scripts" / "studyflow_mac_launcher.sh"
    raise SystemExit(subprocess.run([str(launcher)], check=False).returncode)


def cmd_doctor(args: argparse.Namespace) -> None:
    env_file = Path(".env")
    print(f"Working directory: {Path.cwd()}")
    print(f".env: {'found' if env_file.exists() else 'missing'} ({env_file.resolve()})")

    client = ClaudeClient()
    if not client.api_key:
        print("ANTHROPIC_API_KEY: missing")
    elif is_placeholder_api_key(client.api_key):
        print("ANTHROPIC_API_KEY: placeholder or incomplete")
    else:
        print(f"ANTHROPIC_API_KEY: looks set (length {len(client.api_key)})")
    print(f"CLAUDE_MODEL: {client.model or 'missing'}")

    if DEFAULT_BUSY_PATH.exists():
        print(f"Default WEMUST calendar: found ({DEFAULT_BUSY_PATH})")
    else:
        print(f"Default WEMUST calendar: missing ({DEFAULT_BUSY_PATH})")

    vault = env_path("OBSIDIAN_VAULT", DEFAULT_OBSIDIAN_VAULT)
    print(f"Obsidian vault: {'found' if vault.exists() else 'missing'} ({vault})")

    blog_dir = env_path("BLOG_SITE_DIR", Path(""))
    if str(blog_dir):
        print(f"Blog site dir: {'found' if blog_dir.exists() else 'missing'} ({blog_dir})")

    if args.claude:
        try:
            text = client.complete("Reply with exactly: OK", max_tokens=8)
        except (ClaudeConfigError, ClaudeAPIError) as exc:
            raise SystemExit(str(exc)) from exc
        print(f"Claude API: ok ({text.strip() or 'empty response'})")


def build_goal(args: argparse.Namespace) -> Goal:
    return Goal(
        title=args.goal,
        description=args.description,
        deadline=parse_dt(args.deadline),
        success_criteria=[
            "能说清核心概念和工程用途",
            "能产出可复用的 Obsidian 笔记",
            "能通过问题清单检验理解",
        ],
    )


def generate_plan_payload(
    goal: Goal,
    start,
    busy_paths: List[str],
    use_claude: bool,
    risk_multiplier: float,
    working_day_start: str,
    working_day_end: str,
    allow_overflow: bool = False,
) -> tuple[Dict[str, Any], List[ScheduleOption]]:
    tasks = get_tasks(goal, use_claude=use_claude)
    busy_slots = read_busy_slots(busy_paths)

    history_path = Path(".studyflow/history.csv")
    effective_risk_multiplier = risk_multiplier or estimate_personal_multiplier(history_path)
    planner = SchedulePlanner(
        working_day_start=working_day_start,
        working_day_end=working_day_end,
        risk_multiplier=effective_risk_multiplier,
        allow_overflow=allow_overflow,
    )
    options = planner.generate_options(tasks, busy_slots, start=start, deadline=goal.deadline)

    payload = {
        "goal": to_jsonable(goal),
        "tasks": to_jsonable(tasks),
        "busy_slots": to_jsonable(busy_slots),
        "risk_multiplier": effective_risk_multiplier,
        "allow_overflow": allow_overflow,
        "schedule_preferences": {
            "working_day_start": working_day_start,
            "working_day_end": working_day_end,
        },
        "options": to_jsonable(options),
    }
    return payload, options


def write_plan_payload(payload: Dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_busy_paths(paths: List[str]) -> List[str]:
    if paths:
        return paths
    configured = os.environ.get("STUDYFLOW_BUSY")
    if configured:
        return [configured]
    if DEFAULT_BUSY_PATH.exists():
        return [str(DEFAULT_BUSY_PATH)]
    return []


def open_target(target: str) -> None:
    subprocess.run(["open", target], check=False)


def open_claude() -> None:
    result = subprocess.run(["open", "-a", "Claude"], check=False, capture_output=True)
    if result.returncode != 0:
        open_target("https://claude.ai/new")


def get_tasks(goal: Goal, use_claude: bool) -> List[TaskBlock]:
    if not use_claude:
        return fallback_decompose(goal)

    client = ClaudeClient()
    try:
        return decompose_goal_with_claude(client, goal)
    except (ClaudeConfigError, ClaudeAPIError, ClaudeResponseError) as exc:
        raise SystemExit(str(exc)) from exc


def cmd_commit(args: argparse.Namespace) -> None:
    payload = read_plan(Path(args.plan))
    goal = load_goal(payload["goal"])
    tasks = tasks_from_dicts(payload["tasks"])
    option = load_option(find_option(payload, args.option))

    if args.calendar_ics:
        path = write_option_ics(option, Path(args.calendar_ics))
        print(f"Calendar ICS written: {path}")

    if args.write_obsidian:
        vault = env_path("OBSIDIAN_VAULT", Path(args.obsidian_vault))
        note_path = write_goal_note(goal, tasks, option, vault, folder=args.obsidian_folder)
        print(f"Obsidian note written: {note_path}")
        print(f"Obsidian URI: {build_obsidian_uri(vault, note_path)}")

    if not args.calendar_ics and not args.write_obsidian:
        print("Nothing exported. Add --calendar-ics and/or --write-obsidian.")


def cmd_export_blog(args: argparse.Namespace) -> None:
    payload = read_plan(Path(args.plan))
    goal = load_goal(payload["goal"])
    tasks = tasks_from_dicts(payload["tasks"])
    option = load_option(find_option(payload, args.option))
    output_dir = resolve_blog_output_dir(args)
    path = write_blog_draft(goal, tasks, option, output_dir, blog_format=args.format)
    print(f"Blog draft written: {path}")


def resolve_blog_output_dir(args: argparse.Namespace) -> Path:
    if args.site_dir:
        return Path(args.site_dir)
    if args.out:
        return Path(args.out)
    if os.environ.get("BLOG_SITE_DIR"):
        return env_path("BLOG_SITE_DIR", Path(""))
    raise SystemExit("Set --out, --site-dir, or BLOG_SITE_DIR in .env.")


def cmd_show_calendar(args: argparse.Namespace) -> None:
    slots = read_busy_slots(args.paths)
    for slot in sorted(slots, key=lambda item: item.start):
        print(f"{slot.start:%Y-%m-%d %H:%M}-{slot.end:%H:%M}  {slot.title}  [{slot.source}]")


def cmd_record(args: argparse.Namespace) -> None:
    append_record(
        Path(args.history),
        task_id=args.task_id,
        planned_minutes=args.planned_minutes,
        actual_minutes=args.actual_minutes,
        status=args.status,
        note=args.note,
    )
    print(f"Record appended: {args.history}")


def read_plan(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def revision_history_from_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    history = payload.get("revision_history")
    if isinstance(history, list):
        return [item for item in history if isinstance(item, dict)]
    revision = payload.get("revision")
    if isinstance(revision, dict):
        return [revision]
    return []


def schedule_preferences_from_payload(payload: Dict[str, Any]) -> Dict[str, str]:
    preferences = payload.get("schedule_preferences")
    if isinstance(preferences, dict):
        return {
            "working_day_start": str(preferences.get("working_day_start") or "").strip(),
            "working_day_end": str(preferences.get("working_day_end") or "").strip(),
        }
    return {}


def load_goal(item: Dict[str, Any]) -> Goal:
    return Goal(
        title=item["title"],
        description=item.get("description", ""),
        deadline=parse_dt(item["deadline"]),
        success_criteria=list(item.get("success_criteria") or []),
        created_at=parse_dt(item["created_at"]),
    )


def find_option(payload: Dict[str, Any], option_id: str) -> Dict[str, Any]:
    for option in payload.get("options", []):
        if option.get("id") == option_id:
            return option
    available = ", ".join(option.get("id", "") for option in payload.get("options", []))
    raise SystemExit(f"Option not found: {option_id}. Available: {available}")


def load_option(item: Dict[str, Any]) -> ScheduleOption:
    sessions = [
        ScheduledSession(
            task_id=session["task_id"],
            title=session["title"],
            start=parse_dt(session["start"]),
            end=parse_dt(session["end"]),
            option_id=session["option_id"],
            sequence=int(session["sequence"]),
            resources=list(session.get("resources") or []),
            prompt=session.get("prompt", ""),
        )
        for session in item.get("sessions", [])
    ]
    return ScheduleOption(
        id=item["id"],
        label=item["label"],
        strategy=item["strategy"],
        sessions=sessions,
        warnings=list(item.get("warnings") or []),
    )


def parse_dt_now_minute():
    from datetime import datetime

    now = datetime.now()
    return now.replace(second=0, microsecond=0)


def print_plan_summary(options: List[ScheduleOption]) -> None:
    terminal_width = shutil.get_terminal_size((100, 24)).columns
    line = "-" * min(terminal_width, 100)
    for option in options:
        print(line)
        print(f"{option.id}: {option.label}")
        print(f"Scheduled minutes: {option.scheduled_minutes}")
        if option.warnings:
            print("Warnings:")
            for warning in option.warnings:
                print(f"  - {warning}")
        for session in option.sessions:
            print(
                f"  {session.sequence:02d}. {session.start:%Y-%m-%d %H:%M}-{session.end:%H:%M} "
                f"{session.title}"
            )
