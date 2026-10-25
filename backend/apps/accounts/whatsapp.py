"""Код входа в WhatsApp через WhatsApp Cloud API (Meta).

Включается, если заданы WHATSAPP_TOKEN и WHATSAPP_PHONE_NUMBER_ID. Свободный текст WhatsApp
первым сообщением не пропускает — код уходит шаблоном категории «Authentication»
(с кнопкой «Скопировать код»). Шаблон создаётся и проходит проверку в WhatsApp Manager;
его имя и язык — WHATSAPP_TEMPLATE и WHATSAPP_TEMPLATE_LANGUAGE. Настройка — docs/DEPLOY.md.
"""

import httpx
from django.conf import settings

API = "https://graph.facebook.com"


class WhatsAppError(Exception):
    pass


def is_enabled() -> bool:
    return bool(settings.WHATSAPP_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID)


def send_code(phone: str, code: str) -> None:
    if not is_enabled():
        raise WhatsAppError("WhatsApp is not configured")
    payload = {
        "messaging_product": "whatsapp",
        "to": phone.lstrip("+"),
        "type": "template",
        "template": {
            "name": settings.WHATSAPP_TEMPLATE,
            "language": {"code": settings.WHATSAPP_TEMPLATE_LANGUAGE},
            "components": [
                {"type": "body", "parameters": [{"type": "text", "text": code}]},
                # Кнопка «Скопировать код» шаблона авторизации тоже получает код
                {
                    "type": "button",
                    "sub_type": "url",
                    "index": "0",
                    "parameters": [{"type": "text", "text": code}],
                },
            ],
        },
    }
    url = f"{API}/{settings.WHATSAPP_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    try:
        response = httpx.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"},
            timeout=10,
        )
    except httpx.HTTPError as exc:
        raise WhatsAppError(str(exc)) from exc
    if response.is_error:
        raise WhatsAppError(f"WhatsApp error {response.status_code}: {response.text[:300]}")
