import csv
import io
import zipfile

import pytest
from django.urls import reverse

from fundus.accounts.models import FailedLogin, Role, User
from fundus.catalog.models import Team
from fundus.loans import requests, services
from fundus.loans.models import Loan
from tests.factories import CopyFactory, TitleFactory, UserFactory, team_of

pytestmark = pytest.mark.django_db


def read_zip(content):
    archive = zipfile.ZipFile(io.BytesIO(content))
    return {
        name: list(csv.reader(io.StringIO(archive.read(name).decode("utf-8-sig")), delimiter=";"))
        for name in archive.namelist()
        if name.endswith(".csv")
    }


@pytest.fixture
def admin():
    return UserFactory(role=Role.ADMIN)


def test_delete_account_anonymizes_and_cleans_history(client, admin):
    leaving, member = UserFactory(email="weg@schule.de"), UserFactory()
    team = team_of(leaving, member, name="Diagnostik-Team")
    copy = CopyFactory()
    returned = services.lend(copy, by=leaving)
    services.return_copy(copy, by=leaving)
    title = TitleFactory(approval_required=True, team=team)
    pending = requests.request_title(title, leaving, message="bitte")
    other = requests.request_title(title, UserFactory())
    requests.approve(other, leaving)
    FailedLogin.objects.create(username="weg@schule.de")

    client.force_login(admin)
    page = client.get(reverse("user_delete", args=[leaving.pk])).content.decode()
    assert "Endgültig löschen" in page and "„Diagnostik-Team“" in page
    client.post(reverse("user_delete", args=[leaving.pk]))

    assert not User.objects.filter(pk=leaving.pk).exists()
    assert not User.history.filter(id=leaving.pk).exists()
    returned.refresh_from_db()
    pending.refresh_from_db()
    other.refresh_from_db()
    assert returned.anonymized_at and returned.borrower is None
    assert pending.status == Loan.Status.WITHDRAWN and pending.message == ""
    assert other.approved_by is None
    assert not Loan.history.filter(approved_by=leaving.pk).exists()
    assert not Loan.history.filter(borrower=leaving.pk).exists()
    assert list(Team.objects.get(pk=team.pk).members.all()) == [member]
    assert not FailedLogin.objects.exists()


def test_cannot_delete_with_lent_copy_or_self_or_last_admin(client, admin):
    borrower = UserFactory()
    services.lend(CopyFactory(), by=borrower)
    client.force_login(admin)
    page = client.post(reverse("user_delete", args=[borrower.pk])).content.decode()
    assert "noch 1 Exemplar(e) ausgeliehen" in page
    assert User.objects.filter(pk=borrower.pk).exists()

    page = client.post(reverse("user_delete", args=[admin.pk])).content.decode()
    assert "eigene Konto" in page and "mindestens eine" in page
    assert User.objects.filter(pk=admin.pk).exists()


def test_only_admins_delete_accounts(client):
    client.force_login(UserFactory(role=Role.MANAGER))
    target = UserFactory()
    assert client.post(reverse("user_delete", args=[target.pk])).status_code == 403


def test_my_data_contains_own_loans_and_changes(client):
    me = UserFactory(first_name="Erika", email="erika@schule.de")
    team_of(me, name="Lesekoffer")
    copy = CopyFactory(title=TitleFactory(title="Lesetest 3"))
    services.lend(copy, by=me)
    services.lend(CopyFactory(title=TitleFactory(title="Fremder Titel")), by=UserFactory())
    client.force_login(me)
    title = TitleFactory()
    client.post(  # Änderung über die Oberfläche → Protokoll mit Namen
        reverse("account"), {"abwesenheit": "1", "absent_until": "2030-01-01"}
    )

    response = client.get(reverse("my_data"))
    assert response["Content-Type"] == "application/zip"
    files = read_zip(response.content)
    assert files["konto.csv"][1][0] == "erika@schule.de"
    assert files["teams.csv"][1] == ["Lesekoffer"]
    loans = files["ausleihen_und_anfragen.csv"]
    assert len(loans) == 2 and loans[1][0] == "Lesetest 3"
    assert any("Benutzer" in row[1] for row in files["aenderungsprotokoll.csv"][1:])
    assert title  # Titel ohne Bezug zu mir taucht nicht auf
    assert all("Fremder Titel" not in "".join(r) for r in loans)


def test_account_page_links_my_data(client):
    client.force_login(UserFactory())
    assert reverse("my_data") in client.get(reverse("account")).content.decode()
