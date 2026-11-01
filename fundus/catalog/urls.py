from django.urls import path

from fundus.catalog import views, views_labels

urlpatterns = [
    path("katalog/", views.title_list, name="title_list"),
    path("katalog/neu/", views.title_create, name="title_create"),
    path("katalog/erfassen/", views.bulk_start, name="bulk_start"),
    path("katalog/erfassen/vorschau/", views.bulk_preview, name="bulk_preview"),
    path("katalog/erfassen/zeile/<str:isbn>/", views.bulk_row, name="bulk_row"),
    path("katalog/<int:pk>/", views.title_detail, name="title_detail"),
    path("katalog/<int:pk>/cover-holen/", views.fetch_cover, name="fetch_cover"),
    path("katalog/<int:pk>/bearbeiten/", views.title_edit, name="title_edit"),
    path("katalog/<int:pk>/loeschen/", views.title_delete, name="title_delete"),
    path("katalog/<int:pk>/exemplare/neu/", views.copies_add, name="copies_add"),
    path("katalog/etiketten/", views_labels.labels_page, name="labels"),
    path("plakat.pdf", views_labels.poster, name="poster"),
    path("exemplar/<int:pk>/", views.copy_detail, name="copy_detail"),
    path("exemplar/<int:pk>/bearbeiten/", views.copy_edit, name="copy_edit"),
    path("exemplar/<int:pk>/loeschen/", views.copy_delete, name="copy_delete"),
    path("verlauf/<str:kind>/<int:pk>/", views.history, name="history"),
    path(
        "verlauf/<str:kind>/wiederherstellen/<int:history_id>/",
        views.history_restore,
        name="history_restore",
    ),
    path("stammdaten/<str:kind>/", views.masterdata_list, name="masterdata_list"),
    path("stammdaten/<str:kind>/neu/", views.masterdata_edit, name="masterdata_create"),
    path("stammdaten/<str:kind>/<int:pk>/", views.masterdata_edit, name="masterdata_edit"),
]
