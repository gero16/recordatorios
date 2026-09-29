"""Aplicación de escritorio: recordatorios con notificaciones en Windows."""

from __future__ import annotations

import logging
import sys
import tkinter as tk
from datetime import datetime
from tkinter import messagebox
from typing import Any

import customtkinter as ctk

from notifier import dismiss_notifications, show_notification
from phone import load_phone_config, send_phone_notification, update_phone_settings
from scheduler import ReminderScheduler, parse_hhmm
from single_instance import SingleInstanceGuard
from storage import (
    create_reminder,
    delete_reminder,
    is_done_today,
    load_reminders,
    save_reminders,
    set_done_today,
    set_enabled,
    upsert_reminder,
)
from tray import TrayIcon

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

APP_TITLE = "Recordatorios"
ACCENT = "#2563EB"

# Tipografía más legible
FONT_HERO = 30
FONT_SECTION = 20
FONT_BODY = 16
FONT_LABEL = 15
FONT_BUTTON = 15
FONT_CARD_TITLE = 17
FONT_CARD_META = 14
ENTRY_HEIGHT = 42
BTN_HEIGHT = 40
CARD_BTN_HEIGHT = 34
WEEKDAYS = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
WEEKDAY_LONG = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)
NEXT_NOTICE_INTERVAL_MS = 15_000
PAUSED_COLOR = "#64748B"
DONE_COLOR = "#15803D"
PENDING_COLOR = "#B45309"


def format_reminder_detail(reminder: dict[str, Any]) -> str:
    kind = reminder.get("kind")
    if kind == "interval":
        return f"Cada {reminder.get('interval_minutes', '?')} min"
    if kind == "weekly":
        days = []
        for raw in reminder.get("days") or []:
            try:
                day = int(raw)
            except (TypeError, ValueError):
                continue
            if 0 <= day <= 6 and day not in days:
                days.append(day)
        days.sort()
        times = reminder.get("times") or []
        if days == list(range(7)):
            day_text = "Todos los días"
        elif days == [0, 1, 2, 3, 4]:
            day_text = "Lunes a viernes"
        elif days == [5, 6]:
            day_text = "Sábado y domingo"
        elif days:
            day_text = ", ".join(WEEKDAYS[day] for day in days)
        else:
            day_text = "Sin días"
        time_text = ", ".join(str(item) for item in times) if times else "sin hora"
        return f"{day_text} · {time_text}"
    return f"Todos los días a las {reminder.get('time', '?')}"


def format_next_notice(next_at: datetime | None, now: datetime) -> str:
    """Texto del próximo aviso para un recordatorio activo."""
    if next_at is None:
        return "Próximo aviso: calculando…"
    if next_at <= now:
        return "Próximo aviso: en menos de 1 min"

    seconds = (next_at - now).total_seconds()
    if seconds < 45:
        return "Próximo aviso: en menos de 1 min"

    minutes = round(seconds / 60)
    if minutes < 60:
        return f"Próximo aviso: en {max(1, minutes)} min"

    stamp = next_at.strftime("%H:%M")
    day_delta = (next_at.date() - now.date()).days
    if day_delta <= 0:
        when = f"hoy a las {stamp}"
    elif day_delta == 1:
        when = f"mañana a las {stamp}"
    elif day_delta < 7:
        when = f"el {WEEKDAY_LONG[next_at.weekday()]} a las {stamp}"
    elif next_at.year != now.year:
        when = f"el {next_at.strftime('%d/%m/%Y')} a las {stamp}"
    else:
        when = f"el {next_at.strftime('%d/%m')} a las {stamp}"
    return f"Próximo aviso: {when}"


def supports_done(reminder: dict[str, Any]) -> bool:
    return reminder.get("kind") in ("daily", "weekly")


