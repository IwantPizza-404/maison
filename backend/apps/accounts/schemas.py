from datetime import date, datetime
from decimal import Decimal

from ninja import Field, Schema
from pydantic import EmailStr

from apps.catalog.schemas import ImageOut
from apps.orders.schemas import SUPPORTED_LANGUAGES


class AuthMethodsOut(Schema):
    telegram: bool
    sms: bool
    whatsapp: bool


class TelegramStartOut(Schema):
    token: str
    bot_url: str


class SmsStartIn(Schema):
    phone: str = Field(min_length=7, max_length=32)


class TokenOut(Schema):
    token: str


class VerifyIn(Schema):
    token: str = Field(max_length=64)
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class CustomerOut(Schema):
    phone: str
    name: str
    email: str
    telegram_username: str
    has_telegram: bool
    language: str
    currency: str
    notify_telegram: bool

    @staticmethod
    def resolve_has_telegram(obj) -> bool:
        return obj.telegram_id is not None


class CustomerUpdateIn(Schema):
    name: str | None = Field(None, max_length=150)
    email: EmailStr | None = None
    language: str | None = None
    currency: str | None = Field(None, max_length=3)
    notify_telegram: bool | None = None

    def languages_ok(self) -> bool:
        return self.language is None or self.language in SUPPORTED_LANGUAGES


class AddressIn(Schema):
    country: str = Field(min_length=2, max_length=2)
    city: str = Field(min_length=2, max_length=120)
    address: str = Field("", max_length=255)
    is_default: bool = False


class AddressOut(AddressIn):
    id: int

    @staticmethod
    def resolve_country(obj) -> str:
        return str(obj.country.code)


class OrderSummaryOut(Schema):
    number: str
    token: str
    status: str
    status_label: str
    created_at: datetime
    total: Decimal
    currency: str
    exchange_rate: Decimal
    items_count: int

    @staticmethod
    def resolve_status_label(obj) -> str:
        return obj.get_status_display()

    @staticmethod
    def resolve_items_count(obj) -> int:
        return sum(item.quantity for item in obj.items.all())


class SlugIn(Schema):
    slug: str = Field(max_length=220)


class SlugsIn(Schema):
    slugs: list[str] = Field(max_length=100)


class AlertIn(Schema):
    """Подписка на модель (product) или на бренд (brand) — что-то одно."""

    product: str | None = Field(None, max_length=220)
    brand: str | None = Field(None, max_length=140)


class AlertOut(Schema):
    id: int
    kind: str
    product_slug: str | None
    brand_slug: str | None
    title: str
    created_at: datetime
    notified_at: datetime | None

    @staticmethod
    def resolve_kind(obj) -> str:
        return "product" if obj.product_id else "brand"

    @staticmethod
    def resolve_product_slug(obj) -> str | None:
        return obj.product.slug if obj.product_id else None

    @staticmethod
    def resolve_brand_slug(obj) -> str | None:
        return obj.brand.slug if obj.brand_id else None

    @staticmethod
    def resolve_title(obj) -> str:
        if obj.product_id:
            return f"{obj.product.brand.name} {obj.product.name}"
        return obj.brand.name


class WatchRequestIn(Schema):
    brand: str = Field(min_length=2, max_length=120)
    model: str = Field("", max_length=150)
    reference: str = Field("", max_length=80)
    condition: str = Field("any", pattern="^(any|new|pre_owned)$")
    budget: Decimal | None = Field(None, gt=0, max_digits=12, decimal_places=2)
    comment: str = Field("", max_length=2000)


class WatchRequestOut(Schema):
    id: int
    brand: str
    model: str
    reference: str
    condition: str
    budget: Decimal | None
    comment: str
    status: str
    status_label: str
    reply: str
    created_at: datetime

    @staticmethod
    def resolve_status_label(obj) -> str:
        return obj.get_status_display()


class CollectionItemOut(Schema):
    brand: str
    name: str
    reference: str
    serial_number: str
    warranty_until: date | None
    purchased_at: datetime
    order_number: str
    order_token: str
    product_slug: str | None
    image: ImageOut | None
