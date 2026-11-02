"""Anmeldung mit Schulkonto: OIDC (Microsoft Entra, Google, Keycloak …) und
gemeinsame Regeln für OIDC und LDAP.

Konten werden über die E-Mail-Adresse zugeordnet. Rollen vergibt weiter
Fundus. Neue Konten entstehen nur, wenn die Einstellung es erlaubt.

Die Adressen des Anmeldedienstes holt Fundus erst bei der ersten Anmeldung
aus dessen Discovery-Dokument; so startet Fundus auch ohne Netz, und eine
Anmeldung mit Passwort hängt nie vom Anmeldedienst ab.
"""

import logging

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.decorators import login_not_required
from django.core.exceptions import SuspiciousOperation
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.views import View
from mozilla_django_oidc.auth import OIDCAuthenticationBackend
from mozilla_django_oidc.utils import import_from_settings
from mozilla_django_oidc.views import (
    OIDCAuthenticationCallbackView,
    OIDCAuthenticationRequestView,
)

from fundus.accounts.models import Role, User

logger = logging.getLogger(__name__)


def oidc_enabled():
    return bool(settings.OIDC_RP_CLIENT_ID)


def ldap_enabled():
    return bool(settings.LDAP_SERVER_URI)


def sso_enabled():
    return oidc_enabled() or ldap_enabled()


# Discovery


class OIDCConfigError(Exception):
    pass


DISCOVERED_SETTINGS = {
    "OIDC_OP_AUTHORIZATION_ENDPOINT": "authorization_endpoint",
    "OIDC_OP_TOKEN_ENDPOINT": "token_endpoint",
    "OIDC_OP_USER_ENDPOINT": "userinfo_endpoint",
    "OIDC_OP_JWKS_ENDPOINT": "jwks_uri",
}
_discovery_cache = {}


def discovery():
    issuer = settings.OIDC_ISSUER.rstrip("/")
    if not issuer:
        raise OIDCConfigError(_("OIDC_ISSUER ist nicht gesetzt."))
    if issuer not in _discovery_cache:
        url = f"{issuer}/.well-known/openid-configuration"
        try:
            response = requests.get(url, timeout=settings.OIDC_TIMEOUT)
            response.raise_for_status()
            _discovery_cache[issuer] = response.json()
        except (requests.RequestException, ValueError) as error:
            logger.warning("OIDC-Discovery %s fehlgeschlagen: %s", url, error)
            raise OIDCConfigError(_("Der Anmeldedienst ist nicht erreichbar.")) from error
    return _discovery_cache[issuer]


def oidc_setting(attr, *args):
    """Wie mozilla_django_oidc: aus den Einstellungen, Endpunkte notfalls per
    Discovery."""
    if attr in DISCOVERED_SETTINGS and not getattr(settings, attr, ""):
        value = discovery().get(DISCOVERED_SETTINGS[attr])
        if not value:
            raise OIDCConfigError(_("Der Anmeldedienst nennt keinen %(a)s.") % {"a": attr})
        return value
    return import_from_settings(attr, *args)


# Zuordnung von Konten (OIDC und LDAP)


def _note(request, text):
    if request is not None:
        request.fundus_sso_message = text


def match_account(request, email, first_name="", last_name=""):
    """Konto zur E-Mail-Adresse – oder, wenn erlaubt, ein neues als Lehrkraft.
    None mit Hinweis für die Anmeldeseite, wenn es nicht geht."""
    from fundus.core.models import SchoolSettings

    email = (email or "").strip().lower()
    if "@" not in email:
        _note(request, _("Der Anmeldedienst hat keine E-Mail-Adresse übermittelt."))
        return None
    user = User.objects.filter(email__iexact=email).first()
    if user is not None:
        if not user.is_active:
            _note(request, _("Dieses Konto ist deaktiviert. Bitte an die Verwaltung wenden."))
            return None
        changed = []
        if not user.first_name and first_name:
            user.first_name = first_name[:150]
            changed.append("first_name")
        if not user.last_name and last_name:
            user.last_name = last_name[:150]
            changed.append("last_name")
        if changed:
            user.save(update_fields=changed)
        return user
    config = SchoolSettings.current()
    if not config.sso_create_accounts or not config.domain_allowed(email):
        _note(
            request,
            _("Für %(e)s gibt es noch kein Konto in Fundus. Bitte an die Verwaltung wenden.")
            % {"e": email},
        )
        return None
    # Ohne Passwort angelegt: Fundus-Passwort ist damit unbrauchbar.
    return User.objects.create_user(
        email=email,
        first_name=first_name[:150],
        last_name=last_name[:150],
        role=Role.TEACHER,
    )


