import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from fundus.accounts.models import Role
from fundus.accounts.personal_data import delete_account
from fundus.core.forms import SchoolSettingsForm
from fundus.core.models import DEFAULT_LESSON_TIMES, SchoolSettings, parse_lesson_times
from fundus.loans import reservations, services
from fundus.loans.models import Loan
from fundus.loans.services import LoanError
from tests.factories import CategoryFactory, CopyFactory, TitleFactory, UserFactory
from tests.test_settings_numbering import settings_data

pytestmark = pytest.mark.django_db


def day(offset):
    return timezone.localdate() + datetime.timedelta(days=offset)


def days(first, last):
    return reservations.days_period(day(first), day(last))


@pytest.fixture
def teacher():
    return UserFactory(role=Role.TEACHER)


@pytest.fixture
def other():
    return UserFactory(role=Role.TEACHER)


def title_with(copies=1, days=14, **kwargs):
    title = TitleFactory(category=CategoryFactory(default_loan_days=days), **kwargs)
    for _i in range(copies):
        CopyFactory(title=title)
    return title


LESSONS = parse_lesson_times(DEFAULT_LESSON_TIMES)


def lessons(offset, first, last):
    start, end, label = reservations.lessons_period(day(offset), first, last, LESSONS)
    return {"start": start, "end": end, "period_label": label}


# Stundenraster


def test_lesson_times_are_parsed_and_validated():
    assert LESSONS[0] == (1, datetime.time(8, 0), datetime.time(8, 45))
    assert len(LESSONS) == 8
    assert parse_lesson_times("7.55 – 8.40\n\n8:40-9:25")[1][0] == 2
    for bad in ["8 bis 9", "09:00-08:00", "08:00-08:45\n08:30-09:15", "25:00-26:00"]:
        with pytest.raises(ValueError):
            parse_lesson_times(bad)


def test_lesson_times_in_settings_form():
    form = SchoolSettingsForm(
        settings_data(lesson_times="7.55-8.40\n8:40 - 9:25"), instance=SchoolSettings.current()
    )
    assert form.is_valid(), form.errors
    form.save()
    assert SchoolSettings.current().lesson_times == "07:55-08:40\n08:40-09:25"
    form = SchoolSettingsForm(
        settings_data(lesson_times="morgens"), instance=SchoolSettings.current()
    )
    assert not form.is_valid()
    assert "Format" in str(form.errors["lesson_times"])


def test_periods_and_their_description():
    start, end = reservations.days_period(datetime.date(2026, 11, 12), datetime.date(2026, 11, 14))
    assert timezone.localtime(start).hour == 0
    assert reservations.last_day(end) == datetime.date(2026, 11, 14)
    assert reservations.describe_period(start, end) == "12.11.–14.11.2026"
    start, end = reservations.days_period(datetime.date(2026, 12, 30), datetime.date(2027, 1, 2))
    assert reservations.describe_period(start, end) == "30.12.2026–02.01.2027"
    start, end, label = reservations.lessons_period(datetime.date(2026, 11, 12), 3, 4, LESSONS)
    assert label == "3.–4. Stunde"
    assert f"{timezone.localtime(start):%H:%M}-{timezone.localtime(end):%H:%M}" == "09:45-11:15"
    assert reservations.describe_period(start, end, label) == "12.11.2026, 3.–4. Stunde"
    assert reservations.lessons_period(datetime.date(2026, 11, 12), 2, 2, LESSONS)[2] == (
        "2. Stunde"
    )
    with pytest.raises(LoanError):
        reservations.lessons_period(datetime.date(2026, 11, 12), 4, 3, LESSONS)
    with pytest.raises(LoanError):
        reservations.lessons_period(datetime.date(2026, 11, 12), 1, 12, LESSONS)


# Reservieren


def test_reserve_and_conflict(teacher, other):
    title = title_with(copies=1)
    [loan] = reservations.reserve(title, teacher, *days(2, 4))
    assert loan.status == Loan.Status.RESERVED and loan.copy is None
    assert loan.borrower == teacher and loan.group is None

    with pytest.raises(LoanError, match="kein Exemplar frei.*Frühestens wieder ab"):
        reservations.reserve(title, other, *days(3, 5))
    # direkt danach geht es
    reservations.reserve(title, other, *days(5, 6))


