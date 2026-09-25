"""Aplicación de escritorio: recordatorios con notificaciones en Windows."""

from __future__ import annotations

import logging
import sys
import tkinter as tk
from tkinter import messagebox
from typing import Any

import customtkinter as ctk

from notifier import show_notification
from scheduler import ReminderScheduler
from single_instance import SingleInstanceGuard
from storage import (
    create_reminder,
    delete_reminder,
    load_reminders,
    save_reminders,
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


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.title(APP_TITLE)
        self.geometry("860x640")
        self.minsize(760, 560)

        self.reminders: list[dict[str, Any]] = load_reminders()
        self._quitting = False
        self._editing_id: str | None = None

        self.scheduler = ReminderScheduler(on_fire=self._on_reminder_fire)
        self.tray = TrayIcon(on_show=self._show_from_tray, on_quit=self._quit_app)
        self._instance_guard: SingleInstanceGuard | None = None

        self._build_ui()
        self._refresh_list()

        self.protocol("WM_DELETE_WINDOW", self._hide_to_tray)
        self.bind("<Unmap>", self._on_unmap)

        self.scheduler.update_reminders(self.reminders)
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

        # Formulario
        form = ctk.CTkFrame(body)
        form.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        form.grid_columnconfigure(0, weight=1)
        form.grid_rowconfigure(8, weight=1)

        self.form_title = ctk.CTkLabel(
            form, text="Nuevo recordatorio", font=ctk.CTkFont(size=FONT_SECTION, weight="bold")
        )
        self.form_title.grid(row=0, column=0, sticky="w", padx=20, pady=(20, 14))

        ctk.CTkLabel(
            form, text="Mensaje", font=ctk.CTkFont(size=FONT_LABEL, weight="bold")
        ).grid(row=1, column=0, sticky="w", padx=20)
        self.message_entry = ctk.CTkEntry(
            form,
            placeholder_text="Ej: Beber agua",
            height=ENTRY_HEIGHT,
            font=ctk.CTkFont(size=FONT_BODY),
        )
        self.message_entry.grid(row=2, column=0, sticky="ew", padx=20, pady=(6, 16))

        ctk.CTkLabel(
            form, text="Tipo", font=ctk.CTkFont(size=FONT_LABEL, weight="bold")
        ).grid(row=3, column=0, sticky="w", padx=20)
        self.kind_var = tk.StringVar(value="interval")
        kind_row = ctk.CTkFrame(form, fg_color="transparent")
        kind_row.grid(row=4, column=0, sticky="ew", padx=20, pady=(8, 12))
        ctk.CTkRadioButton(
            kind_row,
            text="Cada cierto tiempo",
            variable=self.kind_var,
            value="interval",
            command=self._sync_kind_fields,
            font=ctk.CTkFont(size=FONT_BODY),
        ).pack(side="left", padx=(0, 18))
        ctk.CTkRadioButton(
            kind_row,
            text="A una hora",
            variable=self.kind_var,
            value="daily",
            command=self._sync_kind_fields,
            font=ctk.CTkFont(size=FONT_BODY),
        ).pack(side="left")

        self.interval_frame = ctk.CTkFrame(form, fg_color="transparent")
        self.interval_frame.grid(row=5, column=0, sticky="ew", padx=20, pady=(4, 10))
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
        self.time_frame.grid(row=6, column=0, sticky="ew", padx=20, pady=(4, 10))
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

        form_actions = ctk.CTkFrame(form, fg_color="transparent")
        form_actions.grid(row=7, column=0, sticky="ew", padx=20, pady=(20, 24))
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

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=24, pady=(4, 20))
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
        if self.kind_var.get() == "interval":
            self.interval_frame.grid()
            self.time_frame.grid_remove()
        else:
            self.interval_frame.grid_remove()
            self.time_frame.grid()

    def _refresh_list(self) -> None:
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
            if reminder.get("kind") == "interval":
                detail = f"Cada {reminder.get('interval_minutes', '?')} min"
            else:
                detail = f"Todos los días a las {reminder.get('time', '?')}"

            enabled = bool(reminder.get("enabled", True))
            status = "Activo" if enabled else "Pausado"

            ctk.CTkLabel(
                card,
                text=title,
                font=ctk.CTkFont(size=FONT_CARD_TITLE, weight="bold"),
                anchor="w",
            ).grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 0))
            ctk.CTkLabel(
                card,
                text=f"{detail} · {status}",
                text_color="#64748B",
                font=ctk.CTkFont(size=FONT_CARD_META),
                anchor="w",
            ).grid(row=1, column=0, sticky="ew", padx=14, pady=(4, 10))

            actions = ctk.CTkFrame(card, fg_color="transparent")
            actions.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 12))

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
        if defaults:
            self.interval_entry.insert(0, "30")
            self.time_entry.insert(0, "15:00")
        self._sync_kind_fields()

    def _start_edit(self, reminder_id: str) -> None:
        reminder = next((r for r in self.reminders if r.get("id") == reminder_id), None)
        if not reminder:
            return

        self._editing_id = reminder_id
        self._clear_form(defaults=False)

        self.message_entry.insert(0, reminder.get("message") or "")
        kind = reminder.get("kind") or "interval"
        self.kind_var.set(kind)

        if kind == "interval":
            self.interval_entry.insert(0, str(reminder.get("interval_minutes") or 30))
            self.time_entry.insert(0, "15:00")
        else:
            self.interval_entry.insert(0, "30")
            self.time_entry.insert(0, reminder.get("time") or "15:00")

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
                    enabled=bool(existing.get("enabled", True)) if existing else True,
                    reminder_id=self._editing_id,
                )
            else:
                time_str = self.time_entry.get().strip()
                hour, minute = ReminderScheduler._parse_hhmm(time_str)
                time_norm = f"{hour:02d}:{minute:02d}"
                reminder = create_reminder(
                    message,
                    "daily",
                    time_hhmm=time_norm,
                    enabled=bool(existing.get("enabled", True)) if existing else True,
                    reminder_id=self._editing_id,
                )
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return

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

    def _delete_reminder(self, reminder_id: str) -> None:
        if not messagebox.askyesno(APP_TITLE, "¿Eliminar este recordatorio?"):
            return
        if self._editing_id == reminder_id:
            self._cancel_edit()
        self.reminders = delete_reminder(self.reminders, reminder_id)
        self.scheduler.update_reminders(self.reminders)
        self._refresh_list()

    def _test_notification(self) -> None:
        # Misma ruta visual que los recordatorios reales
        show_notification(APP_TITLE, "Así se verán tus recordatorios.", parent=self)

    def _on_reminder_fire(self, reminder: dict[str, Any]) -> None:
        message = reminder.get("message") or "Recordatorio"
        self.after(
            0,
            lambda m=message: show_notification(APP_TITLE, m, parent=self),
        )

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
