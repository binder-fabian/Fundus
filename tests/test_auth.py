import datetime
import re
from unittest import mock

import pytest
from django.core import mail
from django.urls import reverse

from fundus.accounts.emails import invitation_link
from fundus.accounts.models import Role, User
from fundus.accounts.tokens import invitation_token
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_pages_require_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert response["Location"].startswith(reverse("login"))


def test_login_with_email_ignores_case(client):
    UserFactory(email="anna@schule.de")
    response = client.post(
        reverse("login"), {"username": "Anna@Schule.de", "password": "geheim-1234"}
    )
    assert response.status_code == 302
    assert client.get("/katalog/").status_code == 200


def test_wrong_password_shows_error(client):
    UserFactory(email="anna@schule.de")
    response = client.post(reverse("login"), {"username": "anna@schule.de", "password": "x"})
    assert "stimmen nicht" in response.content.decode()


def test_deactivated_user_cannot_log_in(client):
    UserFactory(email="alt@schule.de", is_active=False)
    client.post(reverse("login"), {"username": "alt@schule.de", "password": "geheim-1234"})
    assert client.get("/").status_code == 302


def test_logout_requires_post_and_ends_session(client):
    client.force_login(UserFactory())
    response = client.post(reverse("logout"))
    assert response["Location"] == reverse("login")
    assert client.get("/").status_code == 302


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (Role.ADMIN, 200),
        (Role.MANAGER, 403),
        (Role.TEACHER, 403),
        (Role.SECRETARY, 403),
    ],
)
def test_only_admins_manage_users(client, role, expected):
    client.force_login(UserFactory(role=role))
    for name in ("user_list", "user_create", "teacher_import"):
        assert client.get(reverse(name)).status_code == expected


def test_role_capabilities():
    admin, manager, teacher = (
        UserFactory(role=r) for r in (Role.ADMIN, Role.MANAGER, Role.TEACHER)
    )
    assert admin.can_manage_users and admin.can_manage_catalog
    assert manager.can_manage_catalog and not manager.can_manage_users
    assert not teacher.can_manage_catalog and not teacher.can_manage_users
    admin.is_active = False
    assert not admin.can_manage_users


def test_admin_invites_person(client):
    admin = UserFactory(role=Role.ADMIN, first_name="Petra", last_name="Leitung")
    client.force_login(admin)
    response = client.post(
        reverse("user_create"),
        {
            "first_name": "Max",
            "last_name": "Neu",
            "email": "Max.Neu@Schule.de",
            "role": Role.TEACHER,
            "send_invitation": "on",
        },
    )
    assert response.status_code == 302
    user = User.objects.get(email="max.neu@schule.de")
    assert user.invitation_pending
    assert len(mail.outbox) == 1
    assert "Petra Leitung hat Sie zu Fundus eingeladen" in mail.outbox[0].body
    assert "/einladung/" in mail.outbox[0].body


def test_duplicate_email_is_rejected(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    UserFactory(email="max@schule.de")
    response = client.post(
        reverse("user_create"),
        {"first_name": "M", "last_name": "X", "email": "MAX@schule.de", "role": Role.TEACHER},
    )
    assert response.status_code == 200
    assert "bereits ein Konto" in response.content.decode()


def test_invitation_link_sets_password_and_logs_in(client):
    user = UserFactory(email="neu@schule.de")
    user.set_unusable_password()
    user.save()
    path = invitation_link(user).removeprefix("http://localhost:8000")

    response = client.get(path, follow=True)
    assert "Passwort festlegen" in response.content.decode()
    form_url = response.redirect_chain[-1][0]
    response = client.post(
        form_url, {"new_password1": "Sonnenblume-42", "new_password2": "Sonnenblume-42"}
    )
    assert response["Location"] == "/"
    user.refresh_from_db()
    assert user.check_password("Sonnenblume-42")
    assert client.get("/katalog/").status_code == 200

    # Der Link funktioniert nur einmal.
    client.logout()
    assert "Einladung ungültig" in client.get(path, follow=True).content.decode()


def test_invitation_token_expires(settings):
    settings.INVITATION_TIMEOUT_DAYS = 14
    user = UserFactory()
    user.set_unusable_password()
    user.save()
    token = invitation_token.make_token(user)
    now = datetime.datetime.now()
    with mock.patch.object(
        invitation_token, "_now", return_value=now + datetime.timedelta(days=13)
    ):
        assert invitation_token.check_token(user, token)
    with mock.patch.object(
        invitation_token, "_now", return_value=now + datetime.timedelta(days=15)
    ):
        assert not invitation_token.check_token(user, token)


def test_password_reset_reaches_invited_user_without_password(client):
    user = UserFactory(email="verloren@schule.de")
    user.set_unusable_password()
    user.save()
    client.post(reverse("password_reset"), {"email": "verloren@schule.de"})
    assert len(mail.outbox) == 1
    assert re.search(r"http://localhost:8000/passwort-neu/\S+/\S+/", mail.outbox[0].body)


def test_last_admin_cannot_be_demoted_or_deactivated(client):
    admin = UserFactory(role=Role.ADMIN)
    client.force_login(admin)
    data = {
        "first_name": admin.first_name,
        "last_name": admin.last_name,
        "email": admin.email,
        "role": Role.TEACHER,
        "is_active": "on",
    }
    response = client.post(reverse("user_edit", args=[admin.pk]), data)
    assert "letzte aktive Administrator" in response.content.decode()
    admin.refresh_from_db()
    assert admin.role == Role.ADMIN

    UserFactory(role=Role.ADMIN)
    response = client.post(reverse("user_edit", args=[admin.pk]), data)
    assert response.status_code == 302
    admin.refresh_from_db()
    assert admin.role == Role.TEACHER


def test_role_changes_are_recorded_in_history():
    user = UserFactory(role=Role.TEACHER)
    user.role = Role.MANAGER
    user.save()
    assert [h.role for h in user.history.all()] == [Role.MANAGER, Role.TEACHER]
    assert not hasattr(user.history.first(), "password")


def test_admin_hint_when_only_one_admin(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    assert "mindestens zwei" in client.get(reverse("user_list")).content.decode()
