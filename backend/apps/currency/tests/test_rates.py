from datetime import date
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.urls import reverse

from apps.currency import services
from apps.currency.models import ExchangeRate
from apps.currency.services import RatesFetchError, current_rates, parse_cbu, update_rates

CBU_PAYLOAD = [
    {"Ccy": "USD", "Nominal": "1", "Rate": "12000.00", "Date": "10.10.2026"},
    {"Ccy": "EUR", "Nominal": "1", "Rate": "13000.00", "Date": "10.10.2026"},
    {"Ccy": "RUB", "Nominal": "1", "Rate": "150.00", "Date": "10.10.2026"},
    {"Ccy": "JPY", "Nominal": "10", "Rate": "800.00", "Date": "10.10.2026"},
]


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()


def test_parse_cbu_converts_to_units_per_usd():
    rates, rate_date = parse_cbu(CBU_PAYLOAD)

    assert rates["USD"] == 1
    assert rates["UZS"] == Decimal("12000")
    assert rates["RUB"] == Decimal("80")  # 12000 / 150
    assert rates["JPY"] == Decimal("150")  # номинал 10: 12000 / (800 / 10)
    assert rate_date == date(2026, 10, 10)


def test_parse_cbu_without_usd_fails():
    with pytest.raises(RatesFetchError):
        parse_cbu([{"Ccy": "EUR", "Nominal": "1", "Rate": "13000", "Date": "10.10.2026"}])


def test_effective_rate_uses_manual_rate_and_markup():
    rate = ExchangeRate(currency="UZS", rate=Decimal("12000"), markup_percent=Decimal("1.5"))
    assert rate.effective_rate == Decimal("12180")

    rate.manual_rate = Decimal("12500")
    assert rate.effective_rate == Decimal("12687.5")


def set_rate(code: str, **fields) -> ExchangeRate:
    # UZS, EUR и RUB создаёт миграция — обновляем, а не создаём
    item, _created = ExchangeRate.objects.update_or_create(currency=code, defaults=fields)
    return item


@pytest.fixture
def cbu(monkeypatch):
    monkeypatch.setattr(services, "fetch_cbu_rates", lambda: parse_cbu(CBU_PAYLOAD))


@pytest.mark.django_db
def test_update_rates_updates_currencies_from_admin(cbu):
    set_rate("AED", manual_rate=Decimal("3.67"))  # у ЦБ нет — остаётся ручной курс

    assert sorted(update_rates()) == ["EUR", "RUB", "UZS"]
    assert ExchangeRate.objects.get(currency="RUB").rate == Decimal("80")
    assert ExchangeRate.objects.get(currency="AED").rate is None
    assert not ExchangeRate.objects.filter(currency="USD").exists()


@pytest.mark.django_db
def test_update_rates_keeps_manual_settings(monkeypatch):
    set_rate("UZS", rate=1, manual_rate=Decimal("12500"))
    monkeypatch.setattr(services, "fetch_cbu_rates", lambda: parse_cbu(CBU_PAYLOAD))

    update_rates()

    rate = ExchangeRate.objects.get(currency="UZS")
    assert rate.rate == Decimal("12000")
    assert rate.manual_rate == Decimal("12500")


@pytest.mark.django_db
def test_admin_change_resets_cached_rates():
    item = set_rate("UZS", rate=Decimal("12000"))
    assert current_rates()["UZS"] == Decimal("12000")

    item.markup_percent = Decimal("10")
    item.save()

    assert current_rates()["UZS"] == Decimal("13200")


@pytest.mark.django_db
def test_rates_api(client):
    set_rate("UZS", rate=Decimal("12000"))

    data = client.get("/api/v1/currency/rates").json()

    assert data["base"] == "USD"
    assert Decimal(data["rates"]["UZS"]) == Decimal("12000")
    assert Decimal(data["rates"]["USD"]) == 1


@pytest.mark.django_db
def test_site_gets_active_currencies_with_rate_in_admin_order():
    set_rate("UZS", rate=Decimal("12000"), position=2)
    set_rate("EUR", rate=Decimal("0.9"), position=1)
    set_rate("RUB", rate=Decimal("80"), is_active=False)
    set_rate("AED", position=0)  # ещё без курса

    assert list(current_rates()) == ["USD", "EUR", "UZS"]


@pytest.fixture
def admin_client(client, django_user_model):
    client.force_login(django_user_model.objects.create_superuser("a", "a@maison.uz", "p"))
    return client


def add_currency(admin_client, **data):
    form = {"currency": "", "is_active": "on", "manual_rate": "", "markup_percent": "0", **data}
    return admin_client.post(reverse("admin:currency_exchangerate_add"), form)


@pytest.mark.django_db
def test_admin_adds_currency_with_central_bank_rate(admin_client, cbu):
    response = add_currency(admin_client, currency="jpy")

    assert response.status_code == 302
    item = ExchangeRate.objects.get(currency="JPY")
    assert item.rate == Decimal("150")
    assert current_rates()["JPY"] == Decimal("150")


@pytest.mark.django_db
def test_admin_requires_manual_rate_when_central_bank_has_none(admin_client, cbu):
    response = add_currency(admin_client, currency="AED")

    assert response.status_code == 200
    assert "manual_rate" in response.context["adminform"].form.errors
    assert add_currency(admin_client, currency="AED", manual_rate="3.67").status_code == 302
    assert current_rates()["AED"] == Decimal("3.67")


@pytest.mark.django_db
def test_admin_rejects_base_currency_and_bad_codes(admin_client, cbu):
    for code in ("USD", "DOLLAR", "1AB"):
        response = add_currency(admin_client, currency=code, manual_rate="1")

        assert response.status_code == 200, code
        assert "currency" in response.context["adminform"].form.errors


@pytest.mark.django_db
def test_new_currency_goes_to_the_end_of_the_switcher(admin_client, cbu):
    add_currency(admin_client, currency="JPY")

    assert list(current_rates())[-1] == "JPY"
