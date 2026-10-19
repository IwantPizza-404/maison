"""Telegram Bot API: один бот Maison — уведомления менеджеру, вход и уведомления покупателей."""

import logging
from typing import Any
from urllib.parse import urlsplit

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


class TelegramError(Exception):
    pass


def is_configured() -> bool:
    return bool(settings.TELEGRAM_BOT_TOKEN)


def call(method: str, payload: dict[str, Any] | None = None, *, timeout: float = 10) -> Any:
    """Вызов метода Bot API. Ошибки сети и ответы ok=false → TelegramError."""
    try:
        response = httpx.post(
            f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}",
            json=payload or {},
            timeout=timeout,
        )
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise TelegramError(str(exc)) from exc
    if not data.get("ok"):
        raise TelegramError(data.get("description", "Telegram API error"))
    return data.get("result")


def is_public_url(url: str) -> bool:
    """Telegram отклоняет кнопки со ссылками на localhost — локально их пропускаем."""
    host = urlsplit(url).hostname or ""
    return host not in ("localhost", "127.0.0.1", "0.0.0.0") and not host.endswith(".localhost")


def url_buttons(*buttons: tuple[str, str]) -> dict | None:
    """Кнопки-ссылки под сообщением: (текст, url), каждая в своей строке."""
    rows = [[{"text": text, "url": url}] for text, url in buttons if is_public_url(url)]
    return {"inline_keyboard": rows} if rows else None


def send_message(chat_id: int | str, text: str, *, reply_markup: dict | None = None) -> bool:
    """Отправляет HTML-сообщение. Без токена бота — пропускает (False), не падает."""
    if not is_configured() or not chat_id:
        logger.warning("Telegram bot is not configured, message skipped")
        return False
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    call("sendMessage", payload)
    return True
