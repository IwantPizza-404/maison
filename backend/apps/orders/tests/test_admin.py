import re

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse

from apps.catalog.models import Product
from apps.orders.models import Order
from apps.orders.services import Customer, place_order

pytestmark = pytest.mark.django_db


@pytest.fixture
def order(watch, pickup) -> Order:
    return place_order(
        items={"watch": 1},
        customer=Customer(
            name="Aziz", phone="+998901234567", contact_method="telegram", country="UZ", city="T"
        ),
        delivery_code="pickup-tashkent",
        currency="USD",
        language="ru",
    )


@pytest.fixture
def admin_client(client, django_user_model):
    client.force_login(django_user_model.objects.create_superuser("a", "a@maison.uz", "p"))
    return client


def change(admin_client, order: Order, **data):
    url = reverse("admin:orders_order_change", args=[order.pk])
    form = {"tracking_number": "", "manager_note": "", "delivery_price": "", **data}
    # Инлайн позиций в форме — только для чтения, но management form обязателен
    form.update({"items-TOTAL_FORMS": "0", "items-INITIAL_FORMS": "0"})
    return admin_client.post(url, form)


def press(admin_client, order: Order, button: str, **data):
    """Кнопка перехода в нижней панели заказа."""
    return change(admin_client, order, **{f"orders_order_{button}": "", **data})


def move(admin_client, order: Order, status: str, **data):
    """Перенос карточки на доске заказов."""
    return admin_client.post(
        reverse("admin:orders_order_board_move"), {"order": order.pk, "status": status, **data}
    )


def test_cancel_button_returns_stock(admin_client, order, watch):
    response = press(admin_client, order, "to_cancelled")

    assert response.status_code == 302
    assert response.url == reverse("admin:orders_order_change", args=[order.pk])
    order.refresh_from_db()
    watch.refresh_from_db()
    assert order.status == Order.Status.CANCELLED
    assert watch.availability == Product.Availability.IN_STOCK


def test_admin_offers_only_allowed_transitions(admin_client, order):
    html = admin_client.get(reverse("admin:orders_order_change", args=[order.pk])).content.decode()

    assert 'name="orders_order_to_confirmed"' in html
    assert 'name="orders_order_to_cancelled"' in html
    assert 'name="orders_order_to_shipped"' not in html


def test_status_cannot_be_changed_through_form(admin_client, order):
    change(admin_client, order, status="cancelled")

    order.refresh_from_db()
    assert order.status == Order.Status.NEW


def test_transition_saves_form_first(admin_client, order):
    order.status = Order.Status.PAID
    order.save()

    press(admin_client, order, "to_shipped", tracking_number="BTS123")

    order.refresh_from_db()
    assert order.status == Order.Status.SHIPPED
    assert order.tracking_number == "BTS123"


def test_skipping_a_step_is_rejected(admin_client, order):
    press(admin_client, order, "to_shipped")

    order.refresh_from_db()
    assert order.status == Order.Status.NEW


def test_manager_sets_delivery_price(admin_client, order):
    change(admin_client, order, delivery_price="25")

    order.refresh_from_db()
    assert order.total == order.subtotal + 25


def test_board_shows_orders_by_status(admin_client, order):
    response = admin_client.get(reverse("admin:orders_order_board"))

    assert response.status_code == 200
    assert order.number in response.content.decode()


def test_board_moves_order(admin_client, order):
    response = move(admin_client, order, "confirmed")

    assert response.status_code == 200
    assert response.json()["allowed"] == ["cancelled", "paid"]
    order.refresh_from_db()
    assert order.status == Order.Status.CONFIRMED


def test_board_ships_with_tracking_number(admin_client, order):
    order.status = Order.Status.PAID
    order.save()

    move(admin_client, order, "shipped", tracking_number=" BTS777 ")

    order.refresh_from_db()
    assert order.status == Order.Status.SHIPPED
    assert order.tracking_number == "BTS777"


def test_board_rejects_invalid_transition(admin_client, order):
    response = move(admin_client, order, "completed")

    assert response.status_code == 400
    assert response.json()["error"]
    order.refresh_from_db()
    assert order.status == Order.Status.NEW


def test_board_move_requires_change_permission(client, django_user_model, order):
    viewer = django_user_model.objects.create_user("v", "v@maison.uz", "p", is_staff=True)
    viewer.user_permissions.add(Permission.objects.get(codename="view_order"))
    client.force_login(viewer)

    assert client.get(reverse("admin:orders_order_board")).status_code == 200
    assert move(client, order, "confirmed").status_code == 403
    order.refresh_from_db()
    assert order.status == Order.Status.NEW


@pytest.mark.parametrize(
    ("url", "active"),
    [
        ("admin:orders_order_changelist", "/admin/orders/order/"),
        ("admin:orders_order_board", "/admin/orders/order/board/"),
    ],
)
def test_only_one_orders_menu_item_is_active(admin_client, url, active):
    html = admin_client.get(reverse(url)).content.decode()

    assert re.findall(r'<a href="(/admin/orders/[^"]+)" class="[^"]* active"', html) == [active]
