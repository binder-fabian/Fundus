from django.conf import settings
from django.urls import include, path

from fundus.core import views as core_views

urlpatterns = [
    path("", core_views.home, name="home"),
    path("health", core_views.health, name="health"),
    path("", include("fundus.accounts.urls")),
    path("", include("fundus.catalog.urls")),
    # Coverbilder aus dem Datenverzeichnis; nur für angemeldete Personen.
    path(settings.MEDIA_URL.lstrip("/") + "<path:path>", core_views.media, name="media"),
]