def test_reserve_several_copies(teacher, other):
    title = title_with(copies=3)
    created = reservations.reserve(title, teacher, *days(1, 1), quantity=2)
    assert len(created) == 2 and created[0].group == created[1].group is not None
    with pytest.raises(LoanError, match="nur 1 Exemplar"):
        reservations.reserve(title, other, *days(1, 1), quantity=2)
    with pytest.raises(LoanError, match="nur 3 Exemplar"):
        reservations.reserve(title, other, *days(5, 5), quantity=4)
    [mine] = reservations.my_reservations(teacher)
    assert mine.quantity == 2


def test_lessons_on_the_same_day_share_a_copy(teacher, other):
    title = title_with(copies=1)
    reservations.reserve(title, teacher, **lessons(1, 1, 2))
    reservations.reserve(title, other, **lessons(1, 3, 4))
    with pytest.raises(LoanError):
        reservations.reserve(title, other, **lessons(1, 2, 3))
    with pytest.raises(LoanError, match="kein Exemplar frei"):
        reservations.reserve(title, other, *days(1, 1))


def test_running_loans_block_until_their_due_date(teacher, other):
    title = title_with(copies=1)
    services.lend(title.copies.first(), by=teacher, due_date=day(3))
    with pytest.raises(LoanError):
        reservations.reserve(title, other, *days(3, 3))
    reservations.reserve(title, other, *days(4, 4))


def test_reserve_rules(teacher):
    with pytest.raises(LoanError, match="anfragen"):
        reservations.reserve(title_with(approval_required=True), teacher, *days(1, 1))
    with pytest.raises(LoanError, match="nicht zum Ausleihen"):
        reservations.reserve(title_with(lendable=False), teacher, *days(1, 1))
    with pytest.raises(LoanError, match="Vergangenheit"):
        reservations.reserve(title_with(), teacher, *days(-3, -2))


def test_cancel(teacher, other):
    title = title_with(copies=2)
    created = reservations.reserve(title, teacher, *days(1, 1), quantity=2)
    with pytest.raises(LoanError, match="Nur die Person"):
        reservations.cancel(created[0], other)
    assert reservations.cancel(created[0], teacher) == 2
    assert set(Loan.objects.values_list("status", flat=True)) == {"withdrawn"}
    with pytest.raises(LoanError, match="nicht mehr offen"):
        reservations.cancel(created[1], teacher)


# Abholen und Konflikte beim Ausleihen


def test_lending_picks_up_own_reservation(teacher):
    title = title_with(copies=1)
    [reservation] = reservations.reserve(title, teacher, *days(0, 2))
    loan = services.lend(title.copies.first(), by=teacher)
    assert loan.pk == reservation.pk
    assert loan.status == Loan.Status.LENT
    assert loan.due_date == day(2)
    assert Loan.objects.count() == 1


def test_lessons_pickup_is_due_the_same_day(teacher, other):
    title = title_with(copies=1)
    now = timezone.now()
    reservation = Loan.objects.create(
        title=title,
        borrower=teacher,
        status=Loan.Status.RESERVED,
        reserved_from=now - datetime.timedelta(minutes=10),
        reserved_until=now + datetime.timedelta(minutes=30),
        period_label="3. Stunde",
    )
    # danach hat jemand anderes reserviert
    later = Loan.objects.create(
        title=title,
        borrower=other,
        status=Loan.Status.RESERVED,
        reserved_from=now + datetime.timedelta(minutes=40),
        reserved_until=now + datetime.timedelta(minutes=90),
        period_label="5. Stunde",
    )
    loan = services.lend(title.copies.first(), by=teacher)
    assert loan.pk == reservation.pk
    assert loan.due_date == reservations.last_day(reservation.reserved_until)
    later.refresh_from_db()
    assert later.status == Loan.Status.RESERVED


def test_lending_respects_other_reservations(teacher, other):
    title = title_with(copies=1, days=14)
    reservations.reserve(title, other, *days(5, 6))
    copy = title.copies.first()
    with pytest.raises(LoanError, match="Rückgabe bitte bis spätestens"):
        services.lend(copy, by=teacher)
    loan = services.lend(copy, by=teacher, due_date=day(4))
    assert loan.due_date == day(4)


