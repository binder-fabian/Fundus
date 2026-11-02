import pytest
import requests
from django.contrib.auth import get_user
from django.urls import reverse
from ldap3 import MOCK_SYNC, Connection, Server
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

from fundus.accounts import ldap, sso
from fundus.accounts.models import Role, User
from fundus.core.models import SchoolSettings
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db

DISCOVERY = {
    "authorization_endpoint": "https://idp.test/auth",
    "token_endpoint": "https://idp.test/token",
    "userinfo_endpoint": "https://idp.test/userinfo",
    "jwks_uri": "https://idp.test/jwks",
}


class FakeResponse:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


@pytest.fixture(autouse=True)
def clear_discovery():
    sso._discovery_cache.clear()
    yield
    sso._discovery_cache.clear()


@pytest.fixture
def oidc(settings, monkeypatch):
    settings.OIDC_ISSUER = "https://idp.test/realms/schule"
    settings.OIDC_RP_CLIENT_ID = "fundus"
    settings.OIDC_RP_CLIENT_SECRET = "geheim"
    calls = []

    def fake_get(url, timeout=None):
        calls.append(url)
        return FakeResponse(DISCOVERY)

    monkeypatch.setattr(sso.requests, "get", fake_get)
    return calls


def configure(**values):
    config = SchoolSettings.current()
    for key, value in values.items():
        setattr(config, key, value)
    config.save()


# Discovery und Zuordnung


def test_discovery_is_fetched_once_and_cached(oidc):
    assert sso.oidc_setting("OIDC_OP_TOKEN_ENDPOINT") == "https://idp.test/token"
    assert sso.oidc_setting("OIDC_OP_JWKS_ENDPOINT") == "https://idp.test/jwks"
    assert oidc == ["https://idp.test/realms/schule/.well-known/openid-configuration"]


def test_explicit_endpoints_win(oidc, settings):
    settings.OIDC_OP_TOKEN_ENDPOINT = "https://anders.test/token"
    assert sso.oidc_setting("OIDC_OP_TOKEN_ENDPOINT") == "https://anders.test/token"
    assert oidc == []


def test_discovery_failure(settings, monkeypatch):
    settings.OIDC_ISSUER = "https://idp.test"

    def broken(url, timeout=None):
        raise requests.ConnectionError("weg")

    monkeypatch.setattr(sso.requests, "get", broken)
    with pytest.raises(sso.OIDCConfigError, match="nicht erreichbar"):
        sso.oidc_setting("OIDC_OP_TOKEN_ENDPOINT")


class Req:
    pass


def test_match_account_rules():
    teacher = UserFactory(email="t.lehrer@schule.de", first_name="", last_name="")
    request = Req()
    assert sso.match_account(request, "T.Lehrer@Schule.de", "Tina", "Lehrer") == teacher
    teacher.refresh_from_db()
    assert teacher.get_full_name() == "Tina Lehrer"

    teacher.is_active = False
    teacher.save()
    assert sso.match_account(request, "t.lehrer@schule.de") is None
    assert "deaktiviert" in request.fundus_sso_message

    assert sso.match_account(request, "neu@schule.de") is None
    assert "noch kein Konto" in request.fundus_sso_message
    assert not User.objects.filter(email="neu@schule.de").exists()

    configure(sso_create_accounts=True, sso_domains="schule.de, @foerderzentrum.de")
    assert sso.match_account(request, "fremd@andere.de") is None
    user = sso.match_account(request, "Neu@Foerderzentrum.de", "Nina", "Neu")
    assert user.email == "neu@foerderzentrum.de" and user.role == Role.TEACHER
    assert not user.has_usable_password()


def test_oidc_claims(oidc, monkeypatch):
    UserFactory(email="anna@schule.de")
    backend = sso.OIDCBackend()
    backend.request = Req()
    claims = {"preferred_username": "anna@schule.de", "given_name": "Anna"}
    monkeypatch.setattr(OIDCAuthenticationBackend, "get_userinfo", lambda *a: claims)
    assert backend.get_or_create_user("a", "i", {}).email == "anna@schule.de"

    claims = {"email": "anna@schule.de", "email_verified": False}
    assert backend.get_or_create_user("a", "i", {}) is None
    assert "nicht bestätigt" in backend.request.fundus_sso_message

    # E-Mail nur im ID-Token (z. B. Entra)
    def no_userinfo(*args):
        raise requests.HTTPError("401")

    monkeypatch.setattr(OIDCAuthenticationBackend, "get_userinfo", no_userinfo)
    user = backend.get_or_create_user("a", "i", {"email": "anna@schule.de"})
    assert user.email == "anna@schule.de"


# Ablauf im Browser


def test_full_oidc_login(client, oidc, monkeypatch):
    UserFactory(email="anna@schule.de", role=Role.TEACHER)
    page = client.get(reverse("login")).content.decode()
    assert "Mit Schulkonto anmelden" in page

    response = client.get(reverse("oidc_authentication_init"))
    assert response.status_code == 302
    assert response["Location"].startswith("https://idp.test/auth?")
    state = next(iter(client.session["oidc_states"]))

    monkeypatch.setattr(
        sso.OIDCBackend, "get_token", lambda self, payload: {"id_token": "i", "access_token": "a"}
    )
    monkeypatch.setattr(sso.OIDCBackend, "verify_token", lambda self, token, **kw: {"sub": "1"})
    monkeypatch.setattr(
        OIDCAuthenticationBackend, "get_userinfo", lambda *a: {"email": "anna@schule.de"}
    )
    response = client.get(reverse("oidc_authentication_callback"), {"code": "c", "state": state})
    assert response.status_code == 302 and response["Location"] == "/"
    assert get_user(client).email == "anna@schule.de"


