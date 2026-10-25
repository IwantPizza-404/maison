from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import ChoicesDropdownFilter
from unfold.decorators import action, display

from apps.core.excel import xlsx_response
from apps.orders.models import Order

from .models import Address, Customer, StockAlert, WatchRequest, WishlistItem
from .services import export_customers


def new_requests_badge(request: HttpRequest) -> int | None:
    return WatchRequest.objects.filter(status=WatchRequest.Status.NEW).count() or None


class ReadOnlyInline(TabularInline):
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


class AddressInline(ReadOnlyInline):
    model = Address
    fields = ("country", "city", "address", "is_default")


class OrderInline(ReadOnlyInline):
    model = Order
    fields = ("order_link", "created_at", "status", "total")
    readonly_fields = ("order_link",)
    verbose_name_plural = _("orders")

    @display(description=_("order"))
    def order_link(self, obj: Order) -> str:
        return format_html(
            '<a href="{}">{}</a>', reverse("admin:orders_order_change", args=[obj.pk]), obj.number
        )


class WishlistInline(ReadOnlyInline):
    model = WishlistItem
    fields = ("product", "known_price", "created_at")


class AlertInline(ReadOnlyInline):
    model = StockAlert
    fields = ("product", "brand", "is_active", "notified_at")


class WatchRequestInline(ReadOnlyInline):
    model = WatchRequest
    fields = ("request_link", "status", "created_at")
    readonly_fields = ("request_link",)

    @display(description=_("watch request"))
    def request_link(self, obj: WatchRequest) -> str:
        url = reverse("admin:accounts_watchrequest_change", args=[obj.pk])
        return format_html('<a href="{}">{}</a>', url, obj)


@admin.register(Customer)
class CustomerAdmin(ModelAdmin):
    list_display = ("__str__", "telegram_display", "orders_count", "created_at", "last_login_at")
    search_fields = ("phone", "name", "email", "telegram_username")
    readonly_fields = ("phone", "telegram_id", "telegram_username", "created_at", "last_login_at")
    fields = (
        ("name", "phone"),
        ("email", "telegram_username"),
        ("language", "currency", "notify_telegram"),
        ("created_at", "last_login_at"),
    )
    inlines = (OrderInline, WatchRequestInline, WishlistInline, AlertInline, AddressInline)
    actions = ("export_selected",)
    actions_list = ("export_all",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        # Покупатели регистрируются сами — через вход на сайте
        return False

    @display(description="Telegram")
    def telegram_display(self, obj: Customer) -> str:
        if obj.telegram_username:
            return f"@{obj.telegram_username}"
        return "✓" if obj.telegram_id else "—"

    @display(description=_("orders"))
    def orders_count(self, obj: Customer) -> int:
        return obj.orders.count()

    @action(description=_("Export"), url_path="export", permissions=["view"])
    def export_all(self, request: HttpRequest) -> HttpResponse:
        return xlsx_response(export_customers(Customer.objects.all()), "maison-customers")

    @action(description=_("Export selected to Excel"))
    def export_selected(self, request: HttpRequest, queryset: QuerySet[Customer]) -> HttpResponse:
        return xlsx_response(export_customers(queryset), "maison-customers")


WATCH_REQUEST_COLORS = {
    WatchRequest.Status.NEW: "info",
    WatchRequest.Status.SEARCHING: "warning",
    WatchRequest.Status.OFFERED: "success",
    WatchRequest.Status.CLOSED: "danger",
}


@admin.register(WatchRequest)
class WatchRequestAdmin(ModelAdmin):
    list_display = ("__str__", "customer", "budget", "status_badge", "created_at")
    list_filter = (("status", ChoicesDropdownFilter),)
    list_filter_submit = True
    search_fields = ("brand", "model", "reference", "customer__phone", "customer__name")
    readonly_fields = (
        "customer",
        "brand",
        "model",
        "reference",
        "condition",
        "budget",
        "comment",
        "created_at",
    )
    fieldsets = (
        (
            _("Request"),
            {
                "fields": (
                    ("brand", "model", "reference"),
                    ("condition", "budget"),
                    "comment",
                    ("customer", "created_at"),
                )
            },
        ),
        (_("Reply"), {"fields": ("status", "reply")}),
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    @display(description=_("status"), label=WATCH_REQUEST_COLORS)
    def status_badge(self, obj: WatchRequest) -> tuple[str, str]:
        return obj.status, obj.get_status_display()
