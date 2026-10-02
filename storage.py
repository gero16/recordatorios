"""Persistencia de recordatorios en JSON."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
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


def _normalize_schedule(schedule: dict[int, list[str]] | None) -> dict[str, list[str]]:
    if not schedule:
        raise ValueError("Elige al menos un día y una hora.")
    normalized: dict[str, list[str]] = {}
    for raw_day, raw_times in schedule.items():
        try:
            day = int(raw_day)
        except (TypeError, ValueError) as exc:
            raise ValueError("Hay un día que no es válido.") from exc
        if day < 0 or day > 6:
            raise ValueError("Hay un día que no es válido.")
        times = _normalize_times(list(raw_times) if raw_times else None)
        normalized[str(day)] = times
    if not normalized:
        raise ValueError("Elige al menos un día y una hora.")
    return dict(sorted(normalized.items(), key=lambda item: int(item[0])))


def create_reminder(
    message: str,
    kind: str,
    *,
    interval_minutes: int | None = None,
    time_hhmm: str | None = None,
    days: list[int] | None = None,
    times: list[str] | None = None,
    schedule: dict[int, list[str]] | None = None,
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
        # schedule: día 0=lunes … 6=domingo, cada uno con sus horas.
        if schedule is not None:
            reminder["schedule"] = _normalize_schedule(schedule)
        else:
            shared = _normalize_times(times)
            reminder["schedule"] = {str(day): list(shared) for day in _normalize_days(days)}
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


def is_done_today(reminder: dict[str, Any], today: str | None = None) -> bool:
    stamp = today or datetime.now().strftime("%Y-%m-%d")
    return reminder.get("done_on") == stamp


def set_done_today(
    reminders: list[dict[str, Any]], reminder_id: str, done: bool, *, today: str | None = None
) -> list[dict[str, Any]]:
    """Marca o quita el hecho de hoy. Solo aplica a avisos diarios o de días concretos."""
    stamp = today or datetime.now().strftime("%Y-%m-%d")
    for item in reminders:
        if item.get("id") != reminder_id:
            continue
        if item.get("kind") not in ("daily", "weekly"):
            break
        if done:
            item["done_on"] = stamp
        elif item.get("done_on") == stamp:
            item.pop("done_on", None)
        break
    save_reminders(reminders)
    return reminders
