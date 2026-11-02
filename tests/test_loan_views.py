import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from fundus.accounts.models import Role
from fundus.catalog.models import Copy
from fundus.loans.models import Loan
from tests.factories import (
    CategoryFactory,
    CopyFactory,
    LoanFactory,
    TitleFactory,
    UserFactory,
    team_of,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def teacher(client):
    user = UserFactory(role=Role.TEACHER, first_name="Tina", last_name="Lehrer")
    client.force_login(user)
    return user


def copy_with(**title):
    return CopyFactory(
        inventory_number="FS-0001",
        title=TitleFactory(category=CategoryFactory(default_loan_days=14), **title),
    )


def due_in(days):
    return (timezone.localdate() + datetime.timedelta(days=days)).isoformat()


def test_scan_opens_copy(client, teacher):
    copy = copy_with()
    assert client.get("/s/fs-0001")["Location"] == reverse("copy_detail", args=[copy.pk])
    response = client.get(reverse("scan_lookup"), {"nummer": " FS-0001 "})
    assert response["Location"] == reverse("copy_detail", args=[copy.pk])
    response = client.get("/s/GIBTSNICHT", follow=True)
    assert "Keine Inventarnummer" in response.content.decode()


def test_lend_return_cycle_on_copy_page(client, teacher):
    copy = copy_with()
    page = client.get(reverse("copy_detail", args=[copy.pk])).content.decode()
    assert "Verfügbar" in page and f'value="{due_in(14)}"' in page

    response = client.post(reverse("lend", args=[copy.pk]), {"due_date": due_in(7)}, follow=True)
    content = response.content.decode()
    assert "Ausgeliehen bis" in content and "von Ihnen" in content
    loan = Loan.objects.get(copy=copy, status=Loan.Status.LENT)
    assert loan.borrower == teacher and loan.due_date.isoformat() == due_in(7)

    home = client.get(reverse("home")).content.decode()
    assert copy.title.title in home and "Verlängern" in home

    client.post(reverse("give_back", args=[copy.pk]))
    loan.refresh_from_db()
    assert loan.status == Loan.Status.RETURNED


def test_other_teacher_sees_no_name_but_can_return(client, teacher):
    copy = copy_with()
    LoanFactory(copy=copy, borrower=UserFactory(first_name="Geheim", last_name="Name"))
    page = client.get(reverse("copy_detail", args=[copy.pk])).content.decode()
    assert "Ausgeliehen bis" in page and "Zurückgeben" in page
    assert "Geheim" not in page
    client.post(reverse("give_back", args=[copy.pk]))
    assert not Loan.objects.filter(copy=copy, status=Loan.Status.LENT).exists()


def test_teacher_cannot_return_approval_required_title(client, teacher):
    copy = copy_with(approval_required=True, team=team_of(UserFactory()))
    LoanFactory(copy=copy, borrower=teacher)
    page = client.get(reverse("copy_detail", args=[copy.pk])).content.decode()
    assert "Zurückgeben</button>" not in page and "Zurückbuchen bitte über" in page
    client.post(reverse("give_back", args=[copy.pk]))
    assert Loan.objects.filter(copy=copy, status=Loan.Status.LENT).exists()


def test_manager_sees_name_and_lends_for_teacher(client):
    manager = UserFactory(role=Role.MANAGER)
    other = UserFactory(first_name="Bea", last_name="Beispiel")
    client.force_login(manager)
    copy = copy_with()
    client.post(reverse("lend", args=[copy.pk]), {"due_date": due_in(14), "borrower": other.pk})
    loan = Loan.objects.get(copy=copy)
    assert loan.borrower == other and loan.handed_over_by == manager
    page = client.get(reverse("copy_detail", args=[copy.pk])).content.decode()
    assert "bei Bea Beispiel" in page and "Zurückgeben" in page


def test_teacher_cannot_smuggle_borrower(client, teacher):
    copy = copy_with()
    client.post(
        reverse("lend", args=[copy.pk]), {"due_date": due_in(14), "borrower": UserFactory().pk}
    )
    assert Loan.objects.get(copy=copy).borrower == teacher


def test_approval_required_shows_contact(client, teacher):
    copy = copy_with(approval_required=True, team=team_of(UserFactory(), name="Zoras Team"))
    page = client.get(reverse("copy_detail", args=[copy.pk])).content.decode()
    assert "Freigabepflichtig: Bitte an Zoras Team wenden" in page
    assert "Ausleihen</button>" not in page


def test_return_with_contents_check(client, teacher):
    copy = copy_with(contents="Manual\nTestheft\nSchablone")
    LoanFactory(copy=copy, borrower=teacher)
    page = client.get(reverse("copy_detail", args=[copy.pk])).content.decode()
    assert "Inhalt prüfen" in page and "Schablone" in page
    response = client.post(
        reverse("give_back", args=[copy.pk]), {"part_0": "1", "part_2": "1"}, follow=True
    )
    assert "unvollständig markiert: Testheft" in response.content.decode()
    copy.refresh_from_db()
    assert copy.incomplete and "Testheft" in copy.note


def test_extend_from_home(client, teacher):
    copy = copy_with()
    loan = LoanFactory(copy=copy, borrower=teacher, due_date=timezone.localdate())
    client.post(reverse("extend", args=[loan.pk]), {"weiter": reverse("home")})
    loan.refresh_from_db()
    assert loan.due_date.isoformat() == due_in(14)


def test_past_due_date_rejected(client, teacher):
    copy = copy_with()
    response = client.post(reverse("lend", args=[copy.pk]), {"due_date": due_in(-1)}, follow=True)
    assert "Vergangenheit" in response.content.decode()
    assert not Loan.objects.exists()


def test_overview_for_managers(client):
    client.force_login(UserFactory(role=Role.TEACHER))
    assert client.get(reverse("loan_overview")).status_code == 403

    client.force_login(UserFactory(role=Role.MANAGER))
    late = LoanFactory(due_date=timezone.localdate() - datetime.timedelta(days=2))
    LoanFactory()
    incomplete = CopyFactory(incomplete=True)
    page = client.get(reverse("loan_overview")).content.decode()
    assert "Offen (2)" in page and "Überfällig (1)" in page
    assert incomplete.inventory_number in page
    overdue = client.get(reverse("loan_overview"), {"ansicht": "ueberfaellig"}).content.decode()
    assert late.copy.inventory_number in overdue
    by_teacher = client.get(
        reverse("loan_overview"), {"lehrkraft": late.borrower_id}
    ).content.decode()
    assert late.copy.inventory_number in by_teacher


def test_not_lendable_title_has_no_actions(client, teacher):
    copy = copy_with(lendable=False)
    page = client.get(reverse("copy_detail", args=[copy.pk])).content.decode()
    assert "Ausleihen</button>" not in page and "Verfügbar" not in page
    assert Copy.objects.count() == 1
