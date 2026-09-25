"""Icono en la bandeja del sistema (segundo plano)."""

from __future__ import annotations

import threading
from typing import Callable

from PIL import Image, ImageDraw
import pystray


def _create_icon_image() -> Image.Image:
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    # Campana simple
    draw.ellipse((16, 10, 48, 42), fill=(37, 99, 235))
    draw.rectangle((28, 40, 36, 52), fill=(37, 99, 235))
    draw.ellipse((26, 48, 38, 58), fill=(29, 78, 216))
    return image


class TrayIcon:
    def __init__(
        self,
        *,
        on_show: Callable[[], None],
        on_quit: Callable[[], None],
        tooltip: str = "Recordatorios",
    ) -> None:
        self._on_show = on_show
        self._on_quit = on_quit
        self._tooltip = tooltip
        self._icon: pystray.Icon | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        menu = pystray.Menu(
            pystray.MenuItem("Mostrar", self._handle_show, default=True),
            pystray.MenuItem("Salir", self._handle_quit),
        )
        self._icon = pystray.Icon(
            "recordatorios",
            _create_icon_image(),
            self._tooltip,
            menu,
        )
        self._thread = threading.Thread(target=self._icon.run, name="tray", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:  # noqa: BLE001
                pass
            self._icon = None

    def _handle_show(self, _icon=None, _item=None) -> None:
        self._on_show()

    def _handle_quit(self, _icon=None, _item=None) -> None:
        self._on_quit()
