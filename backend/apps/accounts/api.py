import logging
from typing import Annotated

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django_countries import countries
from ninja import Body, Header, Router, Status
from ninja.throttling import AnonRateThrottle

from apps.catalog.api import published_products
from apps.catalog.models import Brand, Product
from apps.catalog.schemas import ProductListOut
from apps.core import telegram
from apps.orders.models import Order, OrderItem
from apps.orders.schemas import ErrorOut

from . import bot, sms, whatsapp
from .auth import COOKIE_NAME, customer_auth, set_session_cookie
from .models import (
    Address,
    CustomerSession,
    LoginRequest,
    StockAlert,
    WatchRequest,
    WishlistItem,
    hash_secret,
)
from .schemas import (
    AddressIn,
    AddressOut,
    AlertIn,
    AlertOut,
    AuthMethodsOut,
    CollectionItemOut,
    CustomerOut,
    CustomerUpdateIn,
    OrderSummaryOut,
    SlugIn,
    SlugsIn,
    SmsStartIn,
    TelegramStartOut,
    TokenOut,
    VerifyIn,
    WatchRequestIn,
    WatchRequestOut,
)
from .services import LoginError, complete_login, start_sms_login, start_whatsapp_login

logger = logging.getLogger(__name__)

auth_router = Router(tags=["auth"])
account_router = Router(tags=["account"], auth=customer_auth)
telegram_router = Router(tags=["telegram"])


# --- Вход -------------------------------------------------------------------


@auth_router.get("/methods", response=AuthMethodsOut)
def auth_methods(request):
    return {
        "telegram": telegram.is_configured() and bool(settings.TELEGRAM_BOT_USERNAME),
        "sms": sms.is_enabled(),
        "whatsapp": whatsapp.is_enabled(),
    }


@auth_router.post(
    "/telegram/start",
    response={200: TelegramStartOut, 400: ErrorOut},
    throttle=[AnonRateThrottle("30/h")],
)
def telegram_start(request):
    if not settings.TELEGRAM_BOT_USERNAME:
        return Status(400, {"detail": "Telegram login is not configured."})
    _request, token = LoginRequest.create(LoginRequest.Method.TELEGRAM)
    return {"token": token, "bot_url": bot.deep_link(token)}


@auth_router.post(
    "/sms/start", response={200: TokenOut, 400: ErrorOut}, throttle=[AnonRateThrottle("5/h")]
)
def sms_start(request, payload: SmsStartIn):
    try:
        return {"token": start_sms_login(payload.phone)}
    except LoginError as exc:
        return Status(400, {"detail": str(exc)})


@auth_router.post(
    "/whatsapp/start",
    response={200: TokenOut, 400: ErrorOut},
    throttle=[AnonRateThrottle("5/h")],
)
def whatsapp_start(request, payload: SmsStartIn):
    if not whatsapp.is_enabled():
        return Status(400, {"detail": "WhatsApp login is not configured."})
    try:
        return {"token": start_whatsapp_login(payload.phone)}
    except LoginError as exc:
        return Status(400, {"detail": str(exc)})


@auth_router.post(
    "/verify", response={200: CustomerOut, 400: ErrorOut}, throttle=[AnonRateThrottle("30/h")]
)
def verify(request: HttpRequest, response: HttpResponse, payload: VerifyIn):
    try:
        customer = complete_login(payload.token, payload.code)
    except LoginError as exc:
        return Status(400, {"detail": str(exc)})
    _session, key = CustomerSession.start(customer, request.headers.get("user-agent", ""))
    set_session_cookie(response, key)
    return customer


@auth_router.post("/logout", response={204: None})
def logout(request: HttpRequest, response: HttpResponse):
    key = request.COOKIES.get(COOKIE_NAME)
    if key:
        CustomerSession.objects.filter(key_hash=hash_secret(key)).delete()
    response.delete_cookie(COOKIE_NAME, path="/", samesite="Lax")
    return Status(204, None)


# --- Кабинет ----------------------------------------------------------------


@account_router.get("/me", response=CustomerOut)
def me(request):
    return request.auth


@account_router.patch("/me", response={200: CustomerOut, 400: ErrorOut})
def update_me(request, payload: CustomerUpdateIn):
    customer = request.auth
    if not payload.languages_ok():
        return Status(400, {"detail": "Unknown language."})
    for field, value in payload.dict(exclude_unset=True).items():
        setattr(customer, field, value if value is not None else "")
    customer.save()
    return customer


@account_router.get("/addresses", response=list[AddressOut])
def list_addresses(request):
    return request.auth.addresses.all()


@account_router.post("/addresses", response={201: AddressOut, 400: ErrorOut})
def create_address(request, payload: AddressIn):
    if payload.country.upper() not in countries:
        return Status(400, {"detail": "Unknown country."})
    customer = request.auth
    data = payload.dict()
    data["country"] = data["country"].upper()
    # Первый адрес — основной
    data["is_default"] = data["is_default"] or not customer.addresses.exists()
    return Status(201, Address.objects.create(customer=customer, **data))


