from django.urls import path

from fundus.transfer import views

urlpatterns = [
    path("import/", views.upload, name="import_upload"),
    path("import/zuordnung/", views.mapping, name="import_mapping"),
    path("import/vorschau/", views.preview, name="import_preview"),
    path("import/starten/", views.confirm, name="import_confirm"),
    path("import/bericht.csv", views.report, name="import_report"),
    path("export/", views.export_page, name="export_page"),
]
