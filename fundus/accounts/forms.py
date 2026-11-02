from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm
from django.utils.translation import gettext_lazy as _

from fundus.accounts import throttle
from fundus.accounts.models import Role, User


class LoginForm(AuthenticationForm):
    username = forms.EmailField(
        label=_("E-Mail-Adresse"),
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
    )

    def clean(self):
        if throttle.is_locked(self.data.get("username"), self.request):
            raise forms.ValidationError(
                _(
                    "Zu viele falsche Versuche. Bitte in %(m)d Minuten erneut versuchen "
                    "oder „Passwort vergessen“ nutzen."
                )
                % {"m": settings.LOGIN_LOCK_MINUTES},
                code="locked",
            )
        return super().clean()


class InvitationAwarePasswordResetForm(PasswordResetForm):
    """Schickt den Link auch an Eingeladene ohne Passwort – wer die Einladung
    verloren hat, kommt so über „Passwort vergessen“ ins Konto."""

    def get_users(self, email):
        return User.objects.filter(email__iexact=email, is_active=True)


class UserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "role", "is_active"]

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data["email"]).lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(_("Es gibt bereits ein Konto mit dieser E-Mail-Adresse."))
        return email

    def clean(self):
        cleaned = super().clean()
        instance = self.instance
        was_admin = instance.pk and instance.is_active and instance.role == Role.ADMIN
        stays_admin = cleaned.get("is_active") and cleaned.get("role") == Role.ADMIN
        if was_admin and not stays_admin:
            others = User.objects.active_admins().exclude(pk=instance.pk)
            if not others.exists():
                raise forms.ValidationError(
                    _(
                        "Das ist der letzte aktive Administrator. Legen Sie zuerst "
                        "einen weiteren Administrator an."
                    )
                )
        return cleaned


class InviteUserForm(UserForm):
    send_invitation = forms.BooleanField(
        label=_("Einladung jetzt per E-Mail schicken"), required=False, initial=True
    )

    class Meta(UserForm.Meta):
        fields = ["first_name", "last_name", "email", "role"]


class TeacherImportForm(forms.Form):
    file = forms.FileField(
        label=_("CSV-Datei"),
        help_text=_(
            "Spalten: Vorname, Nachname, E-Mail. Trennzeichen Semikolon oder Komma, "
            "eine Kopfzeile ist erlaubt (z. B. Export aus Excel)."
        ),
    )

    MAX_SIZE = 1024 * 1024

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if upload.size > self.MAX_SIZE:
            raise forms.ValidationError(_("Die Datei ist zu groß (höchstens 1 MB)."))
        return upload


class AbsenceForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["absent_until"]
        widgets = {"absent_until": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}
