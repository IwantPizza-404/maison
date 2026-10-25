"""Вход покупателей, привязка гостевых заказов, выгрузка покупателей в Excel."""

import logging

from django.core.cache import cache
from django.db import models, transaction
from django.db.models import Count, Q, QuerySet, Sum
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import pgettext

from apps.core.excel import table
from apps.orders.models import Order

from . import sms, whatsapp
from .models import Customer, LoginRequest, normalize_phone

logger = logging.getLogger(__name__)


class LoginError(Exception):
    """Ошибка входа, которую можно показать покупателю."""


SMS_PER_PHONE_PER_HOUR = 3


def start_sms_login(phone: str) -> str:
    return start_phone_login(LoginRequest.Method.SMS, phone)


def start_whatsapp_login(phone: str) -> str:
    return start_phone_login(LoginRequest.Method.WHATSAPP, phone)


def start_phone_login(method: str, phone: str) -> str:
    """Код на номер телефона — в SMS или WhatsApp. Возвращает токен попытки входа."""
    phone = normalize_phone(phone)
    if len(phone) < 11:
        raise LoginError(_("Enter a phone number in international format."))
    # Лимит на номер (не только на IP): сообщения платные, их нельзя рассылать
    # на чужой номер с разных IP
    key = f"{method}-login:{phone}"
    cache.add(key, 0, 60 * 60)
    if cache.incr(key) > SMS_PER_PHONE_PER_HOUR:
        raise LoginError(_("Too many codes for this number. Try again in an hour."))
    request, token = LoginRequest.create(method, phone=phone)
    code = request.issue_code()
    if method == LoginRequest.Method.WHATSAPP:
        try:
            whatsapp.send_code(phone, code)
        except whatsapp.WhatsAppError as exc:
            logger.error("WhatsApp sending failed: %s", exc)
            raise LoginError(
                _("Could not send the code to WhatsApp. Try another login method.")
            ) from exc
        return token
    try:
        sms.send(phone, _("Maison login code: %(code)s") % {"code": code})
    except sms.SmsError as exc:
        logger.error("SMS sending failed: %s", exc)
        raise LoginError(_("Could not send SMS. Try logging in with Telegram.")) from exc
    return token


def complete_login(token: str, code: str) -> Customer:
    request = LoginRequest.active(token)
    if request is None or not request.phone:
        raise LoginError(_("The code has expired. Please start again."))
    # Проверка — вне транзакции входа: счётчик попыток должен сохраниться и при неверном коде,
    # иначе откат транзакции обнулял бы его и код можно было бы перебирать
    if not request.check_code(code):
        raise LoginError(_("Wrong code."))
    return _finish_login(request)


@transaction.atomic
def _finish_login(request: LoginRequest) -> Customer:
    customer = find_or_create_customer(request.phone, request.telegram_id)
    request.used_at = timezone.now()
    request.save(update_fields=["used_at"])
    customer.last_login_at = timezone.now()
    customer.save(update_fields=["last_login_at"])
    link_guest_orders(customer)
    return customer


def find_or_create_customer(phone: str, telegram_id: int | None) -> Customer:
    """Телефон подтверждён (Telegram-контакт, SMS или WhatsApp) — это один и тот же человек."""
    by_telegram = Customer.objects.filter(telegram_id=telegram_id).first() if telegram_id else None
    by_phone = Customer.objects.filter(phone=phone).first()

    if by_telegram and by_phone and by_telegram != by_phone:
        # Номер переехал на другой Telegram-аккаунт: отвязываем старый
        by_telegram.telegram_id = None
        by_telegram.save(update_fields=["telegram_id"])
        by_telegram = None

    customer = by_phone or by_telegram
    if customer is None:
        return Customer.objects.create(phone=phone, telegram_id=telegram_id)

    changed = []
    if telegram_id and customer.telegram_id != telegram_id:
        customer.telegram_id = telegram_id
        changed.append("telegram_id")
    if customer.phone != phone and not Customer.objects.filter(phone=phone).exists():
        customer.phone = phone  # человек сменил номер в Telegram
        changed.append("phone")
    if changed:
        customer.save(update_fields=changed)
    return customer


def link_guest_orders(customer: Customer) -> int:
    """Заказы без регистрации на этот номер появляются в кабинете."""
    return Order.objects.filter(customer__isnull=True, phone_normalized=customer.phone).update(
        customer=customer
    )


# --- Экспорт ---------------------------------------------------------------------


def export_customers(queryset: QuerySet[Customer]) -> bytes:
    """Покупатели в Excel: контакты, настройки и сводка по заказам (без отменённых)."""
    customers = (
        queryset.annotate(
            orders_count=Count("orders", filter=~Q(orders__status=Order.Status.CANCELLED)),
            orders_total=Sum("orders__total", filter=~Q(orders__status=Order.Status.CANCELLED)),
        )
        .prefetch_related("addresses")
        .order_by("-created_at")
    )

    def label(name: str) -> str:
        model_field = Customer._meta.get_field(name)
        assert isinstance(model_field, models.Field)
        text = str(model_field.verbose_name)
        return text[:1].upper() + text[1:]  # capitalize() сделал бы «telegram» строчным

    def local(value):
        # Excel не умеет даты с часовым поясом — пишем местное время
        return timezone.localtime(value).replace(tzinfo=None) if value else None

    headers = [
        label("phone"),
        # «name» у товара переводится как «Название» — у покупателя это имя
        pgettext("person", "Name"),
        label("email"),
        "Telegram",
        label("language"),
        label("currency"),
        label("notify_telegram"),
        label("created_at"),
        label("last_login_at"),
        _("Orders"),
        _("Orders total, USD"),
        _("Address"),
    ]
    rows = (
        [
            customer.phone,
            customer.name,
            customer.email,
            f"@{customer.telegram_username}" if customer.telegram_username else "",
            customer.language,
            customer.currency,
            _("yes") if customer.notify_telegram else _("no"),
            local(customer.created_at),
            local(customer.last_login_at),
            customer.orders_count,  # type: ignore[attr-defined]
            customer.orders_total or 0,  # type: ignore[attr-defined]
            str(customer.addresses.all()[0]) if customer.addresses.all() else "",
        ]
        for customer in customers
    )
    widths = [18, 22, 26, 18, 10, 10, 14, 18, 18, 10, 16, 40]
    title = str(Customer._meta.verbose_name_plural)
    return table(title[:1].upper() + title[1:], headers, rows, widths)
