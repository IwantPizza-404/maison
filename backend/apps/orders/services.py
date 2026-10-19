"""Корзина и заказы: расчёт, оформление с резервом остатков, смена статусов."""

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils.translation import gettext as _

from apps.catalog.models import Product
from apps.currency.services import current_rates

from .models import DeliveryMethod, Order, OrderItem

if TYPE_CHECKING:
    from apps.accounts.models import Customer as CustomerAccount

logger = logging.getLogger(__name__)

# Под заказ одну модель редко берут больше нескольких штук
MAX_ON_ORDER_QUANTITY = 5


class OrderError(Exception):
    """Ошибка оформления, которую можно показать покупателю."""


@dataclass
class CartLine:
    product: Product | None
    slug: str
    quantity: int
    max_quantity: int = 0
    error: str | None = None

    @property
    def line_total(self) -> Decimal:
        return self.product.price * self.quantity if self.product and not self.error else Decimal(0)


@dataclass
class Quote:
    lines: list[CartLine] = field(default_factory=list)

    @property
    def subtotal(self) -> Decimal:
        return sum((line.line_total for line in self.lines), Decimal(0))

    @property
    def is_valid(self) -> bool:
        return bool(self.lines) and all(line.error is None for line in self.lines)


def max_quantity(product: Product) -> int:
    if product.availability == Product.Availability.IN_STOCK:
        return product.stock_quantity
    if product.availability == Product.Availability.ON_ORDER:
        return MAX_ON_ORDER_QUANTITY
    return 0


def build_quote(items: dict[str, int], *, lock: bool = False) -> Quote:
    """Проверяет позиции корзины по актуальным ценам и наличию.

    lock=True блокирует строки товаров до конца транзакции — чтобы два покупателя
    не купили последний экземпляр одновременно.
    """
    queryset = Product.objects.published().select_related("brand")
    if lock:
        queryset = queryset.select_for_update(of=("self",))
    products = {p.slug: p for p in queryset.filter(slug__in=items)}

    quote = Quote()
    for slug, quantity in items.items():
        product = products.get(slug)
        line = CartLine(product=product, slug=slug, quantity=quantity)
        if product is None:
            line.error = _("This item is no longer available.")
        else:
            line.max_quantity = max_quantity(product)
            if line.max_quantity == 0:
                line.error = _("Sold out.")
            elif quantity > line.max_quantity:
                line.error = _("Only %(n)s available.") % {"n": line.max_quantity}
        quote.lines.append(line)
    return quote


@dataclass
class Customer:
    name: str
    phone: str
    contact_method: str
    country: str
    city: str
    email: str = ""
    address: str = ""
    comment: str = ""


@transaction.atomic
def place_order(
    *,
    items: dict[str, int],
    customer: Customer,
    delivery_code: str,
    currency: str,
    language: str,
    account: "CustomerAccount | None" = None,
    save_address: bool = False,
) -> Order:
    if not items:
        raise OrderError(_("The cart is empty."))

    delivery = DeliveryMethod.objects.filter(code=delivery_code, is_active=True).first()
    if delivery is None or not delivery.is_available_for(customer.country):
        raise OrderError(_("This delivery method is not available for the selected country."))

    quote = build_quote(items, lock=True)
    if not quote.is_valid:
        raise OrderError(_("Some items in the cart have changed. Please review the cart."))

    rates = current_rates()
    if currency not in rates:
        currency = "USD"

    subtotal = quote.subtotal
    order = Order.objects.create(
        customer=account,
        customer_name=customer.name,
        phone=customer.phone,
        email=customer.email,
        contact_method=customer.contact_method,
        country=customer.country,
        city=customer.city,
        address=customer.address,
        comment=customer.comment,
        delivery_method=delivery,
        delivery_price=delivery.price,
        subtotal=subtotal,
        total=subtotal + (delivery.price or 0),
        currency=currency,
        exchange_rate=rates[currency],
        language=language,
    )

    for line in quote.lines:
        product = line.product
        assert product is not None  # гарантировано quote.is_valid
        on_order = product.availability == Product.Availability.ON_ORDER
        OrderItem.objects.create(
            order=order,
            product=product,
            brand=product.brand.name,
            name=product.name,
            reference=product.reference,
            price=product.price,
            quantity=line.quantity,
            on_order=on_order,
            lead_time_days=product.lead_time_days if on_order else None,
        )
        if not on_order:
            reserve_stock(product, line.quantity)

    if account is not None and save_address:
        remember_address(account, customer)

    transaction.on_commit(lambda: notify_new_order(order.pk))
    return order


def remember_address(account: "CustomerAccount", customer: Customer) -> None:
    """Сохраняет адрес из заказа в кабинет, если такого ещё нет."""
    from apps.accounts.models import Address

    exists = account.addresses.filter(
        country=customer.country, city__iexact=customer.city, address__iexact=customer.address
    ).exists()
    if not exists:
        Address.objects.create(
            customer=account,
            country=customer.country,
            city=customer.city,
            address=customer.address,
            is_default=not account.addresses.exists(),
        )


def reserve_stock(product: Product, quantity: int) -> None:
    product.stock_quantity -= quantity
    if product.stock_quantity == 0:
        product.availability = Product.Availability.SOLD_OUT
    product.save(update_fields=["stock_quantity", "availability", "updated_at"])


def release_stock(order: Order) -> None:
    """Возвращает на склад товары отменённого заказа (кроме позиций под заказ)."""
    items = list(order.items.filter(on_order=False, product__isnull=False))
    products = Product.objects.select_for_update().in_bulk(
        [item.product_id for item in items if item.product_id]
    )
    for item in items:
        product = products.get(item.product_id) if item.product_id else None
        if product is None:
            continue
        product.stock_quantity += item.quantity
        if product.availability == Product.Availability.SOLD_OUT:
            product.availability = Product.Availability.IN_STOCK
        product.save(update_fields=["stock_quantity", "availability", "updated_at"])


@transaction.atomic
def change_status(order: Order, status: str, *, tracking_number: str | None = None) -> None:
    """Переводит заказ в следующий статус. Трек-номер можно передать вместе с отправкой —
    тогда он попадёт в уведомление покупателю."""
    if not order.can_change_to(status):
        raise OrderError(
            _("Cannot change status from “%(from)s” to “%(to)s”.")
            % {"from": order.get_status_display(), "to": Order.Status(status).label}
        )
    if status == Order.Status.CANCELLED:
        release_stock(order)
    order.status = status
    update_fields = ["status", "updated_at"]
    if tracking_number is not None:
        order.tracking_number = tracking_number.strip()
        update_fields.append("tracking_number")
    order.save(update_fields=update_fields)
    if order.customer_id:
        from apps.accounts.tasks import notify_order_status

        transaction.on_commit(lambda: notify_order_status.delay(order.pk))


def notify_new_order(order_id: int) -> None:
    from .tasks import send_order_notification

    send_order_notification.delay(order_id)