@account_router.put("/addresses/{address_id}", response={200: AddressOut, 400: ErrorOut})
def update_address(request, address_id: int, payload: AddressIn):
    if payload.country.upper() not in countries:
        return Status(400, {"detail": "Unknown country."})
    address = get_object_or_404(Address, pk=address_id, customer=request.auth)
    for field, value in payload.dict().items():
        setattr(address, field, value.upper() if field == "country" else value)
    address.save()
    return address


@account_router.delete("/addresses/{address_id}", response={204: None})
def delete_address(request, address_id: int):
    get_object_or_404(Address, pk=address_id, customer=request.auth).delete()
    return Status(204, None)


@account_router.get("/orders", response=list[OrderSummaryOut])
def my_orders(request):
    return request.auth.orders.prefetch_related("items").order_by("-created_at")


# --- Вебхук Telegram ----------------------------------------------------------


@telegram_router.post("/webhook", response={200: None, 403: None})
def telegram_webhook(
    request,
    payload: Annotated[dict, Body()],
    secret: Annotated[str, Header(alias="X-Telegram-Bot-Api-Secret-Token")] = "",
):
    if not settings.TELEGRAM_WEBHOOK_SECRET or secret != settings.TELEGRAM_WEBHOOK_SECRET:
        return Status(403, None)
    try:
        bot.process_update(payload)
    except telegram.TelegramError:
        # Ответ 200 — иначе Telegram будет бесконечно повторять то же обновление
        logger.exception("Telegram update processing failed")
    return Status(200, None)


# --- Избранное ----------------------------------------------------------------


def _wishlist_products(customer):
    ids = list(customer.wishlist.values_list("product_id", flat=True))
    products = published_products().in_bulk(ids)
    return [products[pk] for pk in ids if pk in products]


def _add_to_wishlist(customer, slugs: list[str]) -> None:
    for product in Product.objects.published().filter(slug__in=slugs):
        WishlistItem.objects.get_or_create(
            customer=customer, product=product, defaults={"known_price": product.price}
        )


@account_router.get("/wishlist", response=list[ProductListOut])
def wishlist(request):
    return _wishlist_products(request.auth)


@account_router.post("/wishlist", response=list[ProductListOut])
def add_to_wishlist(request, payload: SlugIn):
    _add_to_wishlist(request.auth, [payload.slug])
    return _wishlist_products(request.auth)


@account_router.post("/wishlist/merge", response=list[ProductListOut])
def merge_wishlist(request, payload: SlugsIn):
    """Избранное, собранное до входа (хранилось в браузере), переносится в аккаунт."""
    _add_to_wishlist(request.auth, payload.slugs)
    return _wishlist_products(request.auth)


@account_router.delete("/wishlist/{slug}", response={204: None})
def remove_from_wishlist(request, slug: str):
    request.auth.wishlist.filter(product__slug=slug).delete()
    return Status(204, None)


# --- Подписки «Сообщить о поступлении» ---------------------------------------------


@account_router.get("/alerts", response=list[AlertOut])
def list_alerts(request):
    return request.auth.alerts.filter(is_active=True).select_related("product__brand", "brand")


@account_router.post("/alerts", response={201: AlertOut, 400: ErrorOut})
def create_alert(request, payload: AlertIn):
    if bool(payload.product) == bool(payload.brand):
        return Status(400, {"detail": "Specify either a product or a brand."})
    customer = request.auth
    if payload.product:
        product = get_object_or_404(Product.objects.published(), slug=payload.product)
        alert, _created = StockAlert.objects.get_or_create(
            customer=customer, product=product, is_active=True
        )
    else:
        brand = get_object_or_404(Brand, slug=payload.brand, is_active=True)
        alert, _created = StockAlert.objects.get_or_create(
            customer=customer, brand=brand, is_active=True
        )
    return Status(201, alert)


@account_router.delete("/alerts/{alert_id}", response={204: None})
def delete_alert(request, alert_id: int):
    get_object_or_404(StockAlert, pk=alert_id, customer=request.auth).delete()
    return Status(204, None)


# --- «Найдите мне часы» -----------------------------------------------------------


@account_router.get("/requests", response=list[WatchRequestOut])
def list_requests(request):
    return request.auth.watch_requests.all()


@account_router.post(
    "/requests", response={201: WatchRequestOut}, throttle=[AnonRateThrottle("10/h")]
)
def create_request(request, payload: WatchRequestIn):
    return Status(201, WatchRequest.objects.create(customer=request.auth, **payload.dict()))


# --- Моя коллекция ----------------------------------------------------------------


@account_router.get("/collection", response=list[CollectionItemOut])
def collection(request):
    """Купленные часы: позиции выполненных заказов."""
    items = (
        OrderItem.objects.filter(order__customer=request.auth, order__status=Order.Status.COMPLETED)
        .select_related("order", "product")
        .prefetch_related("product__images")
        .order_by("-order__created_at")
    )
    return [
        {
            "brand": item.brand,
            "name": item.name,
            "reference": item.reference,
            "serial_number": item.serial_number,
            "warranty_until": item.warranty_until,
            "purchased_at": item.order.created_at,
            "order_number": item.order.number,
            "order_token": item.order.token,
            "product_slug": item.product.slug if item.product else None,
            "image": item.product.images.first() if item.product else None,
        }
        for item in items
    ]