def test_lending_blocked_when_reserved_today(teacher, other):
    title = title_with(copies=1)
    reservations.reserve(title, other, *days(0, 1))
    with pytest.raises(LoanError, match="kein Exemplar frei"):
        services.lend(title.copies.first(), by=teacher, due_date=day(0))


def test_extend_is_capped_by_reservations(teacher, other):
    title = title_with(copies=1, days=14)
    loan = services.lend(title.copies.first(), by=teacher, due_date=day(3))
    reservations.reserve(title, other, *days(10, 11))
    loan = services.extend(loan, by=teacher)
    assert loan.due_date == day(9)
    with pytest.raises(LoanError, match="Verlängern ist deshalb nicht möglich"):
        services.extend(loan, by=teacher)


def test_anonymous_mode_reserves_for_a_class(teacher, other):
    config = SchoolSettings.current()
    config.anonymous_lending = True
    config.save()
    title = title_with(copies=1)
    with pytest.raises(LoanError, match="Klasse oder Raum"):
        reservations.reserve(title, teacher, *days(0, 0))
    [reservation] = reservations.reserve(title, teacher, *days(0, 0), label=" 3b ")
    assert reservation.borrower is None and reservation.borrower_label == "3b"
    assert reservations.can_cancel(other, reservation)
    loan = services.lend(title.copies.first(), by=other, label="3B")
    assert loan.pk == reservation.pk and loan.borrower is None


def test_deleting_an_account_withdraws_reservations(teacher):
    admin = UserFactory(role=Role.ADMIN)
    UserFactory(role=Role.ADMIN)
    [reservation] = reservations.reserve(title_with(), teacher, *days(1, 1))
    delete_account(teacher, admin)
    reservation.refresh_from_db()
    assert reservation.status == Loan.Status.WITHDRAWN
    assert reservation.borrower is None


# Oberfläche


def test_reserve_page_days_and_lessons(client, teacher):
    client.force_login(teacher)
    title = title_with(copies=2, title="Tablet-Koffer")
    url = reverse("reserve", args=[title.pk])
    assert "Einzelne Stunden" in client.get(url).content.decode()

    response = client.post(
        url,
        {"art": "tage", "tage-first": day(1), "tage-last": day(2), "tage-quantity": 2},
        follow=True,
    )
    assert "2 Exemplare" in response.content.decode()
    response = client.post(
        url,
        {"art": "stunden", "stunden-day": day(3), "stunden-first": 3, "stunden-last": 4},
        follow=True,
    )
    assert "3.–4. Stunde" in response.content.decode()
    assert Loan.objects.filter(status="reserved").count() == 3

    response = client.post(
        url, {"art": "tage", "tage-first": day(1), "tage-last": day(1), "tage-quantity": 1}
    )
    assert "kein Exemplar frei" in response.content.decode()

    home = client.get(reverse("home")).content.decode()
    assert "Meine Reservierungen" in home and "Tablet-Koffer" in home


def test_reserve_page_hides_names_from_other_teachers(client, teacher, other):
    title = title_with(copies=1)
    reservations.reserve(title, other, *days(1, 1))
    client.force_login(teacher)
    content = client.get(reverse("reserve", args=[title.pk])).content.decode()
    assert other.last_name not in content
    assert "Stornieren" not in content


def test_cancel_view(client, teacher):
    [reservation] = reservations.reserve(title_with(), teacher, *days(1, 1))
    client.force_login(teacher)
    response = client.post(reverse("reservation_cancel", args=[reservation.pk]), follow=True)
    assert "storniert" in response.content.decode()
    reservation.refresh_from_db()
    assert reservation.status == Loan.Status.WITHDRAWN


def test_copy_page_announces_pickup_and_limits(client, teacher, other):
    title = title_with(copies=1, days=14)
    client.force_login(teacher)
    reservations.reserve(title, other, *days(5, 5))
    content = client.get(reverse("copy_detail", args=[title.copies.first().pk])).content.decode()
    assert "Rückgabedatum ist deshalb begrenzt" in content
    assert day(4).isoformat() in content

    reservations.reserve(title, teacher, *days(0, 1))
    content = client.get(reverse("copy_detail", args=[title.copies.first().pk])).content.decode()
    assert "wird mit dem Ausleihen abgeholt" in content