def test_oidc_login_without_account_shows_hint(client, oidc, monkeypatch):
    client.get(reverse("oidc_authentication_init"))
    state = next(iter(client.session["oidc_states"]))
    monkeypatch.setattr(
        sso.OIDCBackend, "get_token", lambda self, payload: {"id_token": "i", "access_token": "a"}
    )
    monkeypatch.setattr(sso.OIDCBackend, "verify_token", lambda self, token, **kw: {"sub": "1"})
    monkeypatch.setattr(
        OIDCAuthenticationBackend, "get_userinfo", lambda *a: {"email": "wer@schule.de"}
    )
    response = client.get(
        reverse("oidc_authentication_callback"), {"code": "c", "state": state}, follow=True
    )
    assert "noch kein Konto" in response.content.decode()
    assert not get_user(client).is_authenticated


def test_unreachable_idp_does_not_break_password_login(client, settings, monkeypatch):
    settings.OIDC_ISSUER = "https://idp.test"
    settings.OIDC_RP_CLIENT_ID = "fundus"

    def broken(url, timeout=None):
        raise requests.ConnectionError("weg")

    monkeypatch.setattr(sso.requests, "get", broken)
    UserFactory(email="t@schule.de")
    response = client.post(reverse("login"), {"username": "t@schule.de", "password": "geheim-1234"})
    assert response.status_code == 302
    client.logout()
    response = client.get(reverse("oidc_authentication_init"), follow=True)
    assert "nicht erreichbar" in response.content.decode()


def test_password_login_only_for_admins(client, oidc):
    configure(password_login="admins")
    UserFactory(email="t@schule.de", role=Role.TEACHER)
    UserFactory(email="admin@schule.de", role=Role.ADMIN)
    page = client.get(reverse("login")).content.decode()
    assert "nur Administratoren" in page
    response = client.post(reverse("login"), {"username": "t@schule.de", "password": "geheim-1234"})
    assert "mit Ihrem Schulkonto an" in response.content.decode()
    response = client.post(
        reverse("login"), {"username": "admin@schule.de", "password": "geheim-1234"}
    )
    assert response.status_code == 302


def test_admins_only_setting_has_no_effect_without_sso(client):
    configure(password_login="admins")
    UserFactory(email="t@schule.de", role=Role.TEACHER)
    response = client.post(reverse("login"), {"username": "t@schule.de", "password": "geheim-1234"})
    assert response.status_code == 302


# LDAP


@pytest.fixture
def directory(settings, monkeypatch):
    settings.LDAP_SERVER_URI = "ldaps://schulserver.test"
    settings.LDAP_BIND_DN = "cn=fundus,dc=schule"
    settings.LDAP_BIND_PASSWORD = "dienst"
    settings.LDAP_USER_SEARCH_BASE = "ou=people,dc=schule"
    srv = Server("schulserver")
    setup = Connection(
        srv, user="cn=fundus,dc=schule", password="dienst", client_strategy=MOCK_SYNC
    )
    setup.strategy.add_entry("cn=fundus,dc=schule", {"userPassword": "dienst", "sn": "fundus"})
    setup.strategy.add_entry(
        "uid=mmuster,ou=people,dc=schule",
        {
            "objectClass": "inetOrgPerson",
            "uid": "mmuster",
            "userPassword": "schulpasswort",
            "mail": "m.muster@schule.de",
            "givenName": "Max",
            "sn": "Muster",
        },
    )
    monkeypatch.setattr(ldap, "server", lambda: srv)
    monkeypatch.setattr(
        ldap,
        "connection",
        lambda s, user=None, password=None: Connection(
            s, user=user, password=password, client_strategy=MOCK_SYNC
        ),
    )
    return srv


def test_ldap_login_with_username(client, directory):
    UserFactory(email="m.muster@schule.de", first_name="", last_name="")
    page = client.get(reverse("login")).content.decode()
    assert "Benutzername oder E-Mail-Adresse" in page
    response = client.post(reverse("login"), {"username": "mmuster", "password": "schulpasswort"})
    assert response.status_code == 302
    user = get_user(client)
    assert user.email == "m.muster@schule.de" and user.get_full_name() == "Max Muster"


def test_ldap_wrong_password_and_unknown_account(client, directory):
    UserFactory(email="m.muster@schule.de")
    response = client.post(reverse("login"), {"username": "mmuster", "password": "falsch"})
    assert "stimmen nicht" in response.content.decode()
    User.objects.all().delete()
    response = client.post(reverse("login"), {"username": "mmuster", "password": "schulpasswort"})
    assert "noch kein Konto" in response.content.decode()


def test_ldap_filter_is_escaped(directory):
    assert ldap.find_user("*") is None
    assert ldap.find_user("mmuster)(uid=*") is None
    assert ldap.find_user("m.muster@schule.de")[0] == "uid=mmuster,ou=people,dc=schule"


def test_ldap_requires_encryption(directory, settings):
    UserFactory(email="m.muster@schule.de")
    settings.LDAP_SERVER_URI = "ldap://schulserver.test"
    assert ldap.LDAPBackend().authenticate(None, "mmuster", "schulpasswort") is None
    settings.LDAP_START_TLS = True
    assert ldap.encrypted()
    settings.LDAP_START_TLS = False
    settings.LDAP_ALLOW_UNENCRYPTED = True
    assert ldap.LDAPBackend().authenticate(None, "mmuster", "schulpasswort").email == (
        "m.muster@schule.de"
    )
