import io
from decimal import Decimal

import pytest
from django.urls import reverse
from openpyxl import load_workbook

from apps.accounts.models import Address, Customer
from apps.catalog.tests.factories import ProductFactory
from apps.orders.models import Order
from apps.orders.services import Customer as OrderCustomer
from apps.orders.services import change_status, place_order

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(client, django_user_model):
    client.force_login(django_user_model.objects.create_superuser("a", "a@maison.uz", "p"))
    return client


def order_for(customer: Customer, price: int) -> Order:
    product = ProductFactory(price=Decimal(price), stock_quantity=1)
    return place_order(
        items={str(product.slug): 1},
        customer=OrderCustomer(
            name="Aziz", phone=customer.phone, contact_method="telegram", country="UZ", city="T"
        ),
        delivery_code="pickup-tashkent",
        currency="USD",
        language="ru",
        account=customer,
    )


def rows(content: bytes) -> list[tuple]:
    return list(load_workbook(io.BytesIO(content)).active.values)


def test_export_all_customers_with_order_totals(admin_client):
    customer = Customer.objects.create(phone="+998901112233", name="Aziz", telegram_username="aziz")
    Address.objects.create(customer=customer, country="UZ", city="Tashkent", is_default=True)
    order_for(customer, 1000)
    change_status(order_for(customer, 500), Order.Status.CANCELLED)
    Customer.objects.create(phone="+998909998877")

    response = admin_client.get(reverse("admin:accounts_customer_export_all"))

    assert response.status_code == 200
    table = rows(response.content)
    assert len(table) == 3
    aziz = next(row for row in table[1:] if row[0] == "+998901112233")
    assert aziz[1] == "Aziz"
    assert aziz[3] == "@aziz"
    assert (aziz[9], aziz[10]) == (1, 1000)  # отменённый заказ не считается
    assert "Tashkent" in aziz[11]


def test_export_selected_customers(admin_client):
    keep = Customer.objects.create(phone="+998901112233")
    Customer.objects.create(phone="+998909998877")

    response = admin_client.post(
        reverse("admin:accounts_customer_changelist"),
        {"action": "export_selected", "_selected_action": [keep.pk]},
    )

    assert [row[0] for row in rows(response.content)[1:]] == ["+998901112233"]
