from __future__ import annotations

import csv
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .models import BusySlot, parse_dt

SHEET_NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

COURSE_HEADER_ALIASES = {
    "title": ["科目名稱", "科目名称", "課程名稱", "课程名称", "课程", "科目", "course", "subject"],
    "date": ["日期", "date"],
    "start": ["開始時間", "开始时间", "開始", "开始", "start"],
    "end": ["結束時間", "结束时间", "結束", "结束", "end"],
    "room": ["課室", "课室", "教室", "room", "classroom"],
    "teacher": ["教師", "教师", "teacher"],
    "code": ["科目編號", "科目编号", "課程編號", "课程编号", "code"],
    "class_name": ["班別名稱", "班别名称", "班別", "班别", "class"],
}


def read_busy_slots(paths: Iterable[str]) -> List[BusySlot]:
    slots: List[BusySlot] = []
    for raw_path in paths:
        path = Path(raw_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(path)
        suffix = path.suffix.lower()
        if suffix == ".csv":
            slots.extend(read_busy_slots_csv(path))
        elif suffix == ".ics":
            slots.extend(read_busy_slots_ics(path))
        elif suffix == ".xlsx":
            slots.extend(read_busy_slots_xlsx(path))
        else:
            raise ValueError(f"Unsupported calendar import format: {path}")
    return slots


def read_busy_slots_csv(path: Path) -> List[BusySlot]:
    slots: List[BusySlot] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if not row.get("start") or not row.get("end"):
                continue
            slots.append(
                BusySlot(
                    title=row.get("title") or "Busy",
                    start=parse_dt(row["start"]),
                    end=parse_dt(row["end"]),
                    source=row.get("source") or path.name,
                )
            )
    return slots


def read_busy_slots_ics(path: Path) -> List[BusySlot]:
    lines = unfold_ics_lines(path.read_text(encoding="utf-8", errors="replace").splitlines())
    events: List[Dict[str, str]] = []
    current: Dict[str, str] = {}
    in_event = False

    for line in lines:
        if line == "BEGIN:VEVENT":
            current = {}
            in_event = True
            continue
        if line == "END:VEVENT":
            if current:
                events.append(current)
            current = {}
            in_event = False
            continue
        if not in_event or ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.split(";", 1)[0].upper()
        current[key] = value

    slots: List[BusySlot] = []
    for event in events:
        if "DTSTART" not in event:
            continue
        start = parse_ics_datetime(event["DTSTART"])
        if "DTEND" in event:
            end = parse_ics_datetime(event["DTEND"])
        elif "DURATION" in event:
            end = start + parse_ics_duration(event["DURATION"])
        else:
            end = start + timedelta(hours=1)

        slots.append(
            BusySlot(
                title=event.get("SUMMARY") or "Busy",
                start=start,
                end=end,
                source=path.name,
            )
        )
    return slots


def read_busy_slots_xlsx(path: Path) -> List[BusySlot]:
    rows = read_xlsx_rows(path)
    slots: List[BusySlot] = []
    for sheet_name, sheet_rows in rows.items():
        slots.extend(parse_course_rows(sheet_rows, source=f"{path.name}:{sheet_name}"))
    return slots


def read_xlsx_rows(path: Path) -> Dict[str, List[List[str]]]:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        shared_strings = read_shared_strings(archive, names)
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = read_workbook_relationships(archive)

        result: Dict[str, List[List[str]]] = {}
        for sheet in workbook.findall("a:sheets/a:sheet", SHEET_NS):
            name = sheet.attrib.get("name", "Sheet")
            rel_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            if not rel_id or rel_id not in relationships:
                continue
            target = relationships[rel_id].lstrip("/")
            sheet_path = target if target.startswith("xl/") else f"xl/{target}"
            if sheet_path not in names:
                continue
            result[name] = read_worksheet_rows(archive, sheet_path, shared_strings)
        return result


def read_shared_strings(archive: zipfile.ZipFile, names: set[str]) -> List[str]:
    if "xl/sharedStrings.xml" not in names:
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    values: List[str] = []
    for item in root.findall("a:si", SHEET_NS):
        values.append("".join(text.text or "" for text in item.findall(".//a:t", SHEET_NS)))
    return values


def read_workbook_relationships(archive: zipfile.ZipFile) -> Dict[str, str]:
    root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    return {item.attrib["Id"]: item.attrib["Target"] for item in root}


def read_worksheet_rows(
    archive: zipfile.ZipFile,
    sheet_path: str,
    shared_strings: List[str],
) -> List[List[str]]:
    root = ET.fromstring(archive.read(sheet_path))
    rows: List[List[str]] = []
    for row in root.findall("a:sheetData/a:row", SHEET_NS):
        values_by_col: Dict[int, str] = {}
        for cell in row.findall("a:c", SHEET_NS):
            col = column_index(cell.attrib.get("r", "A1"))
            values_by_col[col] = read_cell_value(cell, shared_strings)
        if values_by_col:
            max_col = max(values_by_col)
            rows.append([values_by_col.get(index, "") for index in range(1, max_col + 1)])
    return rows


def read_cell_value(cell: ET.Element, shared_strings: List[str]) -> str:
    cell_type = cell.attrib.get("t", "")
    if cell_type == "inlineStr":
        return clean_text("".join(text.text or "" for text in cell.findall(".//a:t", SHEET_NS)))

    value = cell.find("a:v", SHEET_NS)
    if value is None:
        return ""

    raw = value.text or ""
    if cell_type == "s":
        try:
            return clean_text(shared_strings[int(raw)])
        except (ValueError, IndexError):
            return clean_text(raw)
    if cell_type == "b":
        return "TRUE" if raw == "1" else "FALSE"
    return clean_text(raw)


def column_index(cell_ref: str) -> int:
    letters = re.sub(r"[^A-Z]", "", cell_ref.upper())
    total = 0
    for letter in letters:
        total = total * 26 + (ord(letter) - ord("A") + 1)
    return total or 1


def clean_text(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower() == "null" else text


def parse_course_rows(rows: List[List[str]], source: str) -> List[BusySlot]:
    header_index, field_map = find_course_header(rows)
    if header_index is None:
        return []

    slots: List[BusySlot] = []
    for row in rows[header_index + 1 :]:
        record = row_to_record(row, field_map)
        try:
            slot = record_to_busy_slot(record, source)
        except ValueError:
            continue
        if slot:
            slots.append(slot)
    return slots


def find_course_header(rows: List[List[str]]) -> tuple[Optional[int], Dict[str, int]]:
    for index, row in enumerate(rows):
        normalized = [normalize_header(cell) for cell in row]
        field_map: Dict[str, int] = {}
        for field, aliases in COURSE_HEADER_ALIASES.items():
            alias_set = {normalize_header(alias) for alias in aliases}
            for col_index, cell in enumerate(normalized):
                if cell in alias_set:
                    field_map[field] = col_index
                    break
        required = {"title", "date", "start", "end"}
        if required.issubset(field_map):
            return index, field_map
    return None, {}


def normalize_header(value: str) -> str:
    return re.sub(r"\s+", "", clean_text(value).lower())


def row_to_record(row: List[str], field_map: Dict[str, int]) -> Dict[str, str]:
    record: Dict[str, str] = {}
    for field, index in field_map.items():
        record[field] = clean_text(row[index]) if index < len(row) else ""
    return record


def record_to_busy_slot(record: Dict[str, str], source: str) -> Optional[BusySlot]:
    title = record.get("title", "")
    if not title:
        return None

    class_date = parse_date_value(record.get("date", ""))
    start_time = parse_time_value(record.get("start", ""))
    end_time = parse_time_value(record.get("end", ""))
    start = datetime.combine(class_date, start_time)
    end = datetime.combine(class_date, end_time)
    if end <= start:
        end = end + timedelta(days=1)

    parts = [title]
    code = record.get("code", "")
    room = record.get("room", "")
    class_name = record.get("class_name", "")
    if code:
        parts.append(code)
    if class_name:
        parts.append(class_name)
    display_title = " ".join(parts)
    if room:
        display_title = f"{display_title} @ {room}"

    return BusySlot(title=display_title, start=start, end=end, source=source)


def parse_date_value(value: str) -> date:
    text = clean_text(value)
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass

    # Excel serial date, including the 1900 leap-year bug convention.
    try:
        serial = float(text)
    except ValueError as exc:
        raise ValueError(f"Unsupported date value: {value!r}") from exc
    return (datetime(1899, 12, 30) + timedelta(days=serial)).date()


def parse_time_value(value: str) -> time:
    text = clean_text(value)
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            pass
    try:
        number = float(text)
    except ValueError as exc:
        raise ValueError(f"Unsupported time value: {value!r}") from exc
    if 0 <= number < 1:
        minutes = int(round(number * 24 * 60))
        return time(hour=minutes // 60, minute=minutes % 60)
    raise ValueError(f"Unsupported time value: {value!r}")


def unfold_ics_lines(lines: Iterable[str]) -> List[str]:
    unfolded: List[str] = []
    for line in lines:
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line.strip())
    return unfolded


def parse_ics_datetime(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1]
    if len(text) == 8:
        return datetime.strptime(text, "%Y%m%d")
    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    raise ValueError(f"Unsupported ICS datetime: {value!r}")


def parse_ics_duration(value: str) -> timedelta:
    text = value.strip().upper()
    if not text.startswith("P"):
        raise ValueError(f"Unsupported ICS duration: {value!r}")
    days = hours = minutes = 0
    date_part, _, time_part = text[1:].partition("T")
    if date_part.endswith("D"):
        days = int(date_part[:-1])
    if "H" in time_part:
        hours_text, time_part = time_part.split("H", 1)
        hours = int(hours_text or 0)
    if "M" in time_part:
        minutes_text = time_part.split("M", 1)[0]
        minutes = int(minutes_text or 0)
    return timedelta(days=days, hours=hours, minutes=minutes)
