"""Garantiza una sola instancia de la aplicación en Windows."""

from __future__ import annotations

import ctypes
import logging
import socket
import threading
from collections.abc import Callable
from ctypes import wintypes

logger = logging.getLogger(__name__)

_MUTEX_NAME = "Local\\RecordatoriosDesktopApp_SingleInstance"
_LOCK_HOST = "127.0.0.1"
_LOCK_PORT = 57391
_SHOW_CMD = b"SHOW\n"

# Constantes Win32
_ERROR_ALREADY_EXISTS = 183
_SW_RESTORE = 9


class SingleInstanceGuard:
    """
    Usa un mutex de Windows para permitir una sola instancia.
    Si ya hay una abierta, le pide que muestre la ventana y esta sale.
    """

    def __init__(self) -> None:
        self._mutex_handle: int | None = None
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._on_show: Callable[[], None] | None = None

    def try_acquire(self) -> bool:
        """True si esta es la única instancia; False si ya había otra."""
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, wintypes.BOOL(False), _MUTEX_NAME)
        if not handle:
            logger.error("No se pudo crear el mutex de instancia única")
            return True  # no bloquear el arranque si falla el mutex

        last_error = kernel32.GetLastError()
        if last_error == _ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            self._notify_existing()
            return False

        self._mutex_handle = handle
        self._start_server()
        return True

    def start_listener(self, on_show: Callable[[], None]) -> None:
        self._on_show = on_show
        if self._server is None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._listen_loop,
            name="single-instance",
            daemon=True,
        )
        self._thread.start()

    def release(self) -> None:
        self._stop.set()
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass
            self._server = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None

        if self._mutex_handle is not None:
            try:
                ctypes.windll.kernel32.CloseHandle(self._mutex_handle)
            except Exception:  # noqa: BLE001
                pass
            self._mutex_handle = None

    def _start_server(self) -> None:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # Sin SO_REUSEADDR: en Windows reutilizar permite otro bind
            server.bind((_LOCK_HOST, _LOCK_PORT))
            server.listen(5)
            server.settimeout(1.0)
            self._server = server
        except OSError as exc:
            logger.debug("No se pudo abrir el canal de activación: %s", exc)
            try:
                server.close()
            except OSError:
                pass
            self._server = None

    def _notify_existing(self) -> None:
        # 1) Intentar avisar por socket a la instancia viva
        try:
            with socket.create_connection((_LOCK_HOST, _LOCK_PORT), timeout=1.0) as client:
                client.sendall(_SHOW_CMD)
                return
        except OSError:
            pass

        # 2) Respaldo: traer al frente la ventana por título
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, "Recordatorios")
            if hwnd:
                user32.ShowWindow(hwnd, _SW_RESTORE)
                user32.SetForegroundWindow(hwnd)
        except Exception as exc:  # noqa: BLE001
            logger.debug("No se pudo enfocar la ventana existente: %s", exc)

    def _listen_loop(self) -> None:
        assert self._server is not None
        while not self._stop.is_set():
            try:
                conn, _addr = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                data = conn.recv(64)
                conn.close()
            except OSError:
                continue
            if data.startswith(b"SHOW") and self._on_show is not None:
                try:
                    self._on_show()
                except Exception:  # noqa: BLE001
                    logger.exception("Error al restaurar la ventana existente")
