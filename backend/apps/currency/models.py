from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class ExchangeRate(models.Model):
    """Валюта отображения цен и её курс к базовой (USD): сколько единиц валюты за 1 USD.

    Валюты добавляются в админке. Курс подтягивается из ЦБ Узбекистана автоматически,
    если ЦБ его публикует; иначе — только ручной курс. Наценка — на конвертацию.
    """

    currency = models.CharField(
        _("currency"),
        max_length=3,
        unique=True,
        validators=[RegexValidator(r"^[A-Z]{3}$", _("Three-letter ISO code, e.g. AED."))],
        help_text=_("Three-letter ISO code: EUR, RUB, AED, KZT…"),
    )
    rate = models.DecimalField(
        _("official rate"),
        max_digits=18,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.000001"))],
        help_text=_("Units of currency per 1 USD, updated automatically."),
    )
    manual_rate = models.DecimalField(
        _("manual rate"),
        max_digits=18,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.000001"))],
        help_text=_("If set, used instead of the official rate."),
    )
    markup_percent = models.DecimalField(
        _("markup, %"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Added to the rate, e.g. to cover conversion costs."),
    )
    is_active = models.BooleanField(
        _("shown on the site"), default=True, help_text=_("Available in the currency switcher.")
    )
    position = models.PositiveIntegerField(_("position"), default=0, db_index=True)
    rate_date = models.DateField(_("rate date"), null=True, blank=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("exchange rate")
        verbose_name_plural = _("exchange rates")
        ordering = ["position", "currency"]

    def __str__(self) -> str:
        return f"1 USD = {self.effective_rate or '—'} {self.currency}"

    def clean(self) -> None:
        self.currency = (self.currency or "").strip().upper()
        if self.currency == settings.BASE_CURRENCY:
            raise ValidationError(
                {"currency": _("%(code)s is the base currency.") % {"code": self.currency}}
            )
        if self.rate is None and self.manual_rate is None:
            raise ValidationError(
                {
                    "manual_rate": _(
                        "The Central Bank does not publish this currency — set the rate manually."
                    )
                }
            )

    @property
    def effective_rate(self) -> Decimal | None:
        base = self.manual_rate if self.manual_rate is not None else self.rate
        if base is None:
            return None
        rate = base * (1 + self.markup_percent / 100)
        return rate.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
