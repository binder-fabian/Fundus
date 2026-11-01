from django.urls import include, path

from fundus.core import views as core_views

urlpatterns = [
    path("", core_views.home, name="home"),
    path("health", core_views.health, name="health"),
    path("", include("fundus.accounts.urls")),
]
