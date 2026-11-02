import datetime

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from fundus.accounts.models import Role
from fundus.core.models import SchoolSettings
from fundus.loans import requests, reservations, services
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


def test_hand_over_without_prior_approval_uses_end_of_period(setup):
    teacher, anna, _ben, title, copy = setup
    today = timezone.localdate()
    wish = today + datetime.timedelta(days=5)
    start, end = reservations.days_period(today, wish)
    loan = requests.request_title(title, by=teacher, start=start, end=end)
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
    assert "anfragen</button>" in page
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
        "Freigabepflichtig." in page and "Diagnostik-Team" in page and "anfragen</button>" in page
    )
    client.force_login(anna)
    page = client.get(reverse("title_detail", args=[title.pk])).content.decode()
    assert "anfragen</button>" not in page


# Anfragen mit Zeitraum (Reservierung freigabepflichtiger Titel)


def period(first, last):
    today = timezone.localdate()
    return reservations.days_period(
        today + datetime.timedelta(days=first), today + datetime.timedelta(days=last)
    )


def test_period_request_blocks_the_period_while_open(setup):
    teacher, anna, _ben, title, _copy = setup
    start, end = period(3, 4)
    loan = requests.request_title(title, by=teacher, start=start, end=end, message="3b")
    assert loan.status == Loan.Status.REQUESTED and loan.reserved_from == start
    assert "Dieser Zeitraum ist bis zu Ihrer Entscheidung vorgemerkt" in mail.outbox[0].body
    with pytest.raises(LoanError, match="kein Exemplar frei"):
        requests.request_title(title, by=UserFactory(), start=start, end=end)
    # weitere Zeiträume und eine Anfrage „so bald wie möglich“ gehen trotzdem
    requests.request_title(title, by=teacher, start=period(6, 6)[0], end=period(6, 6)[1])
    requests.request_title(title, by=teacher)
    assert requests.period_requests(title, teacher).count() == 2


def test_period_request_does_not_block_extending_before_it(setup):
    teacher, anna, _ben, title, copy = setup
    loan = requests.hand_over(requests.request_title(title, by=teacher), copy, by=anna)
    requests.request_title(title, by=UserFactory(), start=period(40, 41)[0], end=period(40, 41)[1])
    loan = services.extend(loan, by=teacher)
    assert loan.due_date == timezone.localdate() + datetime.timedelta(days=28)


def test_approve_with_other_period_and_after_period_is_over(setup):
    teacher, anna, _ben, title, _copy = setup
    start, end = period(2, 2)
    loan = requests.request_title(title, by=teacher, start=start, end=end)
    Loan.objects.filter(pk=loan.pk).update(
        reserved_from=period(-3, -2)[0], reserved_until=period(-3, -2)[1]
    )
    with pytest.raises(LoanError, match="Zeitraum ist vorbei"):
        requests.approve(loan, by=anna)
    loan = requests.approve(loan, by=anna, new_period=period(5, 7))
    assert loan.status == Loan.Status.APPROVED
    assert reservations.last_day(loan.reserved_until) == (
        timezone.localdate() + datetime.timedelta(days=7)
    )
    assert "anderen Zeitraum vorgeschlagen" in mail.outbox[-1].body


def test_open_period_requests_never_expire_but_team_is_reminded(setup):
    teacher, anna, ben, title, _copy = setup
    old = requests.request_title(title, by=teacher, start=period(1, 1)[0], end=period(1, 1)[1])
    Loan.objects.filter(pk=old.pk).update(
        reserved_from=period(-5, -4)[0], reserved_until=period(-5, -4)[1]
    )
    tomorrow = requests.request_title(
        title, by=UserFactory(), start=period(1, 1)[0], end=period(1, 1)[1]
    )
    mail.outbox.clear()
    counts = requests.daily_request_tasks()
    assert counts["verfallen"] == 0
    old.refresh_from_db()
    assert old.status == Loan.Status.REQUESTED
    subjects = [m.subject for m in mail.outbox]
    assert any(s.startswith("Morgen gewünscht, noch offen") for s in subjects)
    tomorrow.refresh_from_db()
    assert tomorrow.start_reminded_at is not None


def test_approved_period_request_expires_at_the_end(setup):
    teacher, anna, ben, title, _copy = setup
    loan = requests.request_title(title, by=teacher, start=period(1, 1)[0], end=period(1, 1)[1])
    requests.approve(loan, by=anna)
    assert requests.daily_request_tasks()["verfallen"] == 0
    Loan.objects.filter(pk=loan.pk).update(
        reserved_from=period(-2, -1)[0], reserved_until=period(-2, -1)[1]
    )
    mail.outbox.clear()
    assert requests.daily_request_tasks()["verfallen"] == 1
    loan.refresh_from_db()
    assert loan.status == Loan.Status.EXPIRED
    assert set(mail.outbox[0].to) == {teacher.email, anna.email, ben.email}
    assert "im Zeitraum nicht abgeholt" in mail.outbox[0].body


def test_period_request_in_the_browser(client, setup):
    teacher, anna, _ben, title, copy = setup
    client.force_login(teacher)
    page = client.get(reverse("title_detail", args=[title.pk])).content.decode()
    assert "Für einen bestimmten Zeitraum anfragen" in page
    url = reverse("reserve", args=[title.pk])
    assert "Für einen Zeitraum anfragen" in client.get(url).content.decode()
    day = (timezone.localdate() + datetime.timedelta(days=2)).isoformat()
    response = client.post(
        url,
        {
            "art": "stunden",
            "stunden-day": day,
            "stunden-first": 1,
            "stunden-last": 2,
            "stunden-message": "für die 4a",
        },
        follow=True,
    )
    content = response.content.decode()
    assert "Angefragt für" in content and "1.–2. Stunde" in content
    assert "Zurückziehen" in content
    loan = Loan.objects.get(title=title)
    assert loan.status == Loan.Status.REQUESTED and loan.message == "für die 4a"

    client.force_login(anna)
    home = client.get(reverse("home")).content.decode()
    assert "1.–2. Stunde" in home and "Anderer Zeitraum" in home
    first = (timezone.localdate() + datetime.timedelta(days=9)).isoformat()
    client.post(reverse("request_approve", args=[loan.pk]), {"neu_von": first})
    loan.refresh_from_db()
    assert loan.status == Loan.Status.APPROVED and loan.period_label == ""
    assert reservations.last_day(loan.reserved_until).isoformat() == first
