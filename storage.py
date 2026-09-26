"""Persistencia de recordatorios en JSON."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from scheduler import parse_hhmm

DATA_DIR = Path(__file__).resolve().parent / "data"
REMINDERS_FILE = DATA_DIR / "reminders.json"


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_reminders() -> list[dict[str, Any]]:
    _ensure_data_dir()
    if not REMINDERS_FILE.exists():
        return []
    try:
        with REMINDERS_FILE.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return []


def save_reminders(reminders: list[dict[str, Any]]) -> None:
    _ensure_data_dir()
    with REMINDERS_FILE.open("w", encoding="utf-8") as fh:
        json.dump(reminders, fh, ensure_ascii=False, indent=2)


def _normalize_days(days: list[int] | None) -> list[int]:
    if not days:
        raise ValueError("Elige al menos un día.")
    normalized = sorted({int(day) for day in days})
    if any(day < 0 or day > 6 for day in normalized):
        raise ValueError("Hay un día que no es válido.")
    return normalized


def _normalize_times(times: list[str] | None) -> list[str]:
    if not times:
        raise ValueError("Agrega al menos una hora.")
    normalized: list[str] = []
    for value in times:
        hour, minute = parse_hhmm(str(value))
        stamp = f"{hour:02d}:{minute:02d}"
        if stamp not in normalized:
            normalized.append(stamp)
    if not normalized:
        raise ValueError("Agrega al menos una hora.")
    if len(normalized) > 24:
        raise ValueError("Puedes agregar hasta 24 horas.")
    normalized.sort()
    return normalized


def create_reminder(
    message: str,
    kind: str,
    *,
    interval_minutes: int | None = None,
    time_hhmm: str | None = None,
    days: list[int] | None = None,
    times: list[str] | None = None,
    enabled: bool = True,
    reminder_id: str | None = None,
) -> dict[str, Any]:
    reminder: dict[str, Any] = {
        "id": reminder_id or str(uuid.uuid4()),
        "message": message.strip(),
        "kind": kind,  # "interval" | "daily" | "weekly"
        "enabled": enabled,
    }
    if kind == "interval":
        reminder["interval_minutes"] = int(interval_minutes or 30)
    elif kind == "daily":
        hour, minute = parse_hhmm(time_hhmm or "09:00")
        reminder["time"] = f"{hour:02d}:{minute:02d}"
    elif kind == "weekly":
        # days: 0 = lunes … 6 = domingo. times: varias horas en esos días.
        reminder["days"] = _normalize_days(days)
        reminder["times"] = _normalize_times(times)
    else:
        raise ValueError(f"Tipo de recordatorio no válido: {kind}")
    return reminder


def upsert_reminder(reminders: list[dict[str, Any]], reminder: dict[str, Any]) -> list[dict[str, Any]]:
    updated = False
    for idx, item in enumerate(reminders):
        if item.get("id") == reminder.get("id"):
            reminders[idx] = reminder
            updated = True
            break
    if not updated:
        reminders.append(reminder)
    save_reminders(reminders)
    return reminders


def delete_reminder(reminders: list[dict[str, Any]], reminder_id: str) -> list[dict[str, Any]]:
    reminders = [r for r in reminders if r.get("id") != reminder_id]
    save_reminders(reminders)
    return reminders


def set_enabled(
    reminders: list[dict[str, Any]], reminder_id: str, enabled: bool
) -> list[dict[str, Any]]:
    for item in reminders:
        if item.get("id") == reminder_id:
            item["enabled"] = enabled
            break
    save_reminders(reminders)
    return reminders
