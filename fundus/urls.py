from django.conf import settings
from django.urls import include, path

from fundus.core import views as core_views

urlpatterns = [
    path("", core_views.home, name="home"),
    path("health", core_views.health, name="health"),
    path("einstellungen/", core_views.school_settings, name="school_settings"),
    path("", include("fundus.accounts.urls")),
    path("", include("fundus.catalog.urls")),
    path("", include("fundus.transfer.urls")),
    # Coverbilder aus dem Datenverzeichnis; nur für angemeldete Personen.
    path(settings.MEDIA_URL.lstrip("/") + "<path:path>", core_views.media, name="media"),
]
