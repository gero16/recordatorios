"""Programación de recordatorios por intervalo o a una hora fija."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ReminderScheduler:
    """Ejecuta callbacks en segundo plano según los recordatorios activos."""

    def __init__(self, on_fire: Callable[[dict[str, Any]], None]) -> None:
        self._on_fire = on_fire
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._reminders: list[dict[str, Any]] = []
        # id -> datetime de la próxima ejecución
        self._next_run: dict[str, datetime] = {}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None

    def update_reminders(
        self,
        reminders: list[dict[str, Any]],
        *,
        reset_ids: set[str] | None = None,
    ) -> None:
        with self._lock:
            self._reminders = [dict(r) for r in reminders]
            active_ids = {r["id"] for r in self._reminders if r.get("enabled")}
            # Quitar próximas ejecuciones de avisos eliminados o desactivados
            for rid in list(self._next_run):
                if rid not in active_ids:
                    del self._next_run[rid]
            if reset_ids:
                for rid in reset_ids:
                    self._next_run.pop(rid, None)
            now = datetime.now()
            for reminder in self._reminders:
                if not reminder.get("enabled"):
                    continue
                rid = reminder["id"]
                if rid not in self._next_run:
                    self._next_run[rid] = self._compute_next(reminder, now)

    def _compute_next(self, reminder: dict[str, Any], after: datetime) -> datetime:
        kind = reminder.get("kind")
        if kind == "interval":
            minutes = max(1, int(reminder.get("interval_minutes") or 30))
            return after + timedelta(minutes=minutes)
        if kind == "daily":
            time_str = reminder.get("time") or "09:00"
            hour, minute = self._parse_hhmm(time_str)
            candidate = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate <= after:
                candidate += timedelta(days=1)
            return candidate
        # Desconocido: no disparar pronto
        return after + timedelta(days=3650)

    @staticmethod
    def _parse_hhmm(value: str) -> tuple[int, int]:
        parts = value.strip().split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"Hora inválida: {value}")
        return hour, minute

    def _loop(self) -> None:
        while not self._stop.is_set():
            now = datetime.now()
            due: list[dict[str, Any]] = []
            with self._lock:
                for reminder in self._reminders:
                    if not reminder.get("enabled"):
                        continue
                    rid = reminder["id"]
                    next_at = self._next_run.get(rid)
                    if next_at is None:
                        self._next_run[rid] = self._compute_next(reminder, now)
                        continue
                    if next_at <= now:
                        due.append(dict(reminder))
                        # Programar la siguiente inmediatamente después de disparar
                        self._next_run[rid] = self._compute_next(reminder, now)

            for reminder in due:
                try:
                    self._on_fire(reminder)
                except Exception:  # noqa: BLE001
                    logger.exception("Error al disparar recordatorio %s", reminder.get("id"))

            self._stop.wait(1.0)

    def seconds_until_next(self, reminder_id: str) -> float | None:
        with self._lock:
            next_at = self._next_run.get(reminder_id)
        if next_at is None:
            return None
        return max(0.0, (next_at - datetime.now()).total_seconds())
