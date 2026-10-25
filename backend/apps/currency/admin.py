from django import forms
from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.decorators import action, display

from .models import ExchangeRate
from .services import RatesFetchError, official_rate, update_rates


class ExchangeRateForm(forms.ModelForm):
    class Meta:
        model = ExchangeRate
        fields = ("currency", "is_active", "manual_rate", "markup_percent")

    def clean_currency(self) -> str:
        return (self.cleaned_data.get("currency") or "").strip().upper()

    def clean(self):
        cleaned = super().clean()
        # Новая валюта: официальный курс берём из ЦБ сразу (clean идёт до проверки модели) —
        # ручной курс нужен, только если ЦБ эту валюту не публикует
        code = cleaned.get("currency") if cleaned else None
        if code and not self.instance.pk and self.instance.rate is None:
            try:
                found = official_rate(code)
            except RatesFetchError:
                found = None
            if found:
                self.instance.rate, self.instance.rate_date = found
        return cleaned


@admin.register(ExchangeRate)
class ExchangeRateAdmin(ModelAdmin):
    form = ExchangeRateForm
    list_display = (
        "currency",
        "effective",
        "rate",
        "manual_rate",
        "markup_percent",
        "is_active",
        "rate_date",
    )
    list_editable = ("manual_rate", "markup_percent", "is_active")
    readonly_fields = ("rate", "rate_date", "updated_at")
    fields = (
        "currency",
        "is_active",
        ("rate", "rate_date"),
        "manual_rate",
        "markup_percent",
        "updated_at",
    )
    actions_list = ("refresh_rates",)
    ordering_field = "position"
    hide_ordering_field = True

    def get_readonly_fields(self, request: HttpRequest, obj=None):
        # Код существующей валюты не меняем: он сохранён в заказах и настройках покупателей
        return (*self.readonly_fields, "currency") if obj else self.readonly_fields

    def save_model(self, request: HttpRequest, obj: ExchangeRate, form, change: bool) -> None:
        if not change:  # новая валюта — в конец переключателя на сайте
            last = ExchangeRate.objects.order_by("-position").values_list("position", flat=True)
            obj.position = (last.first() or 0) + 1
        super().save_model(request, obj, form, change)

    @display(description=_("effective rate"))
    def effective(self, obj: ExchangeRate) -> str:
        rate = obj.effective_rate
        if rate is None:
            return "—"
        # Курсы меньше единицы (BTC, KWD…) иначе выглядели бы как 0.00
        return f"{rate:,.2f}" if rate >= 1 else f"{rate:.6f}".rstrip("0")

    @action(description=_("Update from Central Bank"), icon="sync")
    def refresh_rates(self, request: HttpRequest) -> HttpResponseRedirect:
        try:
            updated = update_rates()
            self.message_user(
                request, _("Rates updated: %s") % ", ".join(updated), messages.SUCCESS
            )
        except RatesFetchError as exc:
            self.message_user(request, _("Could not load rates: %s") % exc, messages.ERROR)
        return HttpResponseRedirect(reverse("admin:currency_exchangerate_changelist"))
