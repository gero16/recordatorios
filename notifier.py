"""Panel de notificaciones: una sola ventana con tarjetas apiladas."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable

import customtkinter as ctk

logger = logging.getLogger(__name__)

PANEL_WIDTH = 380
CARD_HEIGHT = 118
CARD_HEIGHT_DONE = 148
CARD_GAP = 8
PANEL_PAD = 10
MARGIN_RIGHT = 20
MARGIN_BOTTOM = 56
MAX_CARDS = 5

ACCENT = "#2563EB"
PANEL_BG = "#E8EEF5"
CARD_BG = "#FFFFFF"
TITLE_COLOR = "#0F172A"
BODY_COLOR = "#475569"
MUTED = "#94A3B8"
BORDER = "#D0D7E2"
DONE_BG = "#DCFCE7"
DONE_HOVER = "#BBF7D0"
DONE_TEXT = "#166534"

_dock: NotificationDock | None = None


def _play_sound() -> None:
    try:
        import winsound

        winsound.MessageBeep(winsound.MB_OK)
    except Exception:  # noqa: BLE001
        pass


class NotificationDock(ctk.CTkToplevel):
    """Una sola ventana anclada a la derecha; las tarjetas viven adentro."""

    def __init__(self, parent: Any) -> None:
        super().__init__(parent)
        self._parent = parent
        self._cards: list[ctk.CTkFrame] = []

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(fg_color=PANEL_BG)
        try:
            self.attributes("-alpha", 0.98)
        except Exception:  # noqa: BLE001
            pass

        self._stack = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=0)
        self._stack.pack(fill="both", expand=True, padx=PANEL_PAD, pady=PANEL_PAD)

        self.withdraw()

    def add(
        self,
        title: str,
        message: str,
        *,
        on_done: Callable[[], None] | None = None,
        reminder_id: str | None = None,
    ) -> None:
        while len(self._cards) >= MAX_CARDS:
            self._remove_card(self._cards[0])

        card = self._build_card(title, message, on_done=on_done, reminder_id=reminder_id)
        self._cards.append(card)
        self._relayout_cards()
        self._layout_window()
        self.deiconify()
        self.lift()
        try:
            self.attributes("-topmost", True)
        except Exception:  # noqa: BLE001
            pass

    def _build_card(
        self,
        title: str,
        message: str,
        *,
        on_done: Callable[[], None] | None = None,
        reminder_id: str | None = None,
    ) -> ctk.CTkFrame:
        height = CARD_HEIGHT_DONE if on_done is not None else CARD_HEIGHT
        card = ctk.CTkFrame(
            self._stack,
            fg_color=CARD_BG,
            corner_radius=14,
            border_width=1,
            border_color=BORDER,
            height=height,
        )
        card.pack_propagate(False)
        card._panel_height = height  # type: ignore[attr-defined]
        card._reminder_id = reminder_id  # type: ignore[attr-defined]
        card._on_done = on_done  # type: ignore[attr-defined]

        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=14, pady=12)

        top = ctk.CTkFrame(content, fg_color="transparent")
        top.pack(fill="x")

        # Punto de acento + título (no rompe el borde redondeado)
        ctk.CTkLabel(
            top,
            text="●",
            text_color=ACCENT,
            font=ctk.CTkFont(size=12),
            width=18,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkLabel(
            top,
            text=title,
            text_color=TITLE_COLOR,
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            top,
            text="✕",
            width=28,
            height=28,
            corner_radius=8,
            fg_color="transparent",
            hover_color="#F1F5F9",
            text_color=MUTED,
            font=ctk.CTkFont(size=13),
            command=lambda c=card: self._remove_card(c),
        ).pack(side="right")

        ctk.CTkLabel(
            content,
            text=self._truncate(message),
            text_color=BODY_COLOR,
            font=ctk.CTkFont(size=14),
            anchor="w",
            justify="left",
            wraplength=PANEL_WIDTH - 60,
        ).pack(fill="x", pady=(8, 0), padx=(24, 0))

        bottom = ctk.CTkFrame(content, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", pady=(8, 0))

        if on_done is not None:
            ctk.CTkButton(
                bottom,
                text="Hecho",
                width=78,
                height=28,
                corner_radius=8,
                fg_color=DONE_BG,
                hover_color=DONE_HOVER,
                text_color=DONE_TEXT,
                font=ctk.CTkFont(size=13, weight="bold"),
                command=lambda c=card: self._complete_card(c),
            ).pack(side="left")

        ctk.CTkLabel(
            bottom,
            text=datetime.now().strftime("%H:%M"),
            text_color=MUTED,
            font=ctk.CTkFont(size=11),
            anchor="e",
        ).pack(side="right")

        return card

    @staticmethod
    def _truncate(text: str, max_chars: int = 95) -> str:
        clean = " ".join(text.split())
        if len(clean) <= max_chars:
            return clean
        return clean[: max_chars - 1].rstrip() + "…"

    def _relayout_cards(self) -> None:
        for item in self._stack.winfo_children():
            item.pack_forget()

        # Más nueva arriba
        newest_first = list(reversed(self._cards))
        for i, item in enumerate(newest_first):
            gap = CARD_GAP if i < len(newest_first) - 1 else 0
            item.pack(fill="x", pady=(0, gap))

    def _complete_card(self, card: ctk.CTkFrame) -> None:
        reminder_id = getattr(card, "_reminder_id", None)
        callback = getattr(card, "_on_done", None)
        if reminder_id:
            pending = [
                item
                for item in self._cards
                if getattr(item, "_reminder_id", None) == reminder_id
            ]
        else:
            pending = [card]
        if card not in pending:
            pending.append(card)
        for item in pending:
            self._remove_card(item)
        if callback is None:
            return
        try:
            callback()
        except Exception:  # noqa: BLE001
            logger.exception("Error al marcar el recordatorio como hecho")

    def dismiss(self, reminder_id: str) -> None:
        pending = [
            item for item in self._cards if getattr(item, "_reminder_id", None) == reminder_id
        ]
        for item in pending:
            self._remove_card(item)

    def _card_height(self, card: ctk.CTkFrame) -> int:
        height = getattr(card, "_panel_height", CARD_HEIGHT)
        try:
            return int(height)
        except (TypeError, ValueError):
            return CARD_HEIGHT

    def _remove_card(self, card: ctk.CTkFrame) -> None:
        if card in self._cards:
            self._cards.remove(card)
        try:
            card.destroy()
        except Exception:  # noqa: BLE001
            pass

        if not self._cards:
            self.withdraw()
            return

        self._relayout_cards()
        self._layout_window()

    def _layout_window(self) -> None:
        n = len(self._cards)
        if n == 0:
            return

        height = (
            PANEL_PAD * 2
            + sum(self._card_height(card) for card in self._cards)
            + max(0, n - 1) * CARD_GAP
        )
        width = PANEL_WIDTH

        self.update_idletasks()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = screen_w - width - MARGIN_RIGHT
        y = max(16, screen_h - height - MARGIN_BOTTOM)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.update_idletasks()


def show_notification(
    title: str,
    message: str,
    parent=None,
    *,
    on_done: Callable[[], None] | None = None,
    reminder_id: str | None = None,
) -> None:
    """Agrega una tarjeta al panel (la más nueva queda arriba)."""
    global _dock

    if parent is None:
        logger.error("show_notification requiere la ventana padre")
        return

    try:
        if _dock is None or not _dock.winfo_exists():
            _dock = NotificationDock(parent)

        _dock.add(title, message, on_done=on_done, reminder_id=reminder_id)
        _play_sound()
    except Exception as exc:  # noqa: BLE001
        logger.exception("No se pudo mostrar la notificación: %s", exc)


def dismiss_notifications(reminder_id: str) -> None:
    """Cierra las tarjetas abiertas de un recordatorio."""
    if _dock is None:
        return
    try:
        if not _dock.winfo_exists():
            return
        _dock.dismiss(reminder_id)
    except Exception:  # noqa: BLE001
        logger.exception("No se pudo cerrar la notificación %s", reminder_id)
