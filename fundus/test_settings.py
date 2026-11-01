"""Einstellungen für die Tests.

DATABASE_URL wird wie im Betrieb gelesen, damit dieselben Tests gegen SQLite
(Standard) und PostgreSQL laufen.
"""

import os
import tempfile

os.environ.setdefault("SECRET_KEY", "nur-fuer-tests")
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="fundus-test-"))

from fundus.settings import *  # noqa: E402, F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
WHITENOISE_AUTOREFRESH = True
WHITENOISE_USE_FINDERS = True
