"""Общие настройки для всех окружений. Окружение-специфичное — в dev/prod/test."""

from pathlib import Path

import environ
from celery.schedules import crontab
from django.templatetags.static import static
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

# --- Приложения -------------------------------------------------------------

UNFOLD_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
]

DJANGO_APPS = [
    # modeltranslation должен идти до django.contrib.admin
    "modeltranslation",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "ninja",
    "django_countries",
    "corsheaders",
    "storages",
]

LOCAL_APPS = [
    "apps.core",
    "apps.catalog",
    "apps.currency",
    "apps.accounts",
    "apps.orders",
    "apps.content",
]

INSTALLED_APPS = UNFOLD_APPS + DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- База данных и кэш -------------------------------------------------------

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = True
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)

REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

SESSION_ENGINE = "django.contrib.sessions.backends.cache"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Пароли -----------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Языки ------------------------------------------------------------------

LANGUAGE_CODE = "en"
LANGUAGES = [
    ("en", _("English")),
    ("uz", _("Uzbek")),
    ("ru", _("Russian")),
]
MODELTRANSLATION_DEFAULT_LANGUAGE = "en"
MODELTRANSLATION_FALLBACK_LANGUAGES = ("en",)
LOCALE_PATHS = [BASE_DIR / "locale"]

TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

# --- Валюты -----------------------------------------------------------------

# Цены хранятся в базовой валюте; остальные — пересчёт по курсу для отображения.
BASE_CURRENCY = "USD"
DISPLAY_CURRENCIES = ["USD", "UZS", "EUR", "RUB"]

# --- Статика и медиа ---------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

AWS_STORAGE_BUCKET_NAME = env("S3_BUCKET", default="")
AWS_S3_ENDPOINT_URL = env("S3_ENDPOINT_URL", default=None)
AWS_S3_CUSTOM_DOMAIN = env("S3_CUSTOM_DOMAIN", default=None)
AWS_ACCESS_KEY_ID = env("S3_ACCESS_KEY", default="")
AWS_SECRET_ACCESS_KEY = env("S3_SECRET_KEY", default="")
AWS_QUERYSTRING_AUTH = False
AWS_DEFAULT_ACL = None
AWS_S3_FILE_OVERWRITE = False

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage"
        if AWS_STORAGE_BUCKET_NAME
        else "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# --- CORS (витрина Nuxt) -----------------------------------------------------

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
# Cookie сессии покупателя должна уходить с запросами витрины к API (локально — другой порт)
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# --- Celery -----------------------------------------------------------------

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = None
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    # ЦБ публикует курсы раз в день; второй запуск — подстраховка
    "update-exchange-rates": {
        "task": "apps.currency.tasks.update_exchange_rates",
        "schedule": crontab(hour="9,15", minute=30),
    },
}

# --- Внешние сервисы ----------------------------------------------------------

# Публичный адрес бэкенда — для ссылок на админку в уведомлениях
BACKEND_URL = env("BACKEND_URL", default="http://localhost:8000")

# Адрес витрины — для ссылок в сообщениях бота
SITE_URL = env("SITE_URL", default="http://localhost:3000").rstrip("/")

# Telegram-бот Maison (@BotFather): уведомления менеджеру, вход и уведомления покупателей
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN", default="")
TELEGRAM_BOT_USERNAME = env("TELEGRAM_BOT_USERNAME", default="")
TELEGRAM_MANAGER_CHAT_ID = env("TELEGRAM_MANAGER_CHAT_ID", default="")
# Секрет в заголовке вебхука: запросы не от Telegram отклоняются
TELEGRAM_WEBHOOK_SECRET = env("TELEGRAM_WEBHOOK_SECRET", default="")

# Вход по SMS через Eskiz.uz — включается, если заданы учётные данные
ESKIZ_EMAIL = env("ESKIZ_EMAIL", default="")
ESKIZ_PASSWORD = env("ESKIZ_PASSWORD", default="")
ESKIZ_SENDER = env("ESKIZ_SENDER", default="4546")

MEILISEARCH_URL = env("MEILISEARCH_URL", default="http://localhost:7700")
MEILISEARCH_API_KEY = env("MEILISEARCH_API_KEY", default="")

# --- Логирование -------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "default"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}

# --- Админка (Unfold) --------------------------------------------------------

