import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from fundus.accounts.models import Role
from fundus.catalog.models import SupportFocus
from fundus.core.privacy import anonymize_loans
from fundus.loans import stats
from fundus.loans.models import Loan
from tests.factories import CategoryFactory, CopyFactory, LoanFactory, TitleFactory, UserFactory

pytestmark = pytest.mark.django_db


def at(day):
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time(10)))


def lent(title, day, days=None):
    loan = LoanFactory(copy=CopyFactory(title=title), lent_at=at(day))
    if days is not None:
        loan.status = Loan.Status.RETURNED
        loan.returned_at = at(day + datetime.timedelta(days=days))
        loan.save()
    return loan


def test_presets_follow_school_year():
    options = stats.presets(datetime.date(2026, 11, 2))
    assert options["schuljahr"].start == datetime.date(2026, 8, 1)
    assert options["schuljahr"].end == datetime.date(2027, 7, 31)
    assert options["schuljahr"].label == "Schuljahr 2026/27"
    assert options["halbjahr2"].start == datetime.date(2027, 2, 1)
    assert options["vorjahr"].start == datetime.date(2025, 8, 1)
    assert stats.presets(datetime.date(2027, 3, 1))["schuljahr"].start.year == 2026


def test_free_period_and_fallback():
    key, period = stats.period_from({"zeitraum": "frei", "von": "2026-12-31", "bis": "2026-09-01"})
    assert key == "frei" and period.start < period.end
    key, _ = stats.period_from({"zeitraum": "frei", "von": "kaputt"})
    assert key == "schuljahr"
    assert stats.period_from({"zeitraum": "gibtsnicht"})[0] == "schuljahr"


def test_counts_titles_categories_focuses_and_durations():
    books = CategoryFactory(name="Atlanten")
    focus = SupportFocus.objects.create(name="Lesen im Test")
    test = TitleFactory(title="Lesetest", category=CategoryFactory(name="Lesetests"))
    test.support_focuses.add(focus)
    book = TitleFactory(title="Atlas", category=books)
    unused = TitleFactory(title="Nie gebraucht", category=books)
    TitleFactory(title="Nur Katalog", lendable=False)

    lent(test, datetime.date(2026, 9, 1), days=4)
    lent(test, datetime.date(2026, 10, 1), days=2)
    lent(test, datetime.date(2026, 10, 20))  # noch ausgeliehen
    lent(book, datetime.date(2026, 9, 10), days=10)
    lent(book, datetime.date(2025, 9, 10), days=1)  # anderes Schuljahr

    data = stats.compute(stats.Period(datetime.date(2026, 8, 1), datetime.date(2027, 7, 31), "x"))
    assert data["total"] == 4
    assert data["title_count"] == 2
    assert [(r["title"].title, r["count"]) for r in data["rows"]] == [("Lesetest", 3), ("Atlas", 1)]
    assert data["rows"][0]["avg_days"] == pytest.approx(3)
    assert data["rows"][0]["last_lent"] == datetime.date(2026, 10, 20)
    assert data["avg_days"] == pytest.approx(16 / 3)
    assert data["per_category"] == [("Lesetests", 3), ("Atlanten", 1)]
    assert data["per_focus"] == [("Lesen im Test", 3)]
    assert [t.title for t in data["never"]] == ["Nie gebraucht"]
    assert unused in data["never"]


def test_anonymized_loans_still_count():
    title = TitleFactory()
    loan = lent(title, datetime.date(2026, 9, 1), days=3)
    anonymize_loans([loan.pk])
    loan.refresh_from_db()
    assert loan.borrower is None
    data = stats.compute(stats.Period(datetime.date(2026, 8, 1), datetime.date(2027, 7, 31), "x"))
    assert data["total"] == 1


def test_request_outcomes():
    title = TitleFactory(approval_required=True)
    now = at(datetime.date(2026, 9, 1))
    for status in ["requested", "rejected", "rejected", "withdrawn", "expired"]:
        Loan.objects.create(title=title, borrower=UserFactory(), status=status, requested_at=now)
    LoanFactory(copy=CopyFactory(title=title), requested_at=now, lent_at=now)
    data = stats.compute(stats.Period(datetime.date(2026, 8, 1), datetime.date(2027, 7, 31), "x"))
    assert data["requests"] == {
        "total": 6,
        "handed_over": 1,
        "open": 1,
        "rejected": 2,
        "withdrawn": 1,
        "expired": 1,
    }


def test_page_only_for_management(client):
    client.force_login(UserFactory(role=Role.TEACHER))
    assert client.get(reverse("statistics")).status_code == 403
    client.force_login(UserFactory(role=Role.MANAGER))
    lent(TitleFactory(title="Hörspiel"), timezone.localdate())
    response = client.get(reverse("statistics"))
    content = response.content.decode()
    assert "Hörspiel" in content
    assert "Statistik" in content
    # keine Namen auf der Seite
    assert "Erika" not in content


def test_excel_download(client):
    from openpyxl import load_workbook

    client.force_login(UserFactory(role=Role.ADMIN))
    lent(TitleFactory(title="Hörspiel"), timezone.localdate(), days=0)
    response = client.get(reverse("statistics"), {"zeitraum": "schuljahr", "format": "xlsx"})
    assert response["Content-Disposition"].startswith('attachment; filename="fundus-statistik-')
    book = load_workbook(__import__("io").BytesIO(b"".join(response.streaming_content)))
    assert book.sheetnames == [
        "Übersicht",
        "Titel",
        "Kategorien",
        "Förderschwerpunkte",
        "Nicht ausgeliehen",
    ]
    assert book["Titel"]["A2"].value == "Hörspiel"
    assert book["Übersicht"]["B5"].value == 1
