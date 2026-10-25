"""Загрузка курсов из Центрального банка Узбекистана."""

import logging
from datetime import date, datetime
from decimal import Decimal

import httpx
from django.conf import settings
from django.core.cache import cache
from django.db import transaction

from .models import ExchangeRate

logger = logging.getLogger(__name__)

CBU_URL = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/"
RATES_CACHE_KEY = "currency:rates"


class RatesFetchError(Exception):
    pass


def parse_cbu(payload: list[dict]) -> tuple[dict[str, Decimal], date | None]:
    """Курсы ЦБ (сумы за `Nominal` единиц валюты) → единицы валюты за 1 USD."""
    uzs_per_unit: dict[str, Decimal] = {}
    rate_date = None
    for row in payload:
        uzs_per_unit[row["Ccy"]] = Decimal(row["Rate"]) / Decimal(row["Nominal"])
        if row["Ccy"] == "USD":
            rate_date = datetime.strptime(row["Date"], "%d.%m.%Y").date()

    usd = uzs_per_unit.get("USD")
    if not usd:
        raise RatesFetchError("USD rate is missing in CBU response")

    rates = {"UZS": usd}
    for code, uzs in uzs_per_unit.items():
        rates[code] = usd / uzs
    rates["USD"] = Decimal(1)
    return rates, rate_date


def fetch_cbu_rates(timeout: float = 15) -> tuple[dict[str, Decimal], date | None]:
    try:
        response = httpx.get(CBU_URL, timeout=timeout)
        response.raise_for_status()
        return parse_cbu(response.json())
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise RatesFetchError(str(exc)) from exc


@transaction.atomic
def update_rates() -> list[str]:
    """Обновляет официальные курсы валют из админки. Возвращает обновлённые коды.

    Валюты, которых нет у ЦБ, не трогаем — у них ручной курс.
    """
    rates, rate_date = fetch_cbu_rates()
    updated = []
    for item in ExchangeRate.objects.exclude(currency=settings.BASE_CURRENCY):
        if item.currency not in rates:
            continue
        item.rate = rates[item.currency].quantize(Decimal("0.000001"))
        item.rate_date = rate_date
        item.save(update_fields=["rate", "rate_date", "updated_at"])
        updated.append(item.currency)
    cache.delete(RATES_CACHE_KEY)
    logger.info("Exchange rates updated: %s", ", ".join(updated))
    return updated


def official_rate(code: str) -> tuple[Decimal, date | None] | None:
    """Курс ЦБ для одной валюты — при добавлении валюты в админке. None — ЦБ её не публикует."""
    rates, rate_date = fetch_cbu_rates()
    if code not in rates:
        return None
    return rates[code].quantize(Decimal("0.000001")), rate_date


def current_rates() -> dict[str, Decimal]:
    """Действующие курсы для витрины — включённые валюты в порядке из админки,
    с ручными курсами и наценкой. Кэшируются."""
    rates = cache.get(RATES_CACHE_KEY)
    if rates is None:
        rates = {settings.BASE_CURRENCY: Decimal(1)}
        for item in ExchangeRate.objects.filter(is_active=True):
            effective = item.effective_rate
            if effective is not None:
                rates[item.currency] = effective
        cache.set(RATES_CACHE_KEY, rates, 60 * 10)
    return rates
