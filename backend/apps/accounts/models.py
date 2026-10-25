import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from django_countries import countries
from django_countries.fields import CountryField

SESSION_TTL = timedelta(days=90)
LOGIN_TTL = timedelta(minutes=10)
LOGIN_MAX_ATTEMPTS = 5


def hash_secret(value: str) -> str:
    """В базе храним только хэши токенов и кодов: утечка базы не даёт войти."""
    return hashlib.sha256(value.encode()).hexdigest()


def normalize_phone(phone: str) -> str:
    """+998 (90) 123-45-67 → +998901234567. Узбекский номер без кода страны дополняем 998."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 9:
        digits = "998" + digits
    return f"+{digits}" if digits else ""


class Customer(models.Model):
    """Покупатель сайта. Отдельно от пользователей админки (сотрудников)."""

    phone = models.CharField(_("phone"), max_length=20, unique=True)
    telegram_id = models.BigIntegerField(_("Telegram ID"), unique=True, null=True, blank=True)
    telegram_username = models.CharField(_("Telegram username"), max_length=64, blank=True)
    name = models.CharField(_("name"), max_length=150, blank=True)
    email = models.EmailField(_("email"), blank=True)
    language = models.CharField(
        _("language"), max_length=8, choices=settings.LANGUAGES, default="ru"
    )
    currency = models.CharField(_("currency"), max_length=3, default="USD")
    notify_telegram = models.BooleanField(
        _("Telegram notifications"),
        default=True,
        help_text=_("Order status, back in stock and price drop messages."),
    )
    created_at = models.DateTimeField(_("registered"), auto_now_add=True)
    last_login_at = models.DateTimeField(_("last login"), null=True, blank=True)

    class Meta:
        verbose_name = _("customer")
        verbose_name_plural = _("customers")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.phone})" if self.name else self.phone

    @property
    def can_receive_telegram(self) -> bool:
        return bool(self.telegram_id and self.notify_telegram)


class Address(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="addresses")
    country = CountryField(_("country"))
    city = models.CharField(_("city"), max_length=120)
    address = models.CharField(_("address"), max_length=255, blank=True)
    is_default = models.BooleanField(_("default"), default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("address")
        verbose_name_plural = _("addresses")
        ordering = ["-is_default", "-created_at"]

    def __str__(self) -> str:
        return ", ".join(filter(None, [countries.name(self.country), self.city, self.address]))

    def save(self, *args, **kwargs) -> None:
        super().save(*args, **kwargs)
        if self.is_default:
            self.customer.addresses.exclude(pk=self.pk).update(is_default=False)


class CustomerSession(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="sessions")
    key_hash = models.CharField(max_length=64, unique=True)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        verbose_name = _("session")
        verbose_name_plural = _("sessions")

    def __str__(self) -> str:
        return f"{self.customer} · {self.created_at:%Y-%m-%d}"

    @classmethod
    def start(cls, customer: Customer, user_agent: str = "") -> tuple["CustomerSession", str]:
        """Новая сессия. Возвращает и запись, и ключ для cookie (в базе — только хэш)."""
        key = secrets.token_urlsafe(32)
        session = cls.objects.create(
            customer=customer,
            key_hash=hash_secret(key),
            user_agent=user_agent[:255],
            expires_at=timezone.now() + SESSION_TTL,
        )
        return session, key

    @classmethod
    def customer_for(cls, key: str | None) -> Customer | None:
        if not key:
            return None
        session = (
            cls.objects.select_related("customer")
            .filter(key_hash=hash_secret(key), expires_at__gt=timezone.now())
            .first()
        )
        return session.customer if session else None


class LoginRequest(models.Model):
    """Попытка входа: покупатель получает 6-значный код (в Telegram, SMS или WhatsApp)
    и вводит его на сайте.

    Код вводится в том браузере, где начат вход, — поэтому чужая ссылка на бота
    не даёт злоумышленнику войти в аккаунт жертвы.
    """

    class Method(models.TextChoices):
        TELEGRAM = "telegram", "Telegram"
        SMS = "sms", "SMS"
        WHATSAPP = "whatsapp", "WhatsApp"

    method = models.CharField(max_length=16, choices=Method.choices)
    token_hash = models.CharField(max_length=64, unique=True)
    phone = models.CharField(max_length=20, blank=True)
    telegram_id = models.BigIntegerField(null=True, blank=True)
    code_hash = models.CharField(max_length=64, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("login request")
        verbose_name_plural = _("login requests")

    def __str__(self) -> str:
        return f"{self.method} · {self.phone or '—'}"

    @classmethod
    def create(cls, method: str, phone: str = "") -> tuple["LoginRequest", str]:
        token = secrets.token_urlsafe(24)
        request = cls.objects.create(
            method=method,
            token_hash=hash_secret(token),
            phone=phone,
            expires_at=timezone.now() + LOGIN_TTL,
        )
        return request, token

    @classmethod
    def active(cls, token: str) -> "LoginRequest | None":
        return cls.objects.filter(
            token_hash=hash_secret(token), used_at__isnull=True, expires_at__gt=timezone.now()
        ).first()

    @classmethod
    def active_by_id(cls, pk: int) -> "LoginRequest | None":
        return cls.objects.filter(
            pk=pk, used_at__isnull=True, expires_at__gt=timezone.now()
        ).first()

    def issue_code(self) -> str:
        code = f"{secrets.randbelow(1_000_000):06d}"
        self.code_hash = hash_secret(code)
        self.attempts = 0
        self.save(update_fields=["code_hash", "attempts"])
        return code

    def check_code(self, code: str) -> bool:
        """Не более LOGIN_MAX_ATTEMPTS попыток — перебор 6-значного кода невозможен."""
        # Атомарный инкремент в базе: параллельные запросы не обходят лимит
        updated = LoginRequest.objects.filter(pk=self.pk, attempts__lt=LOGIN_MAX_ATTEMPTS).update(
            attempts=models.F("attempts") + 1
        )
        if not self.code_hash or not updated:
            return False
        return secrets.compare_digest(self.code_hash, hash_secret(code.strip()))


class WishlistItem(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="wishlist")
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="+")
    # Цена, о которой покупатель уже знает: уведомляем, только если новая цена ниже
    known_price = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("favourite")
        verbose_name_plural = _("favourites")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["customer", "product"], name="uniq_wishlist_item"),
        ]

    def __str__(self) -> str:
        return str(self.product)


class StockAlert(models.Model):
    """«Сообщить о поступлении»: на модель (один раз) или на бренд (каждое поступление)."""

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="alerts")
    product = models.ForeignKey(
        "catalog.Product",
        verbose_name=_("product"),
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )
    brand = models.ForeignKey(
        "catalog.Brand",
        verbose_name=_("brand"),
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    notified_at = models.DateTimeField(_("last notification"), null=True, blank=True)

    class Meta:
        verbose_name = _("stock alert")
        verbose_name_plural = _("stock alerts")
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(product__isnull=False, brand__isnull=True)
                | models.Q(product__isnull=True, brand__isnull=False),
                name="stockalert_product_xor_brand",
            ),
            models.UniqueConstraint(
                fields=["customer", "product"],
                condition=models.Q(is_active=True),
                name="uniq_active_product_alert",
            ),
            models.UniqueConstraint(
                fields=["customer", "brand"],
                condition=models.Q(is_active=True),
                name="uniq_active_brand_alert",
            ),
        ]

    def __str__(self) -> str:
        return str(self.product or self.brand)


class WatchRequest(models.Model):
    """«Найдите мне часы»: заявка на модель, которой нет в каталоге."""

    class Status(models.TextChoices):
        NEW = "new", pgettext_lazy("watch request", "New")
        SEARCHING = "searching", _("Searching")
        OFFERED = "offered", _("Offer sent")
        CLOSED = "closed", _("Closed")

    class Condition(models.TextChoices):
        ANY = "any", _("Any")
        NEW = "new", pgettext_lazy("watch condition", "New")
        PRE_OWNED = "pre_owned", _("Pre-owned")

    customer = models.ForeignKey(
        Customer,
        verbose_name=_("customer"),
        on_delete=models.CASCADE,
        related_name="watch_requests",
    )
    brand = models.CharField(_("brand"), max_length=120)
    model = models.CharField(_("model"), max_length=150, blank=True)
    reference = models.CharField(_("reference"), max_length=80, blank=True)
    condition = models.CharField(
        _("condition"), max_length=16, choices=Condition.choices, default=Condition.ANY
    )
    budget = models.DecimalField(
        _("budget, USD"), max_digits=12, decimal_places=2, null=True, blank=True
    )
    comment = models.TextField(_("comment"), blank=True)
    status = models.CharField(
        _("status"), max_length=16, choices=Status.choices, default=Status.NEW, db_index=True
    )
    reply = models.TextField(
        _("reply to customer"),
        blank=True,
        help_text=_("Visible to the customer and sent to Telegram."),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("watch request")
        verbose_name_plural = _("watch requests")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return " ".join(filter(None, [self.brand, self.model, self.reference]))
