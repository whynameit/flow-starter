from __future__ import annotations

import math
import os
import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .calendar_export import display_title
from .models import ScheduleOption, ScheduledSession


DEFAULT_POMOFOCUS_APP = Path("/Users/rh/Applications/Chrome Apps.localized/Pomofocus.app")
DEFAULT_POMOFOCUS_TASKS = Path(".flow-starter/pomofocus-tasks.txt")
DEFAULT_POMOFOCUS_IMPORT = Path(".flow-starter/pomofocus-import.json")
POMOFOCUS_URL = "https://pomofocus.io/app"
IMPORT_RESULT_KEY = "flowStarterPomofocusImportResult"


@dataclass
class PomofocusImportResult:
    count: int
    target: str
    tasks_path: Path
    import_path: Path
    message: str = ""


class PomofocusImportError(RuntimeError):
    pass


def option_to_pomofocus_text(option: ScheduleOption, pomodoro_minutes: int = 25) -> str:
    lines = [session_to_pomofocus_line(session, pomodoro_minutes=pomodoro_minutes) for session in option.sessions]
    return "\n".join(lines).rstrip() + "\n"


def session_to_pomofocus_line(session: ScheduledSession, pomodoro_minutes: int = 25) -> str:
    title = display_title(session.title)
    count = pomodoro_count(session.minutes, pomodoro_minutes=pomodoro_minutes)
    return f"{title} ({session.minutes} 分钟 / {count} 个番茄)"


def pomodoro_count(minutes: int, pomodoro_minutes: int = 25) -> int:
    return max(1, math.ceil(max(1, minutes) / pomodoro_minutes))


def write_pomofocus_tasks(option: ScheduleOption, path: Path = DEFAULT_POMOFOCUS_TASKS) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(option_to_pomofocus_text(option), encoding="utf-8")
    return path


def option_to_pomofocus_tasks(option: ScheduleOption, pomodoro_minutes: int = 25) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for index, session in enumerate(option.sessions, start=1):
        count = pomodoro_count(session.minutes, pomodoro_minutes=pomodoro_minutes)
        tasks.append(
            {
                "id": f"flow-starter-{session.option_id}-{session.sequence}-{session.task_id}",
                "title": display_title(session.title),
                "minutes": session.minutes,
                "estPomodoro": count,
                "actPomodoro": 0,
                "done": 0,
                "note": f"{session.start:%Y-%m-%d %H:%M}-{session.end:%H:%M} · {session.minutes} 分钟",
                "projectName": "",
            }
        )
    return tasks


