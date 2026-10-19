import json
from datetime import timedelta

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import lazy
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from modeltranslation.admin import TabbedTranslationAdmin
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import ChoicesDropdownFilter, RangeDateFilter
from unfold.decorators import action, display

from .models import DeliveryMethod, Order, OrderItem
from .services import OrderError, change_status


def new_orders_badge(request: HttpRequest) -> int | None:
    """Счётчик новых заказов в меню админки."""
    return Order.objects.filter(status=Order.Status.NEW).count() or None


# Свои правила подсветки меню: иначе Unfold из-за вкладок подсвечивает
# и «Заказы», и «Доску заказов» сразу
def is_board_menu_active(request: HttpRequest) -> bool:
    return request.path.startswith(reverse("admin:orders_order_board"))


def is_orders_menu_active(request: HttpRequest) -> bool:
    """«Заказы» — на списке и в карточках заказов, но не на доске."""
    return request.path.startswith(
        reverse("admin:orders_order_changelist")
    ) and not is_board_menu_active(request)


def is_all_orders_tab(request: HttpRequest) -> bool:
    """Вкладка «Все заказы» активна в списке без фильтра по статусу (но не на доске)."""
    return request.path == reverse("admin:orders_order_changelist") and (
        "status__exact" not in request.GET
    )


@admin.register(DeliveryMethod)
class DeliveryMethodAdmin(ModelAdmin, TabbedTranslationAdmin):
    list_display = ("name", "scope", "price_display", "is_active")
    list_filter = ("scope", "is_active")
    prepopulated_fields = {"code": ("name_en",)}
    ordering_field = "position"
    hide_ordering_field = True

    @display(description=_("price, USD"))
    def price_display(self, obj: DeliveryMethod) -> str:
        return f"${obj.price:,.2f}" if obj.price is not None else str(_("by manager"))


