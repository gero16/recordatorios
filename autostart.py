"""Inicio automático con Windows (registro del usuario, sin permisos de administrador)."""

from __future__ import annotations

import logging
import sys
import winreg
from pathlib import Path

logger = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Recordatorios"
AUTOSTART_FLAG = "--autostart"


def _launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" {AUTOSTART_FLAG}'
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    if pythonw.exists():
        exe = pythonw
    script = Path(__file__).resolve().parent / "main.py"
    return f'"{exe}" "{script}" {AUTOSTART_FLAG}'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
        return True
    except OSError:
        return False


def enable() -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, _launch_command())


def disable() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except FileNotFoundError:
        pass


def refresh() -> None:
    """Si está activo, actualiza la ruta por si la carpeta del proyecto se movió."""
    if not is_enabled():
        return
    try:
        enable()
    except OSError:
        logger.exception("No se pudo actualizar el inicio automático")


def started_by_autostart() -> bool:
    return AUTOSTART_FLAG in sys.argv[1:]
