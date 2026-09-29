"""Aviso al celular mediante ntfy. El tema queda solo en este equipo."""

from __future__ import annotations

import json
import logging
import re
import secrets
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / "data"
PHONE_FILE = DATA_DIR / "phone.json"
DEFAULT_SERVER = "https://ntfy.sh"
TOPIC_RE = re.compile(r"^[-_A-Za-z0-9]{1,64}$")

DoneCallback = Callable[[bool, str], None]


def topic_is_valid(topic: str) -> bool:
    return bool(TOPIC_RE.fullmatch(topic.strip()))


def load_phone_config() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if PHONE_FILE.exists():
        try:
            with PHONE_FILE.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and topic_is_valid(str(data.get("topic") or "")):
                data.setdefault("enabled", True)
                data.setdefault("server", DEFAULT_SERVER)
                return data
        except (json.JSONDecodeError, OSError):
            logger.warning("No se pudo leer la configuración del celular; se crea una nueva.")

    config = {
        "enabled": True,
        "server": DEFAULT_SERVER,
        "topic": secrets.token_urlsafe(18),
    }
    _write(config)
    return config


def update_phone_settings(enabled: bool, topic: str) -> dict[str, Any]:
    cleaned = topic.strip()
    if not topic_is_valid(cleaned):
        raise ValueError(
            "El tema solo puede tener letras, números, guiones y guion bajo (máximo 64)."
        )
    current = load_phone_config()
    current["enabled"] = bool(enabled)
    current["topic"] = cleaned
    current["server"] = str(current.get("server") or DEFAULT_SERVER).rstrip("/") or DEFAULT_SERVER
    _write(current)
    return current


def send_phone_notification(
    title: str,
    message: str,
    on_done: DoneCallback | None = None,
) -> None:
    """Envía el aviso en segundo plano. on_done(ok, detalle) puede llamarse desde otro hilo."""

    def work() -> None:
        ok, detail = _send_blocking(title, message)
        if on_done is not None:
            on_done(ok, detail)

    threading.Thread(target=work, name="ntfy", daemon=True).start()


def _send_blocking(title: str, message: str) -> tuple[bool, str]:
    config = load_phone_config()
    if not config.get("enabled", True):
        return False, "off"

    topic = str(config.get("topic") or "").strip()
    if not topic_is_valid(topic):
        return False, "topic"

    server = str(config.get("server") or DEFAULT_SERVER).rstrip("/") or DEFAULT_SERVER
    text = (message or "Recordatorio").strip() or "Recordatorio"
    url = f"{server}/{topic}"
    request = urllib.request.Request(url, data=text.encode("utf-8"), method="POST")
    request.add_header("Content-Type", "text/plain; charset=utf-8")
    request.add_header("Title", title or "Recordatorio")
    request.add_header("Tags", "bell")

    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        logger.warning("No se pudo avisar al celular (HTTP %s).", exc.code)
        return False, "http"
    except Exception:
        logger.warning("No se pudo avisar al celular.")
        return False, "network"

    logger.info("Aviso enviado al celular.")
    return True, ""


def _write(config: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with PHONE_FILE.open("w", encoding="utf-8") as fh:
        json.dump(config, fh, ensure_ascii=False, indent=2)
