import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from fundus.accounts.models import Role
from fundus.catalog.models import Team
from fundus.loans import services
from tests.factories import TitleFactory, UserFactory, team_of

pytestmark = pytest.mark.django_db


def test_available_members_skip_absent_and_inactive():
    today = timezone.localdate()
    here = UserFactory()
    away = UserFactory(absent_until=today + datetime.timedelta(days=3))
    back = UserFactory(absent_until=today - datetime.timedelta(days=1))
    gone = UserFactory(is_active=False)
    team = team_of(here, away, back, gone)
    assert set(team.available_members(today)) == {here, back}


def test_team_members_have_responsible_rights():
    member, outsider = UserFactory(), UserFactory()
    title = TitleFactory(team=team_of(member))
    assert services.is_responsible(member, title)
    assert services.can_lend_for_others(member, title)
    assert not services.is_responsible(outsider, title)
    assert not services.is_responsible(member, TitleFactory())


def test_absent_member_keeps_rights():
    member = UserFactory(absent_until=timezone.localdate() + datetime.timedelta(days=5))
    title = TitleFactory(team=team_of(member))
    assert services.is_responsible(member, title)


def test_manage_teams_in_masterdata(client):
    client.force_login(UserFactory(role=Role.MANAGER))
    a, b = UserFactory(first_name="Anna"), UserFactory(first_name="Ben")
    url = reverse("masterdata_create", args=["teams"])
    client.post(url, {"name": "Diagnostik-Team", "members": [a.pk, b.pk]})
    team = Team.objects.get(name="Diagnostik-Team")
    assert set(team.members.all()) == {a, b}
    listing = client.get(reverse("masterdata_list", args=["teams"])).content.decode()
    assert "Anna" in listing and "Ben" in listing
    assert "gibt es schon" in client.post(url, {"name": "diagnostik-team"}).content.decode()


def test_team_in_use_cannot_be_deleted(client):
    client.force_login(UserFactory(role=Role.MANAGER))
    team = team_of(UserFactory())
    TitleFactory(team=team)
    client.post(reverse("masterdata_edit", args=["teams", team.pk]), {"delete": "1"})
    assert Team.objects.filter(pk=team.pk).exists()


def test_account_page_sets_and_clears_absence(client):
    user = UserFactory()
    team_of(user, name="Diagnostik-Team")
    client.force_login(user)
    page = client.get(reverse("account")).content.decode()
    assert "Diagnostik-Team" in page and "Abwesenheit" in page
    until = (timezone.localdate() + datetime.timedelta(days=7)).isoformat()
    client.post(reverse("account"), {"abwesenheit": "1", "absent_until": until})
    user.refresh_from_db()
    assert user.absent_until.isoformat() == until
    client.post(reverse("account"), {"abwesenheit_loeschen": "1"})
    user.refresh_from_db()
    assert user.absent_until is None


def test_account_page_changes_password(client):
    user = UserFactory()
    client.force_login(user)
    client.post(
        reverse("account"),
        {
            "passwort": "1",
            "old_password": "geheim-1234",
            "new_password1": "Neues-Passwort-77",
            "new_password2": "Neues-Passwort-77",
        },
    )
    user.refresh_from_db()
    assert user.check_password("Neues-Passwort-77")
    assert client.get(reverse("home")).status_code == 200  # bleibt angemeldet


def test_overview_lists_approval_titles_without_team(client):
    client.force_login(UserFactory(role=Role.MANAGER))
    TitleFactory(title="Ohne Team", approval_required=True)
    TitleFactory(title="Mit Team", approval_required=True, team=team_of(UserFactory()))
    page = client.get(reverse("loan_overview")).content.decode()
    assert "Ohne Team" in page and "Mit Team" not in page
