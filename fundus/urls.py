from django.conf import settings
from django.urls import include, path

from fundus.core import pwa
from fundus.core import views as core_views
from fundus.loans import views as loan_views

urlpatterns = [
    path("", loan_views.home, name="home"),
    path("health", core_views.health, name="health"),
    path("manifest.webmanifest", pwa.manifest, name="manifest"),
    path("sw.js", pwa.service_worker, name="service_worker"),
    path("offline/", pwa.offline, name="offline"),
    path("einstellungen/", core_views.school_settings, name="school_settings"),
    path("", include("fundus.accounts.urls")),
    path("", include("fundus.catalog.urls")),
    path("", include("fundus.transfer.urls")),
    path("", include("fundus.loans.urls")),
    path("", include("fundus.supplies.urls")),
    # Coverbilder aus dem Datenverzeichnis; nur für angemeldete Personen.
    path(settings.MEDIA_URL.lstrip("/") + "<path:path>", core_views.media, name="media"),
]
