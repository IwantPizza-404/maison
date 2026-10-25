import secrets

from django.contrib import admin, messages
from django.core.cache import cache
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TabbedTranslationAdmin, TranslationTabularInline
from unfold.admin import ModelAdmin, StackedInline, TabularInline
from unfold.contrib.filters.admin import (
    ChoicesDropdownFilter,
    RangeNumericFilter,
    RelatedDropdownFilter,
)
from unfold.decorators import action, display

from apps.core.excel import xlsx_response

from .models import Brand, Category, Product, ProductImage, SpecOption, WatchSpecs
from .services import (
    ImportFileError,
    export_products,
    import_products,
    products_template,
    unique_slug,
)

IMPORT_MAX_SIZE = 5 * 1024 * 1024
# Файл между проверкой и подтверждением импорта лежит в кэше
IMPORT_CACHE_TTL = 30 * 60


@admin.register(Brand)
class BrandAdmin(ModelAdmin, TabbedTranslationAdmin):
    list_display = ("name", "country", "products_count", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "search_aliases")
    prepopulated_fields = {"slug": ("name",)}
    ordering_field = "position"
    hide_ordering_field = True

    @display(description=_("products"))
    def products_count(self, obj: Brand) -> int:
        return obj.products.count()


@admin.register(Category)
class CategoryAdmin(ModelAdmin, TabbedTranslationAdmin):
    list_display = ("__str__", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name_en",)}
    ordering_field = "position"
    hide_ordering_field = True


@admin.register(SpecOption)
class SpecOptionAdmin(ModelAdmin, TabbedTranslationAdmin):
    list_display = ("name", "kind")
    list_filter = (("kind", ChoicesDropdownFilter),)
    list_filter_submit = True
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name_en",)}
    ordering_field = "position"
    hide_ordering_field = True


class WatchSpecsInline(StackedInline):
    model = WatchSpecs
    can_delete = False
    autocomplete_fields = ("case_material", "glass", "dial_color", "strap_material")
    filter_horizontal = ("complications",)
    fieldsets = (
        (_("Movement"), {"fields": (("movement", "caliber", "power_reserve_hours"),)}),
        (
            _("Case"),
            {
                "fields": (
                    ("case_material", "case_diameter_mm", "case_thickness_mm"),
                    ("glass", "water_resistance_m"),
                )
            },
        ),
        (_("Dial & strap"), {"fields": (("dial_color", "strap_material"), "complications")}),
        (
            _("Set & provenance"),
            {"fields": (("year", "has_box", "has_papers"), "serial_number")},
        ),
    )


class ProductImageInline(TabularInline, TranslationTabularInline):
    model = ProductImage
    extra = 0
    fields = ("preview", "image", "alt", "position")
    readonly_fields = ("preview",)
    ordering_field = "position"
    hide_ordering_field = True

    @display(description=_("preview"))
    def preview(self, obj: ProductImage) -> str:
        if not obj.image:
            return "—"
        return format_html('<img src="{}" style="height:64px">', (obj.thumb or obj.image).url)


@admin.register(Product)
class ProductAdmin(ModelAdmin, TabbedTranslationAdmin):
    list_display = (
        "thumbnail",
        "name",
        "brand",
        "reference",
        "price",
        "availability_badge",
        "stock_quantity",
        "is_published",
    )
    list_display_links = ("thumbnail", "name")
    list_filter = (
        ("brand", RelatedDropdownFilter),
        ("category", RelatedDropdownFilter),
        ("availability", ChoicesDropdownFilter),
        ("condition", ChoicesDropdownFilter),
        ("gender", ChoicesDropdownFilter),
        ("price", RangeNumericFilter),
        "is_published",
        "is_featured",
    )
    list_filter_submit = True
    list_per_page = 50
    search_fields = ("name", "reference", "brand__name", "watch_specs__serial_number")
    autocomplete_fields = ("brand", "category")
    # Пустой slug строится при сохранении из бренда и названия — как при импорте (tissot-prx-200);
    # при вводе название показывается в поле как подсказка (product-slug.js)
    list_select_related = ("brand", "category")
    inlines = (WatchSpecsInline, ProductImageInline)
    actions = ("publish", "unpublish", "export_selected")
    actions_list = ("export_all", "import_file", "download_template")
    fieldsets = (
        (None, {"fields": (("brand", "category"), "name", "slug", "reference", "description")}),
        (_("Price"), {"fields": (("price", "compare_at_price"),)}),
        (
            _("Availability"),
            {"fields": (("availability", "stock_quantity", "lead_time_days"),)},
        ),
        (_("Attributes"), {"fields": (("condition", "gender"),)}),
        (_("Publishing"), {"fields": (("is_published", "is_featured"),)}),
        (
            _("SEO"),
            {"fields": ("seo_title", "seo_description"), "classes": ("collapse",)},
        ),
    )

    class Media:
        js = ("admin/js/urlify.js", "catalog/js/product-slug.js")

    def get_form(self, request: HttpRequest, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change=change, **kwargs)
        if "slug" in form.base_fields:
            form.base_fields["slug"].required = False
            form.base_fields["slug"].help_text = _(
                "Leave empty — it is built from the brand and the English name."
            )
        return form

    def save_model(self, request: HttpRequest, obj: Product, form, change: bool) -> None:
        if not obj.slug:
            obj.slug = unique_slug(obj)
        super().save_model(request, obj, form, change)

    def get_queryset(self, request: HttpRequest) -> QuerySet[Product]:
        return super().get_queryset(request).prefetch_related("images")

    @display(description="")
    def thumbnail(self, obj: Product) -> str:
        images = list(obj.images.all())
        if not images:
            return "—"
        return format_html(
            '<img src="{}" style="height:40px;width:40px;object-fit:cover">',
            (images[0].thumb or images[0].image).url,
        )

    @display(
        description=_("availability"),
        label={
            Product.Availability.IN_STOCK: "success",
            Product.Availability.ON_ORDER: "warning",
            Product.Availability.SOLD_OUT: "danger",
        },
    )
    def availability_badge(self, obj: Product) -> tuple[str, str]:
        return obj.availability, obj.get_availability_display()

    @action(description=_("Publish selected"))
    def publish(self, request: HttpRequest, queryset: QuerySet[Product]) -> None:
        # Поштучно, а не queryset.update(): сохранение запускает уведомления подписчикам бренда
        products = list(queryset.filter(is_published=False))
        for product in products:
            product.is_published = True
            product.save(update_fields=["is_published", "updated_at"])
        updated = len(products)
        self.message_user(request, _("Published: %d") % updated, messages.SUCCESS)

    @action(description=_("Unpublish selected"))
    def unpublish(self, request: HttpRequest, queryset: QuerySet[Product]) -> None:
        updated = queryset.update(is_published=False)
        self.message_user(request, _("Unpublished: %d") % updated, messages.SUCCESS)

    # --- Excel: экспорт, шаблон, импорт ----------------------------------------------

    def has_import_permission(self, request: HttpRequest) -> bool:
        return self.has_add_permission(request) and self.has_change_permission(request)

    @action(description=_("Export selected to Excel"))
    def export_selected(self, request: HttpRequest, queryset: QuerySet[Product]) -> HttpResponse:
        return xlsx_response(export_products(queryset), "maison-products")

    @action(description=_("Export"), url_path="export", permissions=["view"])
    def export_all(self, request: HttpRequest) -> HttpResponse:
        return xlsx_response(export_products(Product.objects.all()), "maison-products")

    @action(description=_("Import template"), url_path="import-template", permissions=["import"])
    def download_template(self, request: HttpRequest) -> HttpResponse:
        return xlsx_response(products_template(), "maison-import-template")

    @action(description=_("Import"), url_path="import", permissions=["import"])
    def import_file(self, request: HttpRequest) -> HttpResponse:
        """Шаг 1 — загрузка и проверка без сохранения, шаг 2 — подтверждение."""
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": _("Import products"),
            "template_url": reverse("admin:catalog_product_download_template"),
            "export_url": reverse("admin:catalog_product_export_all"),
        }
        if request.method == "POST" and request.POST.get("token"):
            data = cache.get(import_cache_key(request.POST["token"]))
            if data is None:
                self.message_user(
                    request, _("The check has expired, upload the file again."), messages.WARNING
                )
            else:
                report = import_products(data, commit=True)
                if report.ok:
                    cache.delete(import_cache_key(request.POST["token"]))
                    self.message_user(
                        request,
                        _("Import finished: %(created)d created, %(updated)d updated.")
                        % {"created": report.created, "updated": report.updated},
                        messages.SUCCESS,
                    )
                    return HttpResponseRedirect(reverse("admin:catalog_product_changelist"))
                context["report"] = report  # каталог изменился между проверкой и импортом
        elif request.method == "POST":
            upload = request.FILES.get("file")
            if upload is None:
                self.message_user(request, _("Choose a file."), messages.ERROR)
            elif upload.size and upload.size > IMPORT_MAX_SIZE:
                self.message_user(request, _("The file is too large (max 5 MB)."), messages.ERROR)
            else:
                data = upload.read()
                try:
                    report = import_products(data, commit=False)
                except ImportFileError as exc:
                    self.message_user(request, str(exc), messages.ERROR)
                else:
                    context.update(report=report, file_name=upload.name)
                    if report.ok:
                        token = secrets.token_urlsafe(16)
                        cache.set(import_cache_key(token), data, IMPORT_CACHE_TTL)
                        context["token"] = token
        return TemplateResponse(request, "admin/catalog/product/import.html", context)


def import_cache_key(token: str) -> str:
    return f"catalog:product-import:{token}"
