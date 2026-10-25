import httpx
import pytest
from django.core.cache import cache

from apps.accounts import sms, whatsapp
from apps.accounts.bot import process_update
from apps.accounts.models import Customer, normalize_phone
from apps.orders.services import Customer as OrderCustomer
from apps.orders.services import place_order

from .conftest import contact_message, start_message

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def reset_throttle():
    cache.clear()


def telegram_start(client) -> str:
    data = client.post("/api/v1/auth/telegram/start", content_type="application/json").json()
    assert data["bot_url"] == f"https://t.me/maison_test_bot?start=login_{data['token']}"
    return data["token"]


def verify(client, token, code):
    return client.post(
        "/api/v1/auth/verify", {"token": token, "code": code}, content_type="application/json"
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+998 (90) 123-45-67", "+998901234567"),
        ("90 123 45 67", "+998901234567"),
        ("+7 916 000 00 00", "+79160000000"),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def test_telegram_login_new_customer(client, tg):
    token = telegram_start(client)

    process_update(start_message(111, token))
    assert tg.last["reply_markup"]["keyboard"][0][0]["request_contact"] is True

    process_update(contact_message(111, "998901234567"))
    response = verify(client, token, tg.last_code())

    assert response.status_code == 200
    assert response.json()["phone"] == "+998901234567"
    assert "maison_session" in response.cookies
    assert response.cookies["maison_session"]["httponly"]
    assert client.get("/api/v1/account/me").json()["has_telegram"] is True
    assert Customer.objects.get().telegram_id == 111


def test_returning_customer_gets_code_immediately(client, tg):
    Customer.objects.create(phone="+998901234567", telegram_id=111)
    token = telegram_start(client)

    process_update(start_message(111, token))

    assert verify(client, token, tg.last_code()).status_code == 200


def test_foreign_contact_is_rejected(client, tg):
    token = telegram_start(client)
    process_update(start_message(111, token))

    process_update(contact_message(111, "998900000000", contact_user_id=222))

    assert "<b>" not in tg.last["text"]  # код не отправлен


def test_attacker_cannot_use_victims_code(client, tg):
    """Злоумышленник отправил жертве ссылку со своим токеном: код получает жертва в Telegram,
    а войти можно только в браузере, где этот код введут."""
    attacker_token = telegram_start(client)
    victim_token = telegram_start(client)
    process_update(start_message(111, victim_token))
    process_update(contact_message(111, "998901234567"))

    assert verify(client, attacker_token, tg.last_code()).status_code == 400


def test_wrong_code_attempts_are_limited(client, tg):
    token = telegram_start(client)
    process_update(start_message(111, token))
    process_update(contact_message(111, "998901234567"))
    code = tg.last_code()
    wrong = "000000" if code != "000000" else "111111"

    for _ in range(5):
        assert verify(client, token, wrong).status_code == 400

    assert verify(client, token, code).status_code == 400  # попытки исчерпаны


def test_code_works_once(client, tg):
    token = telegram_start(client)
    process_update(start_message(111, token))
    process_update(contact_message(111, "998901234567"))
    code = tg.last_code()

    assert verify(client, token, code).status_code == 200
    assert verify(client, token, code).status_code == 400


def test_expired_link_in_bot(client, tg):
    process_update(start_message(111, "unknown-token"))

    assert "expired" in tg.last["text"] or "устарела" in tg.last["text"]


def test_guest_orders_are_linked_on_login(client, tg, watch, pickup):
    order = place_order(
        items={"watch": 1},
        customer=OrderCustomer(
            name="A", phone="90 123 45 67", contact_method="phone", country="UZ", city="T"
        ),
        delivery_code="pickup-tashkent",
        currency="USD",
        language="ru",
    )
    token = telegram_start(client)
    process_update(start_message(111, token))
    process_update(contact_message(111, "+998901234567"))
    verify(client, token, tg.last_code())

    orders = client.get("/api/v1/account/orders").json()

    assert [o["number"] for o in orders] == [order.number]


def test_sms_login(client, settings, monkeypatch):
    settings.ESKIZ_EMAIL, settings.ESKIZ_PASSWORD = "shop@maison.uz", "secret"
    sent = {}
    monkeypatch.setattr(sms, "send", lambda phone, text: sent.update(phone=phone, text=text))

    token = client.post(
        "/api/v1/auth/sms/start", {"phone": "+998 90 765 43 21"}, content_type="application/json"
    ).json()["token"]
    code = sent["text"][-6:]

    assert sent["phone"] == "+998907654321"
    assert verify(client, token, code).json()["phone"] == "+998907654321"
    assert Customer.objects.get().telegram_id is None


def test_sms_disabled_and_methods(client, settings):
    settings.ESKIZ_EMAIL = ""
    settings.TELEGRAM_BOT_TOKEN = ""
    settings.WHATSAPP_TOKEN = ""

    response = client.post(
        "/api/v1/auth/sms/start", {"phone": "+998901234567"}, content_type="application/json"
    )

    assert response.status_code == 400
    assert client.get("/api/v1/auth/methods").json() == {
        "telegram": False,
        "sms": False,
        "whatsapp": False,
    }


def test_phone_moved_to_another_telegram(client, tg):
    old = Customer.objects.create(phone="+998901234567", telegram_id=111)
    Customer.objects.create(phone="+998900000000", telegram_id=222)
    token = telegram_start(client)

    # Пользователь Telegram 222 подтверждает номер, который раньше был у 111
    process_update(start_message(222, token))
    verify(client, token, tg.last_code())  # номер +998900000000 — уже его

    old.refresh_from_db()
    assert old.telegram_id == 111


def test_logout_and_anonymous_access(client, tg):
    token = telegram_start(client)
    process_update(start_message(111, token))
    process_update(contact_message(111, "998901234567"))
    verify(client, token, tg.last_code())

    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/account/me").status_code == 401


def test_webhook_requires_secret(client, settings, tg):
    settings.TELEGRAM_WEBHOOK_SECRET = "s3cret"
    update = start_message(111, "x")

    forbidden = client.post("/api/v1/telegram/webhook", update, content_type="application/json")
    ok = client.post(
        "/api/v1/telegram/webhook",
        update,
        content_type="application/json",
        headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"},
    )

    assert forbidden.status_code == 403
    assert ok.status_code == 200
    assert tg.sent  # обновление обработано


def test_sms_limit_per_phone(client, settings, monkeypatch):
    settings.ESKIZ_EMAIL, settings.ESKIZ_PASSWORD = "shop@maison.uz", "secret"
    monkeypatch.setattr(sms, "send", lambda phone, text: None)

    def start(ip):
        return client.post(
            "/api/v1/auth/sms/start",
            {"phone": "+998901234567"},
            content_type="application/json",
            REMOTE_ADDR=ip,
        ).status_code

    # Разные IP, один номер: четвёртая SMS за час не отправляется
    assert [start(f"10.0.0.{i}") for i in range(4)] == [200, 200, 200, 400]


# --- WhatsApp --------------------------------------------------------------------


@pytest.fixture
def meta(settings, monkeypatch):
    """WhatsApp Cloud API: запоминаем запросы, отвечаем заданным статусом."""
    settings.WHATSAPP_TOKEN, settings.WHATSAPP_PHONE_NUMBER_ID = "meta-token", "1234567890"
    calls: list[dict] = []
    reply = {"status": 200}

    def fake_post(url, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers})
        return httpx.Response(reply["status"], json={}, request=httpx.Request("POST", url))

    monkeypatch.setattr(whatsapp.httpx, "post", fake_post)
    return {"calls": calls, "reply": reply}


def whatsapp_start(client, phone="+998 90 765 43 21"):
    return client.post(
        "/api/v1/auth/whatsapp/start", {"phone": phone}, content_type="application/json"
    )


def test_whatsapp_login(client, meta):
    token = whatsapp_start(client).json()["token"]

    call = meta["calls"][0]
    template = call["json"]["template"]
    code = template["components"][0]["parameters"][0]["text"]
    assert call["url"].endswith("/1234567890/messages")
    assert call["headers"]["Authorization"] == "Bearer meta-token"
    assert call["json"]["to"] == "998907654321"
    assert template["name"] == "login_code"
    assert template["components"][1]["parameters"][0]["text"] == code  # кнопка «Скопировать код»
    assert verify(client, token, code).json()["phone"] == "+998907654321"
    assert client.get("/api/v1/auth/methods").json()["whatsapp"] is True


def test_whatsapp_error_is_shown(client, meta):
    meta["reply"]["status"] = 400

    response = whatsapp_start(client)

    assert response.status_code == 400
    assert "WhatsApp" in response.json()["detail"]


def test_whatsapp_disabled(client, settings):
    settings.WHATSAPP_TOKEN = ""

    assert whatsapp_start(client).status_code == 400