@pytest.mark.django_db(transaction=True)
def test_reserve_and_pickup_run_in_their_own_transaction():
    """Ohne umgebende Test-Transaktion: select_for_update braucht auf
    PostgreSQL eine eigene Transaktion."""
    teacher = UserFactory(role=Role.TEACHER)
    title = title_with(copies=1)
    [reservation] = reservations.reserve(title, teacher, *days(0, 0))
    loan = services.lend(title.copies.first(), by=teacher)
    assert loan.pk == reservation.pk


# Kalender und täglicher Lauf


def test_week_grid_counts_free_copies(teacher, other):
    title = title_with(copies=2)
    monday = reservations.week_start(day(7))
    wednesday = monday + datetime.timedelta(days=2)
    start, end, label = reservations.lessons_period(wednesday, 3, 4, LESSONS)
    reservations.reserve(title, teacher, start, end, period_label=label)
    reservations.reserve(title, other, *reservations.days_period(wednesday, wednesday))
    grid = reservations.week_grid(title, monday, LESSONS)
    assert [d["day"].weekday() for d in grid["days"]] == [0, 1, 2, 3, 4]
    wed = grid["days"][2]
    assert wed["whole"] == 0
    assert [c["free"] for c in wed["cells"]][:5] == [1, 1, 0, 0, 1]
    assert grid["days"][0]["whole"] == 2
    assert grid["rows"][2]["cells"][2]["free"] == 0


def test_weekend_appears_only_when_busy(teacher):
    title = title_with(copies=1)
    monday = reservations.week_start(day(7))
    saturday = monday + datetime.timedelta(days=5)
    reservations.reserve(title, teacher, *reservations.days_period(saturday, saturday))
    days_shown = [d["day"] for d in reservations.week_grid(title, monday, LESSONS)["days"]]
    assert saturday in days_shown
    assert monday + datetime.timedelta(days=6) not in days_shown


def test_calendar_on_reserve_page_prefills_lessons(client, teacher):
    client.force_login(teacher)
    title = title_with(copies=1)
    target = day(8)
    response = client.get(
        reverse("reserve", args=[title.pk]),
        {"woche": target.isoformat(), "tag": target.isoformat(), "stunde": 5},
    )
    content = response.content.decode()
    assert "Belegung" in content and "ganzer Tag" in content
    form = response.context["lessons_form"]
    assert form.initial["day"] == target and form.initial["first"] == 5
    assert response.context["monday"] == reservations.week_start(target)


def test_daily_reminders_and_expiry(teacher, mailoutbox):
    title = title_with(copies=3)
    tomorrow = reservations.reserve(title, teacher, *days(1, 1), quantity=2)
    started = reservations.reserve(title, teacher, *days(-1, 1))[0]
    Loan.objects.filter(pk=started.pk).update(reserved_from=reservations.day_start(day(-1)))
    ended = Loan.objects.create(
        title=title,
        borrower=teacher,
        status=Loan.Status.RESERVED,
        reserved_from=reservations.day_start(day(-3)),
        reserved_until=reservations.day_end(day(-1)),
    )
    counts = reservations.daily_tasks()
    assert counts == {
        "reservierung_erinnert": 1,
        "reservierung_nicht_abgeholt": 1,
        "reservierung_verfallen": 1,
    }
    subjects = sorted(m.subject for m in mailoutbox)
    assert (
        subjects[0].startswith("Morgen reserviert")
        and "2 Exemplare" in mailoutbox[[m.subject for m in mailoutbox].index(subjects[0])].body
    )
    assert subjects[1].startswith("Noch nicht abgeholt")
    ended.refresh_from_db()
    assert ended.status == Loan.Status.EXPIRED
    assert Loan.objects.filter(pk=tomorrow[1].pk, start_reminded_at__isnull=False).exists()
    # nur einmal
    assert reservations.daily_tasks()["reservierung_erinnert"] == 0
    assert len(mailoutbox) == 2


def test_reminders_can_be_switched_off(teacher, mailoutbox):
    config = SchoolSettings.current()
    config.reservation_reminders = False
    config.save()
    reservations.reserve(title_with(), teacher, *days(1, 1))
    assert reservations.daily_tasks()["reservierung_erinnert"] == 0
    assert mailoutbox == []
