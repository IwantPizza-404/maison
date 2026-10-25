from decimal import Decimal

import pytest

from apps.catalog.models import Product
from apps.currency.models import ExchangeRate
from apps.orders.models import DeliveryMethod, Order
from apps.orders.services import Customer, OrderError, build_quote, change_status, place_order

pytestmark = pytest.mark.django_db

CUSTOMER = Customer(
    name="Aziz", phone="+998901234567", contact_method="telegram", country="UZ", city="Tashkent"
)


def order(items, *, customer=CUSTOMER, delivery="pickup-tashkent", currency="USD") -> Order:
    return place_order(
        items=items, customer=customer, delivery_code=delivery, currency=currency, language="ru"
    )


def test_order_reserves_last_item_and_marks_sold_out(watch):
    created = order({"watch": 1})

    watch.refresh_from_db()
    assert watch.stock_quantity == 0
    assert watch.availability == Product.Availability.SOLD_OUT
    assert created.number.startswith("MS-")
    assert created.items.get().price == Decimal("1000")


def test_second_customer_cannot_buy_sold_out_item(watch):
    order({"watch": 1})

    with pytest.raises(OrderError):
        order({"watch": 1})


def test_quantity_above_stock_is_rejected(watch):
    quote = build_quote({"watch": 2})

    assert not quote.is_valid
    assert quote.lines[0].max_quantity == 1


def test_on_order_item_does_not_touch_stock(on_order_watch):
    created = order({"on-order": 2})

    on_order_watch.refresh_from_db()
    assert on_order_watch.availability == Product.Availability.ON_ORDER
    item = created.items.get()
    assert item.on_order and item.lead_time_days == 14


def test_cancel_returns_item_to_stock(watch):
    created = order({"watch": 1})

    change_status(created, Order.Status.CANCELLED)

    watch.refresh_from_db()
    assert watch.stock_quantity == 1
    assert watch.availability == Product.Availability.IN_STOCK


def test_status_transitions_are_enforced(watch):
    created = order({"watch": 1})

    with pytest.raises(OrderError):
        change_status(created, Order.Status.SHIPPED)

    change_status(created, Order.Status.CONFIRMED)
    change_status(created, Order.Status.PAID)
    change_status(created, Order.Status.SHIPPED)
    with pytest.raises(OrderError):
        change_status(created, Order.Status.CANCELLED)


def test_tracking_number_saved_with_shipping(watch):
    created = order({"watch": 1})
    change_status(created, Order.Status.CONFIRMED)
    change_status(created, Order.Status.PAID)

    change_status(created, Order.Status.SHIPPED, tracking_number=" BTS42 ")

    created.refresh_from_db()
    assert created.tracking_number == "BTS42"


def test_international_delivery_only_outside_uzbekistan(watch):
    with pytest.raises(OrderError):
        order({"watch": 1}, delivery="bts-international")

    abroad = Customer(**{**CUSTOMER.__dict__, "country": "AE", "city": "Dubai"})
    with pytest.raises(OrderError):
        order({"watch": 1}, customer=abroad, delivery="pickup-tashkent")

    assert order({"watch": 1}, customer=abroad, delivery="bts-international").country == "AE"


def test_inactive_delivery_method_is_rejected(watch):
    DeliveryMethod.objects.filter(code="pickup-tashkent").update(is_active=False)

    with pytest.raises(OrderError):
        order({"watch": 1})


def test_order_snapshots_exchange_rate(watch):
    ExchangeRate.objects.update_or_create(currency="UZS", defaults={"rate": Decimal("12000")})

    created = order({"watch": 1}, currency="UZS")

    assert created.exchange_rate == Decimal("12000")
    assert created.total_in_currency == Decimal("12000000")
    created.exchange_rate = Decimal("11897.9")  # 11 897 900 → округление до тысяч, как на сайте
    assert created.total_in_currency == Decimal("11898000")


def test_manager_delivery_price_updates_total(watch):
    created = order({"watch": 1}, delivery="courier-tashkent")
    assert created.delivery_price is None and created.total == Decimal("1000")

    created.delivery_price = Decimal("15")
    created.save(update_fields=["delivery_price"])
    created.refresh_from_db()

    assert created.total == Decimal("1015")


def test_failed_order_does_not_reserve_stock(watch, on_order_watch):
    # Одна позиция невалидна — весь заказ откатывается
    with pytest.raises(OrderError):
        order({"watch": 1, "on-order": 99})

    watch.refresh_from_db()
    assert watch.stock_quantity == 1
    assert not Order.objects.exists()