def write_pomofocus_import_json(
    option: ScheduleOption,
    path: Path = DEFAULT_POMOFOCUS_IMPORT,
    pomodoro_minutes: int = 25,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(option_to_pomofocus_tasks(option, pomodoro_minutes=pomodoro_minutes), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def import_option_to_pomofocus(
    option: ScheduleOption,
    app_path: str = "",
    tasks_path: Path = DEFAULT_POMOFOCUS_TASKS,
    import_path: Path = DEFAULT_POMOFOCUS_IMPORT,
) -> PomofocusImportResult:
    write_pomofocus_tasks(option, tasks_path)
    write_pomofocus_import_json(option, import_path)
    tasks = option_to_pomofocus_tasks(option)
    target = open_pomofocus(app_path)
    time.sleep(2.5)
    run_chrome_javascript(build_import_javascript(tasks))
    result = wait_for_import_result()
    if result.get("status") != "ok":
        raise PomofocusImportError(str(result.get("message") or "Pomofocus 任务导入失败。"))
    return PomofocusImportResult(
        count=int(result.get("count") or len(tasks)),
        target=target,
        tasks_path=tasks_path,
        import_path=import_path,
        message=str(result.get("message") or ""),
    )


def build_import_javascript(tasks: list[dict[str, Any]]) -> str:
    payload = json.dumps(tasks, ensure_ascii=False)
    result_key = json.dumps(IMPORT_RESULT_KEY)
    return f"""
(function() {{
  const tasks = {payload};
  const resultKey = {result_key};
  localStorage.setItem(resultKey, JSON.stringify({{ status: "started", count: tasks.length }}));

  const openDb = () => new Promise((resolve, reject) => {{
    const request = indexedDB.open("pomofocus", 23);
    request.onupgradeneeded = event => {{
      const db = event.target.result;
      if (!db.objectStoreNames.contains("config")) db.createObjectStore("config", {{ keyPath: "key" }});
      if (!db.objectStoreNames.contains("timerState")) db.createObjectStore("timerState", {{ keyPath: "key" }});
      if (!db.objectStoreNames.contains("activity")) db.createObjectStore("activity", {{ keyPath: "id" }});
    }};
    request.onerror = () => reject(request.error || new Error("无法打开 Pomofocus 数据库"));
    request.onsuccess = () => resolve(request.result);
  }});

  const waitTransaction = tx => new Promise((resolve, reject) => {{
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error || new Error("Pomofocus 任务写入失败"));
    tx.onabort = () => reject(tx.error || new Error("Pomofocus 任务写入中断"));
  }});

  openDb()
    .then(db => new Promise((resolve, reject) => {{
      const tx = db.transaction("activity", "readwrite");
      const store = tx.objectStore("activity");
      const request = store.getAll();
      request.onerror = () => reject(request.error || new Error("无法读取现有 Pomofocus 任务"));
      request.onsuccess = () => {{
        const existing = request.result || [];
        existing.forEach(item => {{
          if (String(item.id || "").startsWith("flow-starter-")) {{
            store.delete(item.id);
          }}
        }});
        const keptExisting = existing.filter(item => !String(item.id || "").startsWith("flow-starter-"));
        const maxOrder = keptExisting.reduce((max, item) => {{
          const order = Number(item.order);
          return Number.isFinite(order) ? Math.max(max, order) : max;
        }}, -1);
        const stamp = Date.now();
        tasks.forEach((task, index) => {{
          store.put({{
            id: task.id || `flow-starter-${{stamp}}-${{index + 1}}`,
            title: task.title,
            estPomodoro: task.estPomodoro,
            actPomodoro: task.actPomodoro || 0,
            done: task.done || 0,
            note: task.note || "",
            projectName: task.projectName || "",
            order: maxOrder + index + 1,
            apiTaskId: "",
            stashed: false
          }});
        }});
        waitTransaction(tx).then(resolve).catch(reject);
      }};
    }}))
    .then(() => {{
      localStorage.setItem(resultKey, JSON.stringify({{ status: "ok", count: tasks.length }}));
      window.location.reload();
    }})
    .catch(error => {{
      localStorage.setItem(resultKey, JSON.stringify({{
        status: "error",
        message: error && error.message ? error.message : String(error)
      }}));
    }});
  return "flow-starter Pomofocus import started";
}})();
""".strip()


def run_chrome_javascript(script: str) -> str:
    result = subprocess.run(
        [
            "osascript",
            "-e",
            'on run argv',
            "-e",
            'set jsCode to item 1 of argv',
            "-e",
            'tell application "Google Chrome"',
            "-e",
            'repeat with wi from 1 to count of windows',
            "-e",
            'repeat with ti from 1 to count of tabs of window wi',
            "-e",
            'if (URL of tab ti of window wi as text) starts with "https://pomofocus.io/app" then',
            "-e",
            'set active tab index of window wi to ti',
            "-e",
            'return execute active tab of window wi javascript (jsCode as text)',
            "-e",
            'end if',
            "-e",
            'end repeat',
            "-e",
            'end repeat',
            "-e",
            'end tell',
            "-e",
            'return "NO_POMOFOCUS_TAB"',
            "-e",
            'end run',
            script,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PomofocusImportError(simplify_chrome_error(result.stderr or result.stdout))
    output = result.stdout.strip()
    if output == "NO_POMOFOCUS_TAB":
        raise PomofocusImportError("没有找到 Pomofocus 页面。请先打开 Pomofocus 后再试。")
    return output


def wait_for_import_result(timeout_seconds: float = 8.0) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        time.sleep(0.5)
        try:
            raw = run_chrome_javascript(f"localStorage.getItem({json.dumps(IMPORT_RESULT_KEY)})")
        except PomofocusImportError as exc:
            last_error = str(exc)
            continue
        if not raw:
            continue
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if result.get("status") in {"ok", "error"}:
            return result
    return {"status": "error", "message": last_error or "等待 Pomofocus 导入结果超时。"}


def simplify_chrome_error(text: str) -> str:
    if "通过 AppleScript 执行 JavaScript 的功能已关闭" in text or "Allow JavaScript from Apple Events" in text:
        return "Chrome 关闭了 Apple 事件 JavaScript。请在 Chrome 菜单“查看 > 开发者 > 允许 Apple 事件中的 JavaScript”打开一次。"
    return (text.strip() or "Pomofocus 自动导入失败。")[:200]


def copy_to_clipboard(text: str) -> bool:
    try:
        result = subprocess.run(["pbcopy"], input=text, text=True, check=False, capture_output=True)
    except OSError:
        return False
    return result.returncode == 0


def find_pomofocus_app(configured_path: str = "") -> Path | None:
    candidates = list(candidate_app_paths(configured_path))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def candidate_app_paths(configured_path: str = "") -> Iterable[Path]:
    configured = configured_path or os.environ.get("FLOW_STARTER_POMOFOCUS_APP") or os.environ.get("POMOFOCUS_APP") or ""
    if configured:
        yield from app_path_variants(Path(configured).expanduser())

    home = Path.home()
    yield DEFAULT_POMOFOCUS_APP
    yield home / "Applications" / "Chrome Apps.localized" / "Pomofocus.app"
    yield home / "Applications" / "Chrome Apps.localized" / "pomofocus.app"
    yield Path("/Applications/Pomofocus.app")
    yield Path("/Applications/pomofocus.app")


def app_path_variants(path: Path) -> Iterable[Path]:
    yield path
    if path.suffix != ".app":
        yield Path(f"{path}.app")
        if path.name.lower() == "pomofocus":
            yield path.with_name("Pomofocus.app")


def open_pomofocus(configured_path: str = "") -> str:
    app = find_pomofocus_app(configured_path)
    target = str(app) if app else POMOFOCUS_URL
    subprocess.run(["open", target], check=False)
    return target
