from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from fundus.accounts import views

urlpatterns = [
    path("anmelden/", views.LoginView.as_view(), name="login"),
    path("abmelden/", auth_views.LogoutView.as_view(), name="logout"),
    path("passwort-vergessen/", views.PasswordResetView.as_view(), name="password_reset"),
    path(
        "passwort-vergessen/gesendet/",
        auth_views.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "passwort-neu/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "passwort-neu/fertig/",
        auth_views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    path("konto/", views.account, name="account"),
    path(
        "passwort-aendern/",
        auth_views.PasswordChangeView.as_view(success_url=reverse_lazy("password_change_done")),
        name="password_change",
    ),
    path(
        "passwort-aendern/fertig/",
        auth_views.PasswordChangeDoneView.as_view(),
        name="password_change_done",
    ),
    path(
        "einladung/<uidb64>/<token>/",
        views.InvitationAcceptView.as_view(),
        name="invitation_accept",
    ),
    path("benutzer/", views.user_list, name="user_list"),
    path("benutzer/neu/", views.user_create, name="user_create"),
    path("benutzer/import/", views.teacher_import_upload, name="teacher_import"),
    path(
        "benutzer/import/bestaetigen/",
        views.teacher_import_confirm,
        name="teacher_import_confirm",
    ),
    path("benutzer/<int:pk>/", views.user_edit, name="user_edit"),
    path("benutzer/<int:pk>/einladen/", views.user_invite, name="user_invite"),
]
