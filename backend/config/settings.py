import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from django.core.management import utils

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.getenv("DJANGO_DEBUG", "0") == "1"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY is required")
    SECRET_KEY = utils.get_random_secret_key()
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
CSRF_TRUSTED_ORIGINS = [
    x
    for x in os.getenv(
        "DJANGO_CSRF_ORIGINS",
        (
            "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3017,http://127.0.0.1:3017"
            if DEBUG
            else ""
        ),
    ).split(",")
    if x
]
INSTALLED_APPS = [
    "unfold",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "portal",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "portal.limits.StaffLoginLimit",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "portal/templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
DATA_DIR = Path(
    os.getenv("QUORUM_PORTAL_DATA", str(Path.home() / ".local/share/quorum/portal"))
)
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "portal.sqlite3",
        "OPTIONS": {"timeout": 20},
    }
}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation." + name}
    for name in [
        "UserAttributeSimilarityValidator",
        "MinimumLengthValidator",
        "CommonPasswordValidator",
        "NumericPasswordValidator",
    ]
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_TZ = True
STATIC_URL = "/staff-static/"
STATIC_ROOT = Path(os.getenv("QUORUM_STATIC_ROOT", str(DATA_DIR / "static")))
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SESSION_COOKIE_NAME = "quorum_session"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 86400
SECURE_SSL_REDIRECT = not DEBUG
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
DATA_UPLOAD_MAX_MEMORY_SIZE = 65536
UNFOLD = {
    "SITE_TITLE": "Quorum Control",
    "SITE_HEADER": "Quorum",
    "SITE_SUBHEADER": "Control · editorial intelligence",
    "SITE_URL": "/dashboard",
    "STYLES": [lambda request: "/staff-static/portal/control.css"],
    "SIDEBAR": {
        "show_search": True,
        "navigation": [
            {
                "title": "Workspace",
                "items": [
                    {"title": "Overview", "icon": "space_dashboard", "link": "/staff/"},
                    {"title": "Users", "icon": "group", "link": "/staff/auth/user/"},
                    {"title": "Topics", "icon": "bookmark", "link": "/staff/topics/"},
                    {
                        "title": "News sources",
                        "icon": "newspaper",
                        "link": "/staff/sources/",
                    },
                    {
                        "title": "System status",
                        "icon": "monitor_heart",
                        "link": "/staff/status/",
                    },
                    {
                        "title": "Integration readiness",
                        "icon": "hub",
                        "link": "/staff/integrations/",
                    },
                ],
            }
        ],
    },
}

UNFOLD["COLORS"] = {
    "primary": {
        "50": "#edf5f1",
        "100": "#dfede6",
        "200": "#bddbd0",
        "300": "#91c2b4",
        "400": "#4f9b8e",
        "500": "#16766d",
        "600": "#16766d",
        "700": "#105d56",
        "800": "#124c46",
        "900": "#153f3b",
        "950": "#0b2523",
    }
}
UNFOLD["SITE_SYMBOL"] = "blur_on"

UNFOLD["THEME"] = "light"
LOGIN_REDIRECT_URL = "/staff/"
