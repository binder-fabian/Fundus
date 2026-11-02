from django.conf import settings
from django.contrib import messages
from django.contrib.auth import forms as auth_forms
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from fundus.accounts import teacher_import
from fundus.accounts.emails import send_invitation
from fundus.accounts.forms import (
    AbsenceForm,
    InvitationAwarePasswordResetForm,
    InviteUserForm,
    LoginForm,
    TeacherImportForm,
    UserForm,
)
from fundus.accounts.models import Role, User
from fundus.accounts.permissions import require
from fundus.accounts.tokens import invitation_token


class LoginView(auth_views.LoginView):
    form_class = LoginForm
    redirect_authenticated_user = True


class PasswordResetView(auth_views.PasswordResetView):
    form_class = InvitationAwarePasswordResetForm
    email_template_name = "registration/password_reset_email.txt"
    subject_template_name = "registration/password_reset_subject.txt"
    extra_email_context = {"site_url": settings.SITE_URL}


class InvitationAcceptView(auth_views.PasswordResetConfirmView):
    """Passwort festlegen über den Einladungslink; meldet danach direkt an."""

    token_generator = invitation_token
    template_name = "accounts/invitation_accept.html"
    post_reset_login = True
    success_url = reverse_lazy("home")
    reset_url_token = "einladung-annehmen"

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, _("Willkommen bei Fundus! Ihr Passwort ist gespeichert."))
        return response


def _notify_invitation(request, user, sent):
    if sent:
        messages.success(request, _("Einladung an %(email)s verschickt.") % {"email": user.email})
    else:
        messages.warning(
            request,
            _(
                "Die Einladung an %(email)s konnte nicht verschickt werden. "
                "Bitte die E-Mail-Einstellungen prüfen und erneut einladen."
            )
            % {"email": user.email},
        )


@require("can_manage_users")
def user_list(request):
    users = User.objects.order_by("last_name", "first_name", "email")
    return render(
        request,
        "accounts/user_list.html",
        {"users": users, "admin_count": User.objects.active_admins().count()},
    )


@require("can_manage_users")
def user_create(request):
    form = InviteUserForm(request.POST or None, initial={"role": Role.TEACHER})
    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        user.set_unusable_password()
        user.save()
        if form.cleaned_data["send_invitation"]:
            _notify_invitation(request, user, send_invitation(user, invited_by=request.user))
        else:
            messages.success(request, _("Konto für %(name)s angelegt.") % {"name": user})
        return redirect("user_list")
    return render(request, "accounts/user_form.html", {"form": form, "is_new": True})


@require("can_manage_users")
def user_edit(request, pk):
    user = get_object_or_404(User, pk=pk)
    form = UserForm(request.POST or None, instance=user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Änderungen gespeichert."))
        return redirect("user_list")
    return render(
        request, "accounts/user_form.html", {"form": form, "is_new": False, "edited": user}
    )


@require("can_manage_users")
@require_POST
def user_invite(request, pk):
    user = get_object_or_404(User, pk=pk, is_active=True)
    _notify_invitation(request, user, send_invitation(user, invited_by=request.user))
    return redirect("user_list")


SESSION_KEY = "teacher_import_rows"


@require("can_manage_users")
def teacher_import_upload(request):
    form = TeacherImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            rows = teacher_import.parse(form.cleaned_data["file"].read())
        except ValueError:
            form.add_error("file", _("Die Datei konnte nicht gelesen werden."))
        else:
            request.session[SESSION_KEY] = teacher_import.to_session(rows)
            return render(
                request,
                "accounts/teacher_import_preview.html",
                {
                    "rows": rows,
                    "new_count": len(request.session[SESSION_KEY]),
                    "statuses": teacher_import,
                },
            )
    return render(request, "accounts/teacher_import.html", {"form": form})


@require("can_manage_users")
@require_POST
def teacher_import_confirm(request):
    rows = request.session.pop(SESSION_KEY, None)
    if not rows:
        messages.warning(request, _("Keine Daten zum Importieren. Bitte die Datei neu hochladen."))
        return redirect("teacher_import")

    created = []
    with transaction.atomic():
        for row in rows:
            if User.objects.filter(email__iexact=row["email"]).exists():
                continue
            user = User(
                email=row["email"],
                first_name=row["first_name"],
                last_name=row["last_name"],
                role=Role.TEACHER,
            )
            user.set_unusable_password()
            user.save()
            created.append(user)

    failed = 0
    if request.POST.get("send_invitations"):
        failed = sum(not send_invitation(u, invited_by=request.user) for u in created)
    messages.success(request, _("%(n)d Lehrkräfte angelegt.") % {"n": len(created)})
    if failed:
        messages.warning(
            request,
            _("%(n)d Einladungen konnten nicht verschickt werden.") % {"n": failed},
        )
    return redirect("user_list")


def account(request):
    """Mein Konto: Abwesenheit eintragen und Passwort ändern."""
    absence = AbsenceForm(
        request.POST if "abwesenheit" in request.POST else None, instance=request.user
    )
    password = auth_forms.PasswordChangeForm(
        request.user, request.POST if "passwort" in request.POST else None
    )
    if request.method == "POST":
        if "abwesenheit_loeschen" in request.POST:
            request.user.absent_until = None
            request.user.save(update_fields=["absent_until"])
            messages.success(request, _("Abwesenheit gelöscht."))
            return redirect("account")
        if "abwesenheit" in request.POST and absence.is_valid():
            absence.save()
            messages.success(request, _("Abwesenheit gespeichert."))
            return redirect("account")
        if "passwort" in request.POST and password.is_valid():
            user = password.save()
            update_session_auth_hash(request, user)
            messages.success(request, _("Passwort geändert."))
            return redirect("account")
    return render(
        request,
        "accounts/account.html",
        {
            "absence": absence,
            "form": password,
            "teams": request.user.teams.all(),
        },
    )