class OrderItemInline(TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    fields = (
        "brand",
        "name",
        "reference",
        "price",
        "quantity",
        "on_order",
        "serial_number",
        "warranty_until",
    )
    # Серийный номер и гарантию менеджер вписывает при продаже — они видны в «Моей коллекции»
    readonly_fields = ("brand", "name", "reference", "price", "quantity", "on_order")

    def has_add_permission(self, request, obj=None) -> bool:
        return False


def transition_action(status: str, description, icon: str, confirm=None):
    """Кнопка перехода в нижней панели заказа: форма сохраняется (трек-номер, заметка),
    затем меняется статус."""

    def handler(self: "OrderAdmin", request: HttpRequest, obj: Order) -> None:
        self.apply_transition(request, obj, status)

    handler.__name__ = f"to_{status}"
    # Текст подтверждения — на языке менеджера; json.dumps экранирует кавычки перевода
    onclick = lazy(lambda: f"return confirm({json.dumps(str(confirm), ensure_ascii=False)})", str)
    attrs = {"onclick": onclick()} if confirm else None
    return action(description=description, icon=icon, permissions=[f"to_{status}"], attrs=attrs)(
        handler
    )


def transition_permission(status: str):
    """Кнопка видна, только если из текущего статуса заказа в этот можно перейти."""

    def has_permission(self: "OrderAdmin", request: HttpRequest, object_id=None) -> bool:
        if not self.has_change_permission(request):
            return False
        if object_id is None:
            return True  # переход всё равно проверит change_status
        order = Order.objects.filter(pk=object_id).only("status").first()
        return order is not None and order.can_change_to(status)

    return has_permission


# Колонки доски заказов; завершённые и отменённые — только за последние дни
BOARD_COLUMNS = (
    Order.Status.NEW,
    Order.Status.CONFIRMED,
    Order.Status.PAID,
    Order.Status.SHIPPED,
    Order.Status.COMPLETED,
    Order.Status.CANCELLED,
)
BOARD_ARCHIVE_DAYS = 14

STATUS_COLORS = {
    Order.Status.NEW: "info",
    Order.Status.CONFIRMED: "primary",
    Order.Status.PAID: "success",
    Order.Status.SHIPPED: "warning",
    Order.Status.COMPLETED: "success",
    Order.Status.CANCELLED: "danger",
}


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_display = (
        "number",
        "created_at",
        "status_badge",
        "customer_name",
        "phone",
        "country",
        "total_display",
        "delivery_method",
    )
    list_filter = (
        ("status", ChoicesDropdownFilter),
        ("created_at", RangeDateFilter),
        "delivery_method",
    )
    list_filter_submit = True
    search_fields = (
        "number",
        "customer_name",
        "phone",
        "email",
        "items__reference",
        "tracking_number",
    )
    list_select_related = ("delivery_method",)
    inlines = (OrderItemInline,)
    # Статус меняется только кнопками переходов — так нельзя перескочить шаг
    actions_submit_line = ("to_confirmed", "to_paid", "to_shipped", "to_completed", "to_cancelled")
    readonly_fields = (
        "status",
        "number",
        "created_at",
        "customer",
        "customer_name",
        "phone",
        "email",
        "contact_method",
        "contact_links",
        "country",
        "city",
        "address",
        "comment",
        "delivery_method",
        "subtotal",
        "total",
        "currency_display",
        "language",
    )
    fieldsets = (
        (
            None,
            {
                "fields": (
                    ("number", "created_at"),
                    ("status", "tracking_number"),
                    "customer",
                    "manager_note",
                )
            },
        ),
        (
            _("Customer"),
            {
                "fields": (
                    ("customer_name", "contact_method"),
                    ("phone", "email"),
                    "contact_links",
                    "comment",
                )
            },
        ),
        (
            _("Delivery"),
            {"fields": (("delivery_method", "delivery_price"), ("country", "city"), "address")},
        ),
        (_("Amount"), {"fields": (("subtotal", "total"), "currency_display", "language")}),
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        # Заказы создаются только с сайта
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        # Вместо удаления — отмена: так остатки корректно возвращаются на склад
        return False

    to_confirmed = transition_action(Order.Status.CONFIRMED.value, _("Confirm"), "check")
    has_to_confirmed_permission = transition_permission(Order.Status.CONFIRMED.value)
    to_paid = transition_action(Order.Status.PAID.value, _("Payment received"), "payments")
    has_to_paid_permission = transition_permission(Order.Status.PAID.value)
    to_shipped = transition_action(Order.Status.SHIPPED.value, _("Ship"), "local_shipping")
    has_to_shipped_permission = transition_permission(Order.Status.SHIPPED.value)
    to_completed = transition_action(Order.Status.COMPLETED.value, _("Complete"), "done_all")
    has_to_completed_permission = transition_permission(Order.Status.COMPLETED.value)
    to_cancelled = transition_action(
        Order.Status.CANCELLED.value,
        _("Cancel order"),
        "block",
        confirm=_("Cancel the order? Items in stock will be returned to the warehouse."),
    )
    has_to_cancelled_permission = transition_permission(Order.Status.CANCELLED.value)

    def apply_transition(self, request: HttpRequest, obj: Order, status: str) -> None:
        try:
            change_status(obj, status)
        except OrderError as exc:
            self.message_user(request, str(exc), messages.ERROR)
            return
        self.message_user(
            request,
            _("Order %(number)s: %(status)s")
            % {"number": obj.number, "status": obj.get_status_display()},
            messages.SUCCESS,
        )

    def response_change(self, request: HttpRequest, obj: Order) -> HttpResponse:
        # После кнопки перехода остаёмся в заказе — видно новый статус и следующие шаги
        if any(a.action_name in request.POST for a in self._get_base_actions_submit_line()):
            return HttpResponseRedirect(request.path)
        return super().response_change(request, obj)

    # --- Доска заказов ---------------------------------------------------------

    def get_custom_urls(self):
        return (
            ("board/", "orders_order_board", self.board_view),
            ("board/move/", "orders_order_board_move", require_POST(self.board_move_view)),
        )

    def board_view(self, request: HttpRequest, **kwargs) -> TemplateResponse:
        if not self.has_view_permission(request):
            raise PermissionDenied
        archive_since = timezone.now() - timedelta(days=BOARD_ARCHIVE_DAYS)
        archived = (Order.Status.COMPLETED, Order.Status.CANCELLED)
        orders = (
            Order.objects.filter(~Q(status__in=archived) | Q(updated_at__gte=archive_since))
            .select_related("delivery_method")
            .prefetch_related("items")
            .order_by("-created_at")
        )
        by_status: dict[str, list[Order]] = {status: [] for status in BOARD_COLUMNS}
        for order in orders:
            by_status[order.status].append(order)

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": _("Order board"),
            "is_fullwidth": "1",
            "columns": [
                {
                    "status": status,
                    "label": status.label,
                    "orders": by_status[status],
                    # Куда можно перетащить карточки из этой колонки
                    "allowed": " ".join(sorted(Order.TRANSITIONS[status])),
                }
                for status in BOARD_COLUMNS
            ],
            "archive_days": BOARD_ARCHIVE_DAYS,
            "can_change": self.has_change_permission(request),
            "move_url": reverse("admin:orders_order_board_move"),
            "texts": {
                "tracking": str(_("BTS tracking number (can be left empty):")),
                "cancel": str(
                    _("Cancel the order? Items in stock will be returned to the warehouse.")
                ),
                "failed": str(_("Could not change the status.")),
            },
        }
        return TemplateResponse(request, "admin/orders/order/board.html", context)

    def board_move_view(self, request: HttpRequest, **kwargs) -> JsonResponse:
        if not self.has_change_permission(request):
            raise PermissionDenied
        order = get_object_or_404(Order, pk=request.POST.get("order"))
        status = request.POST.get("status", "")
        if status not in Order.Status.values:
            return JsonResponse({"error": str(_("Unknown status."))}, status=400)
        try:
            change_status(order, status, tracking_number=request.POST.get("tracking_number"))
        except OrderError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        return JsonResponse(
            {
                "status": order.status,
                "allowed": sorted(Order.TRANSITIONS[order.status]),
                "tracking_number": order.tracking_number,
            }
        )

    @display(description=_("status"), label=STATUS_COLORS)
    def status_badge(self, obj: Order) -> tuple[str, str]:
        return obj.status, obj.get_status_display()

    @display(description=_("total"))
    def total_display(self, obj: Order) -> str:
        return f"${obj.total:,.0f}"

    @display(description=_("display currency"))
    def currency_display(self, obj: Order) -> str:
        if obj.currency == "USD":
            return "USD"
        return f"{obj.total_in_currency:,.0f} {obj.currency} (1 USD = {obj.exchange_rate:,.2f})"

    @display(description=_("write to customer"))
    def contact_links(self, obj: Order) -> str:
        digits = "".join(ch for ch in obj.phone if ch.isdigit())
        return format_html(
            '<a href="https://wa.me/{}" target="_blank">WhatsApp</a> · <a href="tel:{}">{}</a>',
            digits,
            obj.phone,
            _("Call"),
        )
