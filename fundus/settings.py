"""Einstellungen für Fundus.

Alle Werte kommen aus Umgebungsvariablen (Twelve-Factor). Eine Datei `.env`
im Projektverzeichnis wird nur gelesen, wenn sie existiert – praktisch für
die Entwicklung, im Container nicht nötig. Siehe `.env.example`.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
if (BASE_DIR / ".env").is_file():
    env.read_env(BASE_DIR / ".env")

DEBUG = env.bool("DEBUG", default=False)

# Ohne SECRET_KEY startet Fundus im Produktivbetrieb nicht.
if DEBUG:
    SECRET_KEY = env.str("SECRET_KEY", default="unsicher-nur-fuer-entwicklung")
else:
    SECRET_KEY = env.str("SECRET_KEY")

# Datenverzeichnis: Coverbilder, SQLite-Datenbank, Sicherungen.
DATA_DIR = Path(env.str("DATA_DIR", default=str(BASE_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "simple_history",
    "fundus.core",
    "fundus.accounts",
    "fundus.catalog",
    "fundus.loans",
    "fundus.transfer",
    "fundus.supplies",
]

MIDDLEWARE = [
    "fundus.core.middleware.HealthCheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "fundus.core.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "fundus.urls"
WSGI_APPLICATION = "fundus.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "fundus" / "templates"],
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

# Standard ist SQLite im Datenverzeichnis; im Container setzt docker-compose.yml
# DATABASE_URL auf PostgreSQL.
DATABASES = {
    "default": env.db_url("DATABASE_URL", default=f"sqlite:///{DATA_DIR / 'fundus.sqlite3'}"),
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"
# Lehrkräfte bleiben auf ihrem Handy angemeldet, damit Ausleihen schnell geht.
SESSION_COOKIE_AGE = env.int("SESSION_DAYS", default=30) * 24 * 3600
PASSWORD_RESET_TIMEOUT = 24 * 3600
INVITATION_TIMEOUT_DAYS = env.int("INVITATION_TIMEOUT_DAYS", default=14)
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Oberfläche auf Deutsch. Texte sind mit gettext markiert, Deutsch ist die
# Ausgangssprache; weitere Sprachen kommen später über Übersetzungsdateien.
LANGUAGE_CODE = "de"
TIME_ZONE = env.str("TIME_ZONE", default="Europe/Berlin")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "fundus" / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = DATA_DIR / "media"
# Automatische Sicherungen (siehe Einstellungen → Sicherung)
BACKUP_DIR = Path(env.str("BACKUP_DIR", default=str(DATA_DIR / "sicherungen")))
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
# In der Entwicklung liefert WhiteNoise direkt aus den Quellverzeichnissen aus.
WHITENOISE_AUTOREFRESH = DEBUG
WHITENOISE_USE_FINDERS = DEBUG

# Optional: Schlüssel für Google Books als dritte Quelle beim ISBN-Abruf.
GOOGLE_BOOKS_API_KEY = env.str("GOOGLE_BOOKS_API_KEY", default="")

# Öffentliche Adresse von Fundus, für Links in E-Mails.
SITE_URL = env.str("SITE_URL", default="http://localhost:8000")

EMAIL_CONFIG = env.email_url("EMAIL_URL", default="consolemail://")
vars().update(EMAIL_CONFIG)
DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL", default="fundus@localhost")

# Ab dieser Stunde verschickt der Dienst „scheduler“ täglich die Erinnerungen.
REMINDER_HOUR = env.int("REMINDER_HOUR", default=7)
SCHEDULER_HEARTBEAT = env.str("SCHEDULER_HEARTBEAT", default="/tmp/fundus-scheduler-heartbeat")

# Anmeldesperre nach zu vielen falschen Passwörtern.
LOGIN_MAX_ATTEMPTS = env.int("LOGIN_MAX_ATTEMPTS", default=5)
LOGIN_LOCK_MINUTES = env.int("LOGIN_LOCK_MINUTES", default=15)

# Anmeldung mit Schulkonto (siehe docs/anmeldung.md). Ohne OIDC_CLIENT_ID bzw.
# LDAP_SERVER_URI ist sie aus.
AUTHENTICATION_BACKENDS = [
    "fundus.accounts.sso.PasswordBackend",
    "fundus.accounts.ldap.LDAPBackend",
    "fundus.accounts.sso.OIDCBackend",
]
OIDC_ISSUER = env.str("OIDC_ISSUER", default="")
OIDC_RP_CLIENT_ID = env.str("OIDC_CLIENT_ID", default="")
OIDC_RP_CLIENT_SECRET = env.str("OIDC_CLIENT_SECRET", default="")
OIDC_RP_SIGN_ALGO = env.str("OIDC_SIGN_ALGO", default="RS256")
OIDC_RP_SCOPES = env.str("OIDC_SCOPES", default="openid email profile")
OIDC_BUTTON_LABEL = env.str("OIDC_BUTTON_LABEL", default="Mit Schulkonto anmelden")
# Endpunkte nur nötig, wenn der Dienst kein Discovery-Dokument anbietet.
OIDC_OP_AUTHORIZATION_ENDPOINT = env.str("OIDC_AUTHORIZATION_ENDPOINT", default="")
OIDC_OP_TOKEN_ENDPOINT = env.str("OIDC_TOKEN_ENDPOINT", default="")
OIDC_OP_USER_ENDPOINT = env.str("OIDC_USERINFO_ENDPOINT", default="")
OIDC_OP_JWKS_ENDPOINT = env.str("OIDC_JWKS_ENDPOINT", default="")
OIDC_TIMEOUT = 10
OIDC_USE_PKCE = True
OIDC_CALLBACK_CLASS = "fundus.accounts.sso.OIDCCallbackView"
OIDC_AUTHENTICATE_CLASS = "fundus.accounts.sso.OIDCLoginView"
LOGIN_REDIRECT_URL_FAILURE = "/anmelden/"

LDAP_SERVER_URI = env.str("LDAP_SERVER_URI", default="")
LDAP_START_TLS = env.bool("LDAP_START_TLS", default=False)
LDAP_CA_FILE = env.str("LDAP_CA_FILE", default="")
# Nur zum Testen ohne Verschlüsselung; Passwörter gingen sonst im Klartext übers Netz.
LDAP_ALLOW_UNENCRYPTED = env.bool("LDAP_ALLOW_UNENCRYPTED", default=False)
LDAP_BIND_DN = env.str("LDAP_BIND_DN", default="")
LDAP_BIND_PASSWORD = env.str("LDAP_BIND_PASSWORD", default="")
LDAP_USER_SEARCH_BASE = env.str("LDAP_USER_SEARCH_BASE", default="")
LDAP_USER_FILTER = env.str(
    "LDAP_USER_FILTER",
    default="(|(uid={user})(mail={user})(sAMAccountName={user})(userPrincipalName={user}))",
)
LDAP_ATTR_EMAIL = env.str("LDAP_ATTR_EMAIL", default="mail")
LDAP_ATTR_FIRST_NAME = env.str("LDAP_ATTR_FIRST_NAME", default="givenName")
LDAP_ATTR_LAST_NAME = env.str("LDAP_ATTR_LAST_NAME", default="sn")
LDAP_TIMEOUT = env.int("LDAP_TIMEOUT", default=10)

# Hinter einem Reverse Proxy mit HTTPS (siehe deploy/Caddyfile.example).
BEHIND_HTTPS_PROXY = env.bool("BEHIND_HTTPS_PROXY", default=False)
if BEHIND_HTTPS_PROXY:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env.str("LOG_LEVEL", default="INFO")},
}
