import datetime

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from fundus.accounts.models import Role
from fundus.core.models import SchoolSettings
from fundus.loans import requests, services
from fundus.loans.models import Loan
from fundus.loans.services import LoanError
from tests.factories import CategoryFactory, CopyFactory, TitleFactory, UserFactory, team_of

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup():
    teacher = UserFactory(first_name="Tina", last_name="Lehrer")
    anna = UserFactory(first_name="Anna", last_name="Team")
    ben = UserFactory(first_name="Ben", last_name="Team")
    title = TitleFactory(
        title="ELFE II",
        approval_required=True,
        team=team_of(anna, ben, name="Diagnostik-Team"),
        category=CategoryFactory(default_loan_days=14),
    )
    copy = CopyFactory(title=title, inventory_number="T-1")
    return teacher, anna, ben, title, copy


def test_request_notifies_available_team_members(setup):
    teacher, anna, ben, title, _copy = setup
    ben.absent_until = timezone.localdate() + datetime.timedelta(days=2)
    ben.save()
    loan = requests.request_title(title, by=teacher, message="für die 3b")
    assert loan.status == Loan.Status.REQUESTED and loan.copy is None
    assert mail.outbox[0].to == [anna.email]
    assert "Tina Lehrer" in mail.outbox[0].subject and "für die 3b" in mail.outbox[0].body


def test_request_goes_to_management_when_team_absent(setup):
    teacher, anna, ben, title, _copy = setup
    for member in (anna, ben):
        member.absent_until = timezone.localdate()
        member.save()
    manager = UserFactory(role=Role.MANAGER)
    requests.request_title(title, by=teacher)
    assert mail.outbox[0].to == [manager.email]


def test_only_one_open_request_per_person(setup):
    teacher, *_rest, title, _copy = setup
    requests.request_title(title, by=teacher)
    with pytest.raises(LoanError, match="bereits angefragt"):
        requests.request_title(title, by=teacher)


def test_request_only_for_approval_titles(setup):
    teacher = setup[0]
    with pytest.raises(LoanError, match="keine Anfrage nötig"):
        requests.request_title(TitleFactory(), by=teacher)


def test_approve_and_hand_over(setup):
    teacher, anna, ben, title, copy = setup
    loan = requests.request_title(title, by=teacher)
    with pytest.raises(LoanError, match="zuständige Team"):
        requests.approve(loan, by=UserFactory())
    requests.approve(loan, by=anna)
    assert "Genehmigt" in mail.outbox[-1].subject and mail.outbox[-1].to == [teacher.email]

    loan = requests.hand_over(loan, copy, by=ben)
    assert loan.status == Loan.Status.LENT and loan.copy == copy
    assert loan.approved_by == anna and loan.handed_over_by == ben
    assert loan.due_date == timezone.localdate() + datetime.timedelta(days=14)
    assert services.can_return(ben, loan) and not services.can_return(teacher, loan)


def test_hand_over_without_prior_approval_uses_wished_until(setup):
    teacher, anna, _ben, title, copy = setup
    wish = timezone.localdate() + datetime.timedelta(days=5)
    loan = requests.request_title(title, by=teacher, wished_until=wish)
    loan = requests.hand_over(loan, copy, by=anna)
    assert loan.approved_by == anna and loan.due_date == wish


def test_hand_over_checks_title_and_availability(setup):
    teacher, anna, _ben, title, copy = setup
    loan = requests.request_title(title, by=teacher)
    with pytest.raises(LoanError, match="anderen Titel"):
        requests.hand_over(loan, CopyFactory(), by=anna)
    other = requests.request_title(title, by=UserFactory())
    requests.hand_over(other, copy, by=anna)
    with pytest.raises(LoanError, match="bereits ausgeliehen"):
        requests.hand_over(loan, copy, by=anna)


def test_reject_and_withdraw(setup):
    teacher, anna, _ben, title, _copy = setup
    loan = requests.request_title(title, by=teacher)
    requests.reject(loan, by=anna, reason="gerade in Wartung")
    assert "gerade in Wartung" in mail.outbox[-1].body
    loan = requests.request_title(title, by=teacher)
    with pytest.raises(LoanError, match="anfragende Person"):
        requests.withdraw(loan, by=anna)
    assert requests.withdraw(loan, by=teacher).status == Loan.Status.WITHDRAWN


def test_open_request_blocks_extension_of_other_loan(setup):
    teacher, anna, _ben, title, copy = setup
    lent = services.lend(copy, by=anna, borrower=teacher)
    requests.request_title(title, by=UserFactory())
    with pytest.raises(LoanError, match="Anfrage"):
        services.extend(lent, by=teacher)


def test_daily_tasks_remind_team_and_expire(setup):
    teacher, anna, ben, title, _copy = setup
    today = timezone.localdate()
    stale = requests.request_title(title, by=teacher)
    Loan.objects.filter(pk=stale.pk).update(
        requested_at=timezone.now() - datetime.timedelta(days=3)
    )
    approved = requests.request_title(title, by=UserFactory())
    requests.approve(approved, by=anna)
    Loan.objects.filter(pk=approved.pk).update(
        decided_at=timezone.now()
        - datetime.timedelta(days=SchoolSettings.current().request_pickup_days)
    )
    mail.outbox.clear()
    counts = requests.daily_request_tasks(today)
    assert counts == {"anfrage_erinnert": 1, "verfallen": 1}
    assert Loan.objects.get(pk=approved.pk).status == Loan.Status.EXPIRED
    subjects = [m.subject for m in mail.outbox]
    assert any("Noch offen" in s for s in subjects) and any("Verfallen" in s for s in subjects)
    assert requests.daily_request_tasks(today) == {"anfrage_erinnert": 0, "verfallen": 0}


def test_full_flow_in_the_browser(client, setup):
    teacher, anna, _ben, title, copy = setup
    client.force_login(teacher)
    page = client.get(reverse("copy_detail", args=[copy.pk])).content.decode()
    assert "Anfragen</button>" in page
    client.post(reverse("request_create", args=[title.pk]), {"message": "3b"})
    loan = Loan.objects.get(title=title, borrower=teacher)
    home = client.get(reverse("home")).content.decode()
    assert "Meine Anfragen" in home and "Zurückziehen" in home

    client.force_login(anna)
    home = client.get(reverse("home")).content.decode()
    assert "Anfragen an mein Team" in home and "Tina Lehrer" in home
    client.post(reverse("request_approve", args=[loan.pk]))
    page = client.get(reverse("copy_detail", args=[copy.pk])).content.decode()
    assert "An Tina übergeben" in page
    client.post(reverse("request_hand_over", args=[loan.pk, copy.pk]))
    loan.refresh_from_db()
    assert loan.status == Loan.Status.LENT

    client.force_login(teacher)
    home = client.get(reverse("home")).content.decode()
    assert "ELFE II" in home and "Meine Anfragen" not in home


def test_title_page_request_box(client, setup):
    teacher, anna, _ben, title, _copy = setup
    client.force_login(teacher)
    page = client.get(reverse("title_detail", args=[title.pk])).content.decode()
    assert (
        "Freigabepflichtig." in page and "Diagnostik-Team" in page and "Anfragen</button>" in page
    )
    client.force_login(anna)
    page = client.get(reverse("title_detail", args=[title.pk])).content.decode()
    assert "Anfragen</button>" not in page