def email_from_claims(claims):
    for key in ("email", "preferred_username", "upn"):
        value = (claims.get(key) or "").strip()
        if "@" in value:
            return value
    return ""


# OIDC


class OIDCBackend(OIDCAuthenticationBackend):
    get_settings = staticmethod(oidc_setting)

    def __init__(self, *args, **kwargs):
        # Endpunkte erst bei Bedarf (siehe Properties) – Django erzeugt Backends
        # bei jeder Anmeldung, auch bei der mit Passwort.
        self.UserModel = User

    OIDC_OP_TOKEN_ENDPOINT = property(lambda self: oidc_setting("OIDC_OP_TOKEN_ENDPOINT"))
    OIDC_OP_USER_ENDPOINT = property(lambda self: oidc_setting("OIDC_OP_USER_ENDPOINT"))
    OIDC_OP_JWKS_ENDPOINT = property(lambda self: oidc_setting("OIDC_OP_JWKS_ENDPOINT"))
    OIDC_RP_CLIENT_ID = property(lambda self: settings.OIDC_RP_CLIENT_ID)
    OIDC_RP_CLIENT_SECRET = property(lambda self: settings.OIDC_RP_CLIENT_SECRET)
    OIDC_RP_SIGN_ALGO = property(lambda self: settings.OIDC_RP_SIGN_ALGO)
    OIDC_RP_IDP_SIGN_KEY = None

    def authenticate(self, request, **kwargs):
        if not oidc_enabled():
            return None
        try:
            return super().authenticate(request, **kwargs)
        except (requests.RequestException, OIDCConfigError, SuspiciousOperation) as error:
            logger.warning("Anmeldung mit Schulkonto fehlgeschlagen: %s", error)
            return None

    def verify_claims(self, claims):
        if claims.get("email_verified") is False:
            _note(self.request, _("Die E-Mail-Adresse ist beim Anmeldedienst nicht bestätigt."))
            return False
        return True

    def filter_users_by_claims(self, claims):
        email = email_from_claims(claims)
        return User.objects.filter(email__iexact=email) if email else User.objects.none()

    def get_or_create_user(self, access_token, id_token, payload):
        claims = self.get_userinfo(access_token, id_token, payload)
        if not self.verify_claims(claims):
            return None
        return match_account(
            self.request,
            email_from_claims(claims),
            claims.get("given_name", ""),
            claims.get("family_name", ""),
        )

    def get_userinfo(self, access_token, id_token, payload):
        # Manche Dienste (z. B. Entra) liefern die E-Mail nur im ID-Token.
        try:
            info = super().get_userinfo(access_token, id_token, payload)
        except requests.RequestException:
            info = {}
        return {**payload, **info}


@method_decorator(login_not_required, name="dispatch")
class OIDCLoginView(OIDCAuthenticationRequestView):
    """Leitet zum Anmeldedienst weiter."""

    get_settings = staticmethod(oidc_setting)

    def __init__(self, *args, **kwargs):
        View.__init__(self, *args, **kwargs)

    def get(self, request):
        if not oidc_enabled():
            return redirect("login")
        try:
            self.OIDC_OP_AUTH_ENDPOINT = oidc_setting("OIDC_OP_AUTHORIZATION_ENDPOINT")
        except OIDCConfigError as error:
            messages.error(request, str(error) + " " + _("Bitte später erneut versuchen."))
            return redirect("login")
        self.OIDC_RP_CLIENT_ID = settings.OIDC_RP_CLIENT_ID
        return super().get(request)


@method_decorator(login_not_required, name="dispatch")
class OIDCCallbackView(OIDCAuthenticationCallbackView):
    get_settings = staticmethod(oidc_setting)

    def login_failure(self):
        text = getattr(self.request, "fundus_sso_message", "") or _(
            "Die Anmeldung mit Schulkonto hat nicht geklappt."
        )
        messages.error(self.request, text)
        return super().login_failure()


# Anmeldung mit Fundus-Passwort


def password_allowed(user):
    from fundus.core.models import SchoolSettings

    if user.is_admin or not sso_enabled():
        return True
    return SchoolSettings.current().password_login == SchoolSettings.PasswordLogin.ALL


class PasswordBackend(ModelBackend):
    """Wie üblich – nur dass Lehrkräfte ihr Fundus-Passwort nicht mehr nutzen
    können, wenn die Schule das auf Administratoren beschränkt hat."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        user = super().authenticate(request, username=username, password=password, **kwargs)
        if user is not None and not password_allowed(user):
            _note(request, _("Bitte melden Sie sich mit Ihrem Schulkonto an."))
            return None
        return user
