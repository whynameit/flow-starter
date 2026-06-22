from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import List


def append_record(
    path: Path,
    task_id: str,
    planned_minutes: int,
    actual_minutes: int,
    status: str,
    note: str = "",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["created_at", "task_id", "planned_minutes", "actual_minutes", "status", "note"],
        )
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "task_id": task_id,
                "planned_minutes": planned_minutes,
                "actual_minutes": actual_minutes,
                "status": status,
                "note": note,
            }
        )


def estimate_personal_multiplier(path: Path, default: float = 2.0) -> float:
    if not path.exists():
        return default
    ratios: List[float] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                planned = float(row.get("planned_minutes") or 0)
                actual = float(row.get("actual_minutes") or 0)
            except ValueError:
                continue
            if planned > 0 and actual > 0:
                ratios.append(actual / planned)
    if len(ratios) < 3:
        return default
    return max(default, min(4.0, median(ratios)))
