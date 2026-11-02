import datetime

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from fundus.accounts.models import Role
from fundus.catalog.models import Title
from fundus.core import privacy
from fundus.core.models import SchoolSettings
from fundus.loans import requests, services
from fundus.loans.models import Loan
from fundus.supplies.models import Consumable, ReorderNotice
from tests.factories import CopyFactory, TitleFactory, UserFactory, team_of

pytestmark = pytest.mark.django_db

DAY = datetime.timedelta(days=1)


def returned_loan(days_ago, borrower=None):
    copy = CopyFactory()
    borrower = borrower or UserFactory()
    loan = services.lend(copy, by=borrower)
    services.return_copy(copy, by=borrower)
    returned = timezone.now() - days_ago * DAY
    Loan.objects.filter(pk=loan.pk).update(returned_at=returned)
    return Loan.objects.get(pk=loan.pk)


def test_returned_loans_are_anonymized_after_period_with_history():
    old = returned_loan(400)
    recent = returned_loan(30)
    counts = privacy.run()
    assert counts["ausleihen_anonymisiert"] == 1

    old.refresh_from_db()
    assert old.borrower is None and old.anonymized_at is not None
    assert old.lent_at and old.returned_at and old.copy_id  # Statistik bleibt
    assert str(old.borrower_display) == "anonymisiert"
    for row in old.history.all():
        assert row.borrower_id is None and row.history_user_id is None

    recent.refresh_from_db()
    assert recent.borrower is not None and recent.anonymized_at is None
    assert recent.history.filter(borrower__isnull=False).exists()


def test_open_loans_and_requests_are_never_anonymized():
    copy = CopyFactory()
    teacher = UserFactory()
    loan = services.lend(copy, by=teacher)
    Loan.objects.filter(pk=loan.pk).update(lent_at=timezone.now() - 900 * DAY)
    title = TitleFactory(approval_required=True, team=team_of(UserFactory()))
    request = requests.request_title(title, teacher)
    Loan.objects.filter(pk=request.pk).update(updated_at=timezone.now() - 900 * DAY)
    privacy.run()
    assert not Loan.objects.filter(anonymized_at__isnull=False).exists()


def test_rejected_request_is_anonymized_including_message():
    teacher, member = UserFactory(), UserFactory()
    title = TitleFactory(approval_required=True, team=team_of(member))
    loan = requests.request_title(title, teacher, message="Für die 3b")
    loan = requests.reject(loan, member, reason="Gerade in Benutzung")
    Loan.objects.filter(pk=loan.pk).update(updated_at=timezone.now() - 400 * DAY)
    privacy.run()
    loan.refresh_from_db()
    assert (loan.borrower, loan.approved_by, loan.message, loan.rejection_reason) == (
        None,
        None,
        "",
        "",
    )
    assert not loan.history.exclude(message="").exists()


def test_period_is_configurable():
    config = SchoolSettings.current()
    config.anonymize_after_days = 10
    config.save()
    returned_loan(11)
    assert privacy.loans_due().count() == 1


def test_history_user_removed_after_period_but_change_kept():
    editor = UserFactory(role=Role.MANAGER)
    title = TitleFactory()
    title.title = "Neuer Titel"
    title._history_user = editor
    title.save()
    Title.history.model.objects.update(history_date=timezone.now() - 400 * DAY)
    title.title = "Ganz neuer Titel"
    title._history_user = editor
    title.save()

    privacy.run()
    rows = Title.history.filter(id=title.pk).order_by("history_date")
    assert [r.history_user_id for r in rows][-1] == editor.pk
    assert all(r.history_user_id is None for r in rows[: len(rows) - 1])
    assert rows.filter(title="Neuer Titel").exists()


def test_reorder_names_and_past_absences_are_cleared():
    user = UserFactory(absent_until=timezone.localdate() - DAY)
    item = Consumable.objects.create(name="Bögen", code="NB-0001")
    notice = ReorderNotice.objects.create(
        consumable=item, created_by=user, handled_by=user, status=ReorderNotice.Status.DELIVERED
    )
    ReorderNotice.objects.filter(pk=notice.pk).update(created_at=timezone.now() - 400 * DAY)
    privacy.run()
    notice.refresh_from_db()
    user.refresh_from_db()
    assert notice.created_by is None and notice.handled_by is None
    assert user.absent_until is None


def test_daily_command_runs_privacy(capsys):
    returned_loan(400)
    call_command("daily_tasks")
    assert "Ausleihen anonymisiert: 1" in capsys.readouterr().out
    assert SchoolSettings.current().last_privacy_run is not None


def test_settings_show_preview_and_run_now(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    returned_loan(400)
    page = client.get(reverse("school_settings")).content.decode()
    assert "Beim nächsten täglichen Lauf werden 1 Ausleihen anonymisiert" in page
    response = client.post(reverse("privacy_run_now"), follow=True)
    assert "Ausleihen anonymisiert: 1" in response.content.decode()
    assert Loan.objects.filter(anonymized_at__isnull=False).count() == 1


def test_teacher_cannot_run_privacy(client):
    client.force_login(UserFactory())
    assert client.post(reverse("privacy_run_now")).status_code == 403
