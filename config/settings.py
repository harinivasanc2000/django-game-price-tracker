"""
Django settings for Game Price Tracker.
"""

from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-change-me-in-production")

DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.games",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.games.context_processors.site_ui",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

_DB_CONN_MAX_AGE = int(os.getenv("DB_CONN_MAX_AGE", "60"))
_DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if _DATABASE_URL:
    # django-environ is already a project dependency. A single setting enables
    # PostgreSQL for larger deployments while zero-config local runs stay on
    # the much lighter SQLite database.
    import environ

    database_config = environ.Env.db_url_config(_DATABASE_URL)
    # ``db_url_config`` intentionally accepts only URL/engine arguments across
    # supported django-environ versions; Django's persistence option belongs
    # on the resulting database dictionary.
    database_config["CONN_MAX_AGE"] = _DB_CONN_MAX_AGE
    DATABASES = {"default": database_config}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            # Reuse connections, allow readers during background writes, and
            # acquire SQLite write locks at transaction start instead of after
            # work has been done. This keeps snapshot coalescing deterministic.
            "CONN_MAX_AGE": _DB_CONN_MAX_AGE,
            "OPTIONS": {
                "timeout": 20,
                "transaction_mode": os.getenv("SQLITE_TRANSACTION_MODE", "IMMEDIATE"),
                "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL",
            },
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Europe/London"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

DEFAULT_CURRENCY = os.getenv("DEFAULT_CURRENCY", "GBP")
DEFAULT_REGION = os.getenv("DEFAULT_REGION", "GB")

# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------
# LocMem by default — zero external deps. Swap to Redis in production:
#   CACHES + REDIS_URL -> "django.core.cache.backends.redis.RedisCache"
_CACHE_BACKEND = os.getenv(
    "CACHE_BACKEND", "django.core.cache.backends.locmem.LocMemCache"
)
_CACHE_OPTIONS = {}
if _CACHE_BACKEND.endswith("LocMemCache"):
    # A bounded cache trades a small, predictable amount of RAM for far fewer
    # retailer requests. Redis deployments manage their own eviction policy.
    _CACHE_OPTIONS = {
        "MAX_ENTRIES": int(os.getenv("CACHE_MAX_ENTRIES", "800")),
        "CULL_FREQUENCY": 3,
    }

CACHES = {
    "default": {
        "BACKEND": _CACHE_BACKEND,
        "LOCATION": os.getenv("CACHE_LOCATION", "game-price-tracker"),
        "TIMEOUT": int(os.getenv("CACHE_TIMEOUT", "300")),
        "OPTIONS": _CACHE_OPTIONS,
    }
}

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

# ---------------------------------------------------------------------------
# Email (default: console for local dev — swap to SMTP in production)
# ---------------------------------------------------------------------------
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "Game Price Tracker <noreply@localhost>")
SITE_URL = os.getenv("SITE_URL", "http://127.0.0.1:8000")

# ---------------------------------------------------------------------------
# Celery (background price updates)
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = False
CELERY_TASK_IGNORE_RESULT = os.getenv("CELERY_TASK_IGNORE_RESULT", "True").lower() in (
    "true",
    "1",
    "yes",
)
CELERY_RESULT_EXPIRES = int(os.getenv("CELERY_RESULT_EXPIRES", "3600"))
CELERY_WORKER_CONCURRENCY = int(os.getenv("CELERY_WORKER_CONCURRENCY", "2"))
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_MAX_TASKS_PER_CHILD = int(os.getenv("CELERY_MAX_TASKS_PER_CHILD", "100"))
_PRICE_REFRESH_INTERVAL = int(os.getenv("PRICE_REFRESH_INTERVAL_SECONDS", "43200"))
CELERY_BEAT_SCHEDULE = {
    "compact-cross-platform-price-refresh": {
        "task": "apps.games.tasks.refresh_all_tracked_prices",
        "schedule": _PRICE_REFRESH_INTERVAL,
        # If a worker was offline, do not replay an obsolete retailer sweep.
        "options": {"expires": max(60, _PRICE_REFRESH_INTERVAL - 60)},
    },
    "send-pending-price-alerts": {
        "task": "apps.games.tasks.send_pending_alerts",
        "schedule": 900,
        "options": {"expires": 840},
    },
}
# If Redis is down, tasks can still be run via manage.py refresh_prices
CELERY_TASK_ALWAYS_EAGER = os.getenv("CELERY_TASK_ALWAYS_EAGER", "False").lower() in (
    "true",
    "1",
    "yes",
)