UNFOLD = {
    "SITE_TITLE": "Maison",
    "SITE_HEADER": "Maison",
    "SITE_SYMBOL": "watch",
    "SHOW_LANGUAGES": True,
    "SHOW_HISTORY": True,
    # Открывает вкладку языка с ошибкой (modeltranslation не видит ошибки в разметке Unfold)
    "SCRIPTS": [lambda request: static("core/js/translation-tab-errors.js")],
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": _("Catalog"),
                "items": [
                    {
                        "title": _("Products"),
                        "icon": "watch",
                        "link": reverse_lazy("admin:catalog_product_changelist"),
                    },
                    {
                        "title": _("Brands"),
                        "icon": "sell",
                        "link": reverse_lazy("admin:catalog_brand_changelist"),
                    },
                    {
                        "title": _("Categories"),
                        "icon": "category",
                        "link": reverse_lazy("admin:catalog_category_changelist"),
                    },
                    {
                        "title": _("Specification options"),
                        "icon": "tune",
                        "link": reverse_lazy("admin:catalog_specoption_changelist"),
                    },
                ],
            },
            {
                "title": _("Content"),
                "items": [
                    {
                        "title": _("Home page"),
                        "icon": "home",
                        "link": reverse_lazy("admin:content_homesection_changelist"),
                    },
                    {
                        "title": _("Pages"),
                        "icon": "description",
                        "link": reverse_lazy("admin:content_page_changelist"),
                    },
                    {
                        "title": _("FAQ"),
                        "icon": "help",
                        "link": reverse_lazy("admin:content_faqitem_changelist"),
                    },
                    {
                        "title": _("Site settings"),
                        "icon": "settings",
                        "link": reverse_lazy("admin:content_sitesettings_changelist"),
                    },
                ],
            },
            {
                "title": _("Sales"),
                "items": [
                    {
                        "title": _("Orders"),
                        "icon": "receipt_long",
                        "link": reverse_lazy("admin:orders_order_changelist"),
                        "badge": "apps.orders.admin.new_orders_badge",
                        "active": "apps.orders.admin.is_orders_menu_active",
                    },
                    {
                        "title": _("Order board"),
                        "icon": "view_kanban",
                        "link": reverse_lazy("admin:orders_order_board"),
                        "active": "apps.orders.admin.is_board_menu_active",
                    },
                    {
                        "title": _("Customers"),
                        "icon": "group",
                        "link": reverse_lazy("admin:accounts_customer_changelist"),
                    },
                    {
                        "title": _("Watch requests"),
                        "icon": "search",
                        "link": reverse_lazy("admin:accounts_watchrequest_changelist"),
                        "badge": "apps.accounts.admin.new_requests_badge",
                    },
                ],
            },
            {
                "title": _("Settings"),
                "items": [
                    {
                        "title": _("Delivery methods"),
                        "icon": "local_shipping",
                        "link": reverse_lazy("admin:orders_deliverymethod_changelist"),
                    },
                    {
                        "title": _("Exchange rates"),
                        "icon": "currency_exchange",
                        "link": reverse_lazy("admin:currency_exchangerate_changelist"),
                    },
                ],
            },
            {
                "title": _("Users & access"),
                "items": [
                    {
                        "title": _("Users"),
                        "icon": "person",
                        "link": reverse_lazy("admin:auth_user_changelist"),
                    },
                    {
                        "title": _("Groups"),
                        "icon": "group",
                        "link": reverse_lazy("admin:auth_group_changelist"),
                    },
                ],
            },
        ],
    },
    # Вкладки над списком заказов: доска и заказы по статусам
    "TABS": [
        {
            "models": ["orders.order"],
            "items": [
                {"title": _("Board"), "link": reverse_lazy("admin:orders_order_board")},
                {
                    "title": _("All orders"),
                    "link": reverse_lazy("admin:orders_order_changelist"),
                    "active": "apps.orders.admin.is_all_orders_tab",
                },
                *(
                    {
                        "title": title,
                        "link": lambda request, status=status: (
                            f"{reverse('admin:orders_order_changelist')}?status__exact={status}"
                        ),
                    }
                    for status, title in (
                        ("new", pgettext_lazy("orders tab", "New")),
                        ("confirmed", pgettext_lazy("orders tab", "Confirmed")),
                        ("paid", pgettext_lazy("orders tab", "Paid")),
                        ("shipped", pgettext_lazy("orders tab", "Shipped")),
                    )
                ),
            ],
        },
    ],
}
