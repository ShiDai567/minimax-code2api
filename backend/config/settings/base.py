import json
from pathlib import Path
from urllib.parse import urlsplit

import environ

BASE_DIR = Path(__file__).resolve().parents[2]
env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-only-change-me-not-for-production-use-32")
DEBUG = False
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["127.0.0.1", "localhost"])
APPEND_SLASH = False

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "apps.accounts.apps.AccountsConfig",
    "apps.checkin.apps.CheckinConfig",
    "apps.credits.apps.CreditsConfig",
    "apps.api_keys.apps.ApiKeysConfig",
    "apps.models_manager.apps.ModelsManagerConfig",
    "apps.request_logs.apps.RequestLogsConfig",
    "apps.system_settings.apps.SystemSettingsConfig",
    "apps.gateway.apps.GatewayConfig",
    "apps.dashboard.apps.DashboardConfig",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "APP_DIRS": True, "OPTIONS": {"context_processors": []}}]
STATIC_URL = "static/"

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    )
}
if DATABASES["default"]["ENGINE"].endswith("mysql"):
    DATABASES["default"].setdefault("OPTIONS", {})
    DATABASES["default"]["OPTIONS"].update({"charset": "utf8mb4", "init_command": "SET sql_mode='STRICT_TRANS_TABLES'"})

AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

ADMIN_TOKEN = env("ADMIN_TOKEN", default="")
CONSOLE_PASSWORD = env("CONSOLE_PASSWORD", default="")
ENCRYPTION_KEY = env("ENCRYPTION_KEY", default="")
MCODE_APP_VERSION = env("MCODE_APP_VERSION", default="0.1.0")
UPSTREAM_TIMEOUT_SECONDS = env.int("UPSTREAM_TIMEOUT_SECONDS", default=30)
GATEWAY_HOST = env("GATEWAY_HOST", default="127.0.0.1")
GATEWAY_PORT = env.int("GATEWAY_PORT", default=8045)
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=["http://localhost:3000", "http://127.0.0.1:3000"])
CORS_ALLOW_HEADERS = ["authorization", "content-type", "x-minimax-region", "anthropic-version", "anthropic-beta"]
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=["http://localhost:3000", "http://127.0.0.1:3000"])

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["common.permissions.SessionPermission"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "common.exceptions.exception_handler",
}
SPECTACULAR_SETTINGS = {"TITLE": "MiniMax Code2API", "VERSION": "1.0.0", "SERVE_INCLUDE_SCHEMA": False}


def _load_json(name):
    raw = env(name, default="{}")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise RuntimeError(f"{name} must be a JSON object")
    return value


def _https(value, label):
    parts = urlsplit(value)
    if not (
        isinstance(value, str)
        and parts.scheme == "https"
        and parts.hostname
        and parts.username is None
        and parts.password is None
        and not parts.fragment
    ):
        raise RuntimeError(f"{label} must be an HTTPS URL without credentials")


BALANCE_ADAPTERS = _load_json("BALANCE_ADAPTERS")
MODEL_DISCOVERY_URLS = _load_json("MODEL_DISCOVERY_URLS")
for region in (*BALANCE_ADAPTERS, *MODEL_DISCOVERY_URLS):
    if region not in ("cn", "global"):
        raise RuntimeError("Invalid adapter region")
for adapter in BALANCE_ADAPTERS.values():
    if not isinstance(adapter, dict) or set(adapter) != {"url", "field", "unit"}:
        raise RuntimeError("Balance adapter requires url, field and unit")
    _https(adapter["url"], "Balance adapter")
for url in MODEL_DISCOVERY_URLS.values():
    _https(url, "Model discovery")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