def is_scheduled_today(reminder: dict[str, Any], now: datetime) -> bool:
    """El aviso de hoy se puede marcar hecho si hoy es uno de sus días."""
    kind = reminder.get("kind")
    if kind == "daily":
        return True
    if kind != "weekly":
        return False
    for raw in reminder.get("days") or []:
        try:
            day = int(raw)
        except (TypeError, ValueError):
            continue
        if day == now.weekday():
            return True
    return False


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.title(APP_TITLE)
        self.geometry("980x920")
        self.minsize(920, 820)

        self.reminders: list[dict[str, Any]] = load_reminders()
        self._quitting = False
        self._editing_id: str | None = None
        self._selected_days: set[int] = {0, 1, 2, 3, 4}
        self._times: list[str] = ["09:00"]
        self._day_buttons: list[ctk.CTkButton] = []
        self._next_labels: dict[str, ctk.CTkLabel] = {}
        self._next_notice_job: str | None = None

        self.scheduler = ReminderScheduler(on_fire=self._on_reminder_fire)
        self.tray = TrayIcon(on_show=self._show_from_tray, on_quit=self._quit_app)
        self._instance_guard: SingleInstanceGuard | None = None

        self._build_ui()

        self.protocol("WM_DELETE_WINDOW", self._hide_to_tray)
        self.bind("<Unmap>", self._on_unmap)

        self.scheduler.update_reminders(self.reminders)
        self._refresh_list()
        self._schedule_next_notice_refresh()
        self.scheduler.start()
        self.tray.start()

    # ----- UI -----

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 10))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text=APP_TITLE,
            font=ctk.CTkFont(size=FONT_HERO, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text="Al cerrar o minimizar, la app sigue en la bandeja del sistema.",
            text_color="#64748B",
            font=ctk.CTkFont(size=FONT_BODY),
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=24, pady=8)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        form = ctk.CTkFrame(body)
        form.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        form.grid_columnconfigure(0, weight=1)

        self.form_title = ctk.CTkLabel(
            form, text="Nuevo recordatorio", font=ctk.CTkFont(size=FONT_SECTION, weight="bold")
        )
        self.form_title.grid(row=0, column=0, sticky="w", padx=16, pady=(12, 14))

        ctk.CTkLabel(
            form, text="Mensaje", font=ctk.CTkFont(size=FONT_LABEL, weight="bold")
        ).grid(row=1, column=0, sticky="w", padx=16)
        self.message_entry = ctk.CTkEntry(
            form,
            placeholder_text="Ej: Beber agua",
            height=ENTRY_HEIGHT,
            font=ctk.CTkFont(size=FONT_BODY),
        )
        self.message_entry.grid(row=2, column=0, sticky="ew", padx=16, pady=(6, 16))

        ctk.CTkLabel(
            form, text="Tipo", font=ctk.CTkFont(size=FONT_LABEL, weight="bold")
        ).grid(row=3, column=0, sticky="w", padx=16)
        self.kind_var = tk.StringVar(value="interval")
        kind_row = ctk.CTkFrame(form, fg_color="transparent")
        kind_row.grid(row=4, column=0, sticky="ew", padx=16, pady=(8, 12))
        for label, value in (
            ("Cada cierto tiempo", "interval"),
            ("Todos los días a una hora", "daily"),
            ("Ciertos días y horas", "weekly"),
        ):
            ctk.CTkRadioButton(
                kind_row,
                text=label,
                variable=self.kind_var,
                value=value,
                command=self._sync_kind_fields,
                font=ctk.CTkFont(size=FONT_BODY),
            ).pack(anchor="w", pady=3)

        self.interval_frame = ctk.CTkFrame(form, fg_color="transparent")
        self.interval_frame.grid(row=5, column=0, sticky="ew", padx=16, pady=(4, 10))
        self.interval_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self.interval_frame,
            text="Intervalo (minutos)",
            font=ctk.CTkFont(size=FONT_LABEL, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        self.interval_entry = ctk.CTkEntry(
            self.interval_frame,
            placeholder_text="30",
            height=ENTRY_HEIGHT,
            font=ctk.CTkFont(size=FONT_BODY),
        )
        self.interval_entry.insert(0, "30")
        self.interval_entry.grid(row=1, column=0, sticky="ew", pady=(6, 0))

        self.time_frame = ctk.CTkFrame(form, fg_color="transparent")
        self.time_frame.grid(row=6, column=0, sticky="ew", padx=16, pady=(4, 10))
        self.time_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self.time_frame,
            text="Hora (HH:MM, 24 h)",
            font=ctk.CTkFont(size=FONT_LABEL, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        self.time_entry = ctk.CTkEntry(
            self.time_frame,
            placeholder_text="15:00",
            height=ENTRY_HEIGHT,
            font=ctk.CTkFont(size=FONT_BODY),
        )
        self.time_entry.insert(0, "15:00")
        self.time_entry.grid(row=1, column=0, sticky="ew", pady=(6, 0))

        self.weekly_frame = ctk.CTkFrame(form, fg_color="transparent")
        self.weekly_frame.grid(row=7, column=0, sticky="ew", padx=16, pady=(4, 10))
        self.weekly_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.weekly_frame,
            text="Suena en los días marcados, a cada hora de la lista.",
            text_color="#64748B",
            font=ctk.CTkFont(size=FONT_CARD_META),
            wraplength=320,
            justify="left",
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(
            self.weekly_frame,
            text="Días",
            font=ctk.CTkFont(size=FONT_LABEL, weight="bold"),
        ).grid(row=1, column=0, sticky="w")

        days_row = ctk.CTkFrame(self.weekly_frame, fg_color="transparent")
        days_row.grid(row=2, column=0, sticky="ew", pady=(6, 4))
        for index in range(7):
            days_row.grid_columnconfigure(index, weight=1)
            button = ctk.CTkButton(
                days_row,
                text=WEEKDAYS[index],
                width=52,
                height=34,
                font=ctk.CTkFont(size=13, weight="bold"),
                command=lambda day=index: self._toggle_day(day),
            )
            button.grid(row=0, column=index, padx=2, sticky="ew")
            self._day_buttons.append(button)

        presets = ctk.CTkFrame(self.weekly_frame, fg_color="transparent")
        presets.grid(row=3, column=0, sticky="w", pady=(2, 10))
        for label, days in (
            ("Lu a Vi", {0, 1, 2, 3, 4}),
            ("Fin de semana", {5, 6}),
            ("Todos", set(range(7))),
        ):
            ctk.CTkButton(
                presets,
                text=label,
                height=30,
                font=ctk.CTkFont(size=13),
                fg_color="#E2E8F0",
                hover_color="#CBD5E1",
                text_color="#334155",
                command=lambda selected=days: self._set_days(selected),
            ).pack(side="left", padx=(0, 6))

        ctk.CTkLabel(
            self.weekly_frame,
            text="Horas",
            font=ctk.CTkFont(size=FONT_LABEL, weight="bold"),
        ).grid(row=4, column=0, sticky="w", pady=(4, 0))

        add_row = ctk.CTkFrame(self.weekly_frame, fg_color="transparent")
        add_row.grid(row=5, column=0, sticky="ew", pady=(6, 4))
        add_row.grid_columnconfigure(0, weight=1)
        self.weekly_time_entry = ctk.CTkEntry(
            add_row,
            placeholder_text="09:00 o 09:00, 18:30",
            height=ENTRY_HEIGHT,
            font=ctk.CTkFont(size=FONT_BODY),
        )
        self.weekly_time_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.weekly_time_entry.bind("<Return>", lambda _event: self._add_time_clicked())
        ctk.CTkButton(
            add_row,
            text="Agregar",
            width=110,
            height=ENTRY_HEIGHT,
            font=ctk.CTkFont(size=FONT_BUTTON, weight="bold"),
            fg_color=ACCENT,
            hover_color="#1D4ED8",
            command=self._add_time_clicked,
        ).grid(row=0, column=1)

        self.times_chips = ctk.CTkFrame(self.weekly_frame, fg_color="transparent")
        self.times_chips.grid(row=6, column=0, sticky="ew", pady=(4, 8))
        self.times_chips.grid_columnconfigure((0, 1), weight=1)
        self._refresh_day_buttons()
        self._refresh_time_chips()

        form_actions = ctk.CTkFrame(form, fg_color="transparent")
        form_actions.grid(row=8, column=0, sticky="ew", padx=16, pady=(12, 18))
        form_actions.grid_columnconfigure(0, weight=1)

        self.save_btn = ctk.CTkButton(
            form_actions,
            text="Guardar recordatorio",
            fg_color=ACCENT,
            hover_color="#1D4ED8",
            height=BTN_HEIGHT,
            font=ctk.CTkFont(size=FONT_BUTTON, weight="bold"),
            command=self._save_reminder,
        )
        self.save_btn.grid(row=0, column=0, sticky="ew")

        self.cancel_edit_btn = ctk.CTkButton(
            form_actions,
            text="Cancelar edición",
            fg_color="#64748B",
            hover_color="#475569",
            height=BTN_HEIGHT,
            font=ctk.CTkFont(size=FONT_BUTTON),
            command=self._cancel_edit,
        )
        self.cancel_edit_btn.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.cancel_edit_btn.grid_remove()

        self._sync_kind_fields()

        # Lista
        list_panel = ctk.CTkFrame(body)
        list_panel.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        list_panel.grid_columnconfigure(0, weight=1)
        list_panel.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            list_panel, text="Activos", font=ctk.CTkFont(size=FONT_SECTION, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(20, 12))

        self.list_scroll = ctk.CTkScrollableFrame(list_panel)
        self.list_scroll.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 16))
        self.list_scroll.grid_columnconfigure(0, weight=1)

        phone_config = load_phone_config()
        phone_bar = ctk.CTkFrame(self, fg_color="transparent")
        phone_bar.grid(row=2, column=0, sticky="ew", padx=24, pady=(4, 0))
        phone_bar.grid_columnconfigure(1, weight=1)

        self.phone_enabled_var = tk.BooleanVar(value=bool(phone_config.get("enabled", True)))
        ctk.CTkCheckBox(
            phone_bar,
            text="Avisar al celular",
            variable=self.phone_enabled_var,
            command=self._save_phone_settings,
            font=ctk.CTkFont(size=FONT_BODY),
        ).grid(row=0, column=0, sticky="w")
        self.phone_topic_entry = ctk.CTkEntry(
            phone_bar,
            height=ENTRY_HEIGHT,
            font=ctk.CTkFont(size=FONT_CARD_META),
        )
        self.phone_topic_entry.insert(0, str(phone_config.get("topic") or ""))
        self.phone_topic_entry.grid(row=0, column=1, sticky="ew", padx=(12, 8))
        self.phone_topic_entry.bind("<FocusOut>", lambda _event: self._save_phone_settings())
        self.phone_topic_entry.bind("<Return>", lambda _event: self._save_phone_settings())
        self.copy_topic_btn = ctk.CTkButton(
            phone_bar,
            text="Copiar tema",
            width=130,
            height=ENTRY_HEIGHT,
            font=ctk.CTkFont(size=FONT_BUTTON),
            fg_color="#334155",
            hover_color="#1E293B",
            command=self._copy_phone_topic,
        )
        self.copy_topic_btn.grid(row=0, column=2, sticky="e")
        ctk.CTkLabel(
            phone_bar,
            text="En la app ntfy pulsa + y pega este tema. Quien lo conozca puede ver estos avisos.",
            text_color="#64748B",
            font=ctk.CTkFont(size=FONT_CARD_META),
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", padx=24, pady=(8, 20))
        ctk.CTkButton(
            footer,
            text="Probar notificación",
            width=200,
            height=BTN_HEIGHT,
            font=ctk.CTkFont(size=FONT_BUTTON),
            fg_color="#0F766E",
            hover_color="#0D9488",
            command=self._test_notification,
        ).pack(side="left")
        ctk.CTkButton(
            footer,
            text="Minimizar a bandeja",
            width=200,
            height=BTN_HEIGHT,
            font=ctk.CTkFont(size=FONT_BUTTON),
            fg_color="#475569",
            hover_color="#334155",
            command=self._hide_to_tray,
        ).pack(side="left", padx=(12, 0))

    def _sync_kind_fields(self) -> None:
        kind = self.kind_var.get()
        if kind == "interval":
            self.interval_frame.grid()
            self.time_frame.grid_remove()
            self.weekly_frame.grid_remove()
        elif kind == "weekly":
            self.interval_frame.grid_remove()
            self.time_frame.grid_remove()
            self.weekly_frame.grid()
        else:
            self.interval_frame.grid_remove()
            self.time_frame.grid()
            self.weekly_frame.grid_remove()

    def _toggle_day(self, day: int) -> None:
        if day in self._selected_days:
            self._selected_days.remove(day)
        else:
            self._selected_days.add(day)
        self._refresh_day_buttons()

    def _set_days(self, days: set[int]) -> None:
        self._selected_days = set(days)
        self._refresh_day_buttons()

    def _refresh_day_buttons(self) -> None:
        for day, button in enumerate(self._day_buttons):
            if day in self._selected_days:
                button.configure(fg_color=ACCENT, hover_color="#1D4ED8", text_color="white")
            else:
                button.configure(fg_color="#E2E8F0", hover_color="#CBD5E1", text_color="#334155")

    def _add_time_clicked(self) -> bool:
        return self._add_times_from_text(self.weekly_time_entry.get())

    def _add_times_from_text(self, raw: str) -> bool:
        cleaned = raw.replace(";", " ").replace(",", " ")
        tokens = [part for part in cleaned.split() if part]
        if not tokens:
            messagebox.showwarning(APP_TITLE, "Escribe una hora en formato HH:MM.")
            return False

        normalized: list[str] = []
        for token in tokens:
            try:
                hour, minute = parse_hhmm(token)
            except ValueError:
                messagebox.showerror(
                    APP_TITLE,
                    f"Hora inválida: {token}. Usa HH:MM, por ejemplo 09:30.",
                )
                return False
            stamp = f"{hour:02d}:{minute:02d}"
            if stamp not in normalized:
                normalized.append(stamp)

        for stamp in normalized:
            if stamp not in self._times:
                self._times.append(stamp)
        self._times.sort()
        self.weekly_time_entry.delete(0, "end")
        self._refresh_time_chips()
        return True

    def _remove_time(self, value: str) -> None:
        self._times = [item for item in self._times if item != value]
        self._refresh_time_chips()

    def _refresh_time_chips(self) -> None:
        for child in self.times_chips.winfo_children():
            child.destroy()

        if not self._times:
            ctk.CTkLabel(
                self.times_chips,
                text="Agrega al menos una hora.",
                text_color="#64748B",
                font=ctk.CTkFont(size=FONT_CARD_META),
                anchor="w",
            ).grid(row=0, column=0, columnspan=2, sticky="w", pady=4)
            return

        for index, stamp in enumerate(self._times):
            chip = ctk.CTkFrame(self.times_chips, fg_color="#E8EEF5", corner_radius=8)
            chip.grid(row=index // 2, column=index % 2, sticky="ew", padx=3, pady=3)
            ctk.CTkLabel(
                chip,
                text=stamp,
                font=ctk.CTkFont(size=FONT_BODY, weight="bold"),
            ).pack(side="left", padx=(10, 4), pady=4)
            ctk.CTkButton(
                chip,
                text="✕",
                width=28,
                height=28,
                fg_color="transparent",
                hover_color="#F1F5F9",
                text_color="#64748B",
                command=lambda value=stamp: self._remove_time(value),
            ).pack(side="right", padx=4, pady=4)

    def _next_notice_for(self, reminder: dict[str, Any]) -> tuple[str, str]:
        if not reminder.get("enabled", True):
            return "Pausado", PAUSED_COLOR
        reminder_id = reminder.get("id")
        next_at = self.scheduler.next_run_at(str(reminder_id)) if reminder_id else None
        return format_next_notice(next_at, datetime.now()), ACCENT

    def _refresh_next_notices(self) -> None:
        by_id = {str(item.get("id")): item for item in self.reminders}
        for reminder_id, label in list(self._next_labels.items()):
            reminder = by_id.get(reminder_id)
            if reminder is None:
                continue
            text, color = self._next_notice_for(reminder)
            try:
                label.configure(text=text, text_color=color)
            except tk.TclError:
                continue

    def _schedule_next_notice_refresh(self) -> None:
        if self._quitting:
            return
        self._next_notice_job = self.after(NEXT_NOTICE_INTERVAL_MS, self._on_next_notice_tick)

    def _on_next_notice_tick(self) -> None:
        if self._quitting:
            return
        self._refresh_next_notices()
        self._schedule_next_notice_refresh()

    def _refresh_list(self) -> None:
        self._next_labels = {}
        for child in self.list_scroll.winfo_children():
            child.destroy()

        if not self.reminders:
            ctk.CTkLabel(
                self.list_scroll,
                text="No hay recordatorios todavía.",
                text_color="#64748B",
                font=ctk.CTkFont(size=FONT_BODY),
            ).grid(row=0, column=0, sticky="w", padx=10, pady=12)
            return

        for idx, reminder in enumerate(self.reminders):
            card = ctk.CTkFrame(self.list_scroll)
            card.grid(row=idx, column=0, sticky="ew", padx=4, pady=8)
            card.grid_columnconfigure(0, weight=1)

            title = reminder.get("message") or "(sin mensaje)"
            detail = format_reminder_detail(reminder)
            notice, notice_color = self._next_notice_for(reminder)

            enabled = bool(reminder.get("enabled", True))

            ctk.CTkLabel(
                card,
                text=title,
                font=ctk.CTkFont(size=FONT_CARD_TITLE, weight="bold"),
                anchor="w",
            ).grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 0))
            ctk.CTkLabel(
                card,
                text=detail,
                text_color="#64748B",
                font=ctk.CTkFont(size=FONT_CARD_META),
                anchor="w",
                justify="left",
                wraplength=360,
            ).grid(row=1, column=0, sticky="ew", padx=14, pady=(4, 0))
            notice_label = ctk.CTkLabel(
                card,
                text=notice,
                text_color=notice_color,
                font=ctk.CTkFont(size=FONT_CARD_META, weight="bold"),
                anchor="w",
                justify="left",
                wraplength=360,
            )
            notice_label.grid(row=2, column=0, sticky="ew", padx=14, pady=(2, 6))
            reminder_id = reminder.get("id")
            if reminder_id:
                self._next_labels[str(reminder_id)] = notice_label

            action_row = 3
            if (
                reminder_id
                and supports_done(reminder)
                and is_scheduled_today(reminder, datetime.now())
            ):
                done_now = is_done_today(reminder)
                done_var = tk.BooleanVar(value=done_now)
                ctk.CTkCheckBox(
                    card,
                    text="Hecho hoy" if done_now else "Pendiente hoy",
                    variable=done_var,
                    command=lambda rid=str(reminder_id), var=done_var: self._on_done_checkbox(
                        rid, var
                    ),
                    font=ctk.CTkFont(size=FONT_CARD_META, weight="bold"),
                    text_color=DONE_COLOR if done_now else PENDING_COLOR,
                    fg_color=DONE_COLOR,
                    hover_color="#166534",
                ).grid(row=3, column=0, sticky="w", padx=14, pady=(0, 6))
                action_row = 4

            actions = ctk.CTkFrame(card, fg_color="transparent")
            actions.grid(row=action_row, column=0, sticky="ew", padx=10, pady=(0, 12))

            ctk.CTkButton(
                actions,
                text="Editar",
                width=96,
                height=CARD_BTN_HEIGHT,
                font=ctk.CTkFont(size=FONT_LABEL),
                fg_color="#475569",
                hover_color="#334155",
                command=lambda r=reminder: self._start_edit(r["id"]),
            ).pack(side="left", padx=4)

            toggle_text = "Pausar" if enabled else "Activar"
            ctk.CTkButton(
                actions,
                text=toggle_text,
                width=96,
                height=CARD_BTN_HEIGHT,
                font=ctk.CTkFont(size=FONT_LABEL),
                command=lambda r=reminder: self._toggle_reminder(r["id"]),
            ).pack(side="left", padx=4)
            ctk.CTkButton(
                actions,
                text="Eliminar",
                width=96,
                height=CARD_BTN_HEIGHT,
                font=ctk.CTkFont(size=FONT_LABEL),
                fg_color="#DC2626",
                hover_color="#B91C1C",
                command=lambda r=reminder: self._delete_reminder(r["id"]),
            ).pack(side="left", padx=4)

    # ----- Acciones -----

    def _set_form_mode(self, editing: bool) -> None:
        if editing:
            self.form_title.configure(text="Editar recordatorio")
            self.save_btn.configure(text="Guardar cambios")
            self.cancel_edit_btn.grid()
        else:
            self.form_title.configure(text="Nuevo recordatorio")
            self.save_btn.configure(text="Guardar recordatorio")
            self.cancel_edit_btn.grid_remove()

    def _clear_form(self, *, defaults: bool = True) -> None:
        self.message_entry.delete(0, "end")
        self.kind_var.set("interval")
        self.interval_entry.delete(0, "end")
        self.time_entry.delete(0, "end")
        self.weekly_time_entry.delete(0, "end")
        self._selected_days = {0, 1, 2, 3, 4}
        self._times = ["09:00"] if defaults else []
        if defaults:
            self.interval_entry.insert(0, "30")
            self.time_entry.insert(0, "15:00")
        self._refresh_day_buttons()
        self._refresh_time_chips()
        self._sync_kind_fields()

    def _start_edit(self, reminder_id: str) -> None:
        reminder = next((r for r in self.reminders if r.get("id") == reminder_id), None)
        if not reminder:
            return

        self._editing_id = reminder_id
        self._clear_form(defaults=False)

        self.message_entry.insert(0, reminder.get("message") or "")
        kind = reminder.get("kind") or "interval"
        if kind not in ("interval", "daily", "weekly"):
            kind = "interval"
        self.kind_var.set(kind)

        self.interval_entry.insert(
            0, str(reminder.get("interval_minutes") or 30) if kind == "interval" else "30"
        )
        self.time_entry.insert(0, reminder.get("time") or "15:00")

        if kind == "weekly":
            selected: set[int] = set()
            for raw in reminder.get("days") or []:
                try:
                    day = int(raw)
                except (TypeError, ValueError):
                    continue
                if 0 <= day <= 6:
                    selected.add(day)
            self._selected_days = selected
            loaded_times: list[str] = []
            for value in reminder.get("times") or []:
                try:
                    hour, minute = parse_hhmm(str(value))
                except ValueError:
                    continue
                stamp = f"{hour:02d}:{minute:02d}"
                if stamp not in loaded_times:
                    loaded_times.append(stamp)
            loaded_times.sort()
            self._times = loaded_times
        else:
            self._selected_days = {0, 1, 2, 3, 4}
            self._times = ["09:00"]

        self._refresh_day_buttons()
        self._refresh_time_chips()
        self._sync_kind_fields()
        self._set_form_mode(True)
        self.message_entry.focus_set()
        self.lift()
        self.focus_force()

    def _cancel_edit(self) -> None:
        self._editing_id = None
        self._clear_form()
        self._set_form_mode(False)

    def _save_reminder(self) -> None:
        message = self.message_entry.get().strip()
        if not message:
            messagebox.showwarning(APP_TITLE, "Escribe un mensaje para el recordatorio.")
            return

        kind = self.kind_var.get()
        existing = None
        if self._editing_id:
            existing = next((r for r in self.reminders if r.get("id") == self._editing_id), None)
        enabled = bool(existing.get("enabled", True)) if existing else True

        if kind == "weekly":
            pending = self.weekly_time_entry.get().strip()
            if pending and not self._add_times_from_text(pending):
                return

        try:
            if kind == "interval":
                raw = self.interval_entry.get().strip() or "30"
                minutes = int(raw)
                if minutes < 1:
                    raise ValueError("El intervalo debe ser al menos 1 minuto.")
                reminder = create_reminder(
                    message,
                    "interval",
                    interval_minutes=minutes,
                    enabled=enabled,
                    reminder_id=self._editing_id,
                )
            elif kind == "weekly":
                reminder = create_reminder(
                    message,
                    "weekly",
                    days=sorted(self._selected_days),
                    times=list(self._times),
                    enabled=enabled,
                    reminder_id=self._editing_id,
                )
            else:
                time_str = self.time_entry.get().strip()
                hour, minute = parse_hhmm(time_str)
                time_norm = f"{hour:02d}:{minute:02d}"
                reminder = create_reminder(
                    message,
                    "daily",
                    time_hhmm=time_norm,
                    enabled=enabled,
                    reminder_id=self._editing_id,
                )
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return

        if existing and kind in ("daily", "weekly"):
            done_on = existing.get("done_on")
            if isinstance(done_on, str) and done_on:
                reminder["done_on"] = done_on

        was_editing = self._editing_id
        self.reminders = upsert_reminder(self.reminders, reminder)
        reset = {was_editing} if was_editing else None
        self.scheduler.update_reminders(self.reminders, reset_ids=reset)
        self._editing_id = None
        self._clear_form()
        self._set_form_mode(False)
        self._refresh_list()

    def _toggle_reminder(self, reminder_id: str) -> None:
        current = next((r for r in self.reminders if r.get("id") == reminder_id), None)
        if not current:
            return
        self.reminders = set_enabled(self.reminders, reminder_id, not current.get("enabled", True))
        self.scheduler.update_reminders(self.reminders)
        self._refresh_list()

    def _on_done_checkbox(self, reminder_id: str, variable: tk.BooleanVar) -> None:
        done = bool(variable.get())
        self.after(0, lambda rid=reminder_id, flag=done: self._mark_done(rid, flag))

    def _mark_done(self, reminder_id: str, done: bool) -> None:
        self.reminders = set_done_today(self.reminders, reminder_id, done)
        self.scheduler.update_reminders(self.reminders, reset_ids={reminder_id})
        if done:
            dismiss_notifications(reminder_id)
        self._refresh_list()

    def _delete_reminder(self, reminder_id: str) -> None:
        if not messagebox.askyesno(APP_TITLE, "¿Eliminar este recordatorio?"):
            return
        if self._editing_id == reminder_id:
            self._cancel_edit()
        self.reminders = delete_reminder(self.reminders, reminder_id)
        self.scheduler.update_reminders(self.reminders)
        self._refresh_list()

    def _save_phone_settings(self) -> None:
        topic = self.phone_topic_entry.get()
        try:
            update_phone_settings(self.phone_enabled_var.get(), topic)
        except ValueError as exc:
            messagebox.showwarning(APP_TITLE, str(exc))

    def _copy_phone_topic(self) -> None:
        self._save_phone_settings()
        topic = self.phone_topic_entry.get().strip()
        self.clipboard_clear()
        self.clipboard_append(topic)
        self.copy_topic_btn.configure(text="Copiado")
        self.after(1500, lambda: self.copy_topic_btn.configure(text="Copiar tema"))

    def _test_notification(self) -> None:
        # Misma ruta visual que los recordatorios reales
        message = "Así se verán tus recordatorios."
        show_notification(APP_TITLE, message, parent=self)
        send_phone_notification(
            APP_TITLE,
            message,
            on_done=lambda ok, detail: self.after(
                0, lambda ok=ok, detail=detail: self._on_phone_test_done(ok, detail)
            ),
        )

    def _on_phone_test_done(self, ok: bool, detail: str) -> None:
        if ok:
            messagebox.showinfo(
                APP_TITLE,
                "Aviso enviado al celular. Si no llega, en ntfy suscríbete al tema con «Copiar tema».",
            )
            return
        if detail == "off":
            messagebox.showwarning(
                APP_TITLE,
                "El aviso al celular está desactivado. Marca «Avisar al celular».",
            )
            return
        if detail == "topic":
            messagebox.showwarning(APP_TITLE, "El tema de ntfy no es válido.")
            return
        messagebox.showwarning(
            APP_TITLE,
            "No se pudo enviar al celular. Revisa tu conexión a internet.",
        )

    def _on_reminder_fire(self, reminder: dict[str, Any]) -> None:
        snapshot = dict(reminder)
        self.after(0, lambda item=snapshot: self._present_reminder(item))

    def _present_reminder(self, reminder: dict[str, Any]) -> None:
        message = reminder.get("message") or "Recordatorio"
        reminder_id = str(reminder.get("id") or "")
        on_done = None
        if supports_done(reminder) and reminder_id:
            on_done = lambda rid=reminder_id: self._mark_done(rid, True)
        show_notification(
            APP_TITLE,
            message,
            parent=self,
            on_done=on_done,
            reminder_id=reminder_id or None,
        )
        send_phone_notification(APP_TITLE, message)
        self._refresh_next_notices()

    # ----- Ventana / bandeja -----

    def _on_unmap(self, event) -> None:
        # Minimizar desde la barra de tareas también manda a bandeja
        if event.widget is self and self.state() == "iconic" and not self._quitting:
            self.after(50, self._hide_to_tray)

    def _hide_to_tray(self) -> None:
        if self._quitting:
            return
        self.withdraw()

    def _show_from_tray(self) -> None:
        self.after(0, self._restore_window)

    def _restore_window(self) -> None:
        self.deiconify()
        self.state("normal")
        self.lift()
        self.focus_force()

    def _quit_app(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        if self._next_notice_job is not None:
            try:
                self.after_cancel(self._next_notice_job)
            except tk.TclError:
                pass
            self._next_notice_job = None
        try:
            self.scheduler.stop()
        except Exception:  # noqa: BLE001
            logger.exception("Error al detener el scheduler")
        try:
            self.tray.stop()
        except Exception:  # noqa: BLE001
            logger.exception("Error al detener la bandeja")
        if self._instance_guard is not None:
            try:
                self._instance_guard.release()
            except Exception:  # noqa: BLE001
                logger.exception("Error al liberar el bloqueo de instancia")
        save_reminders(self.reminders)
        self.after(0, self.destroy)


def main() -> int:
    guard = SingleInstanceGuard()
    if not guard.try_acquire():
        # Ya hay una instancia: se le pidió que muestre la ventana
        return 0

    app = App()
    app._instance_guard = guard
    guard.start_listener(on_show=app._show_from_tray)
    try:
        app.mainloop()
    finally:
        guard.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
