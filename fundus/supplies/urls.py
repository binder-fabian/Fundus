from django.urls import path

from fundus.supplies import views

urlpatterns = [
    path("material/", views.consumable_list, name="consumable_list"),
    path("material/neu/", views.consumable_edit, name="consumable_create"),
    path("material/karten/", views.cards, name="reorder_cards"),
    path("material/nachbestellungen/", views.reorder_list, name="reorder_list"),
    path(
        "material/nachbestellungen/<int:pk>/<str:action>/",
        views.notice_action,
        name="notice_action",
    ),
    path("material/<int:pk>/", views.consumable_detail, name="consumable_detail"),
    path("material/<int:pk>/bearbeiten/", views.consumable_edit, name="consumable_edit"),
    path("material/<int:pk>/nachbestellen/", views.reorder, name="consumable_reorder"),
    path("material/<int:pk>/entnehmen/", views.take, name="consumable_take"),
    path("material/<int:pk>/auffuellen/", views.restock, name="consumable_restock"),
]
