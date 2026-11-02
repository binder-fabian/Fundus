import datetime

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from fundus.accounts.models import Role
from fundus.core.models import SchoolSettings
from fundus.loans import services
from fundus.loans.management.commands.run_scheduler import Command as Scheduler
from fundus.loans.reminders import send_reminders
from tests.factories import LoanFactory, UserFactory

pytestmark = pytest.mark.django_db

TODAY = datetime.date(2026, 11, 10)


def loan_due(days_from_today, **kwargs):
    return LoanFactory(due_date=TODAY + datetime.timedelta(days=days_from_today), **kwargs)


def test_reminder_day_before_once(settings):
    settings.SITE_URL = "https://fundus.schule.de"
    loan = loan_due(1)
    loan_due(5)
    counts = send_reminders(TODAY)
    assert counts["vorher"] == 1
    assert mail.outbox[0].to == [loan.borrower.email]
    assert "Mittwoch, 11.11.2026" in mail.outbox[0].body  # Wochentag auf Deutsch
    assert "https://fundus.schule.de/exemplar/" in mail.outbox[0].body
    send_reminders(TODAY)
    assert len(mail.outbox) == 1


def test_overdue_notice_after_configured_days():
    loan_due(-2)
    late = loan_due(-3)
    counts = send_reminders(TODAY)
    assert counts["ueberfaellig"] == 1
    assert mail.outbox[0].to == [late.borrower.email]
    assert "3 Tage her" in mail.outbox[0].body


def test_escalation_to_all_managers_in_one_mail():
    admin = UserFactory(role=Role.ADMIN)
    manager = UserFactory(role=Role.MANAGER)
    UserFactory(role=Role.TEACHER)
    UserFactory(role=Role.MANAGER, is_active=False)
    a = loan_due(-14)
    b = loan_due(-30)
    loan_due(-13)
    counts = send_reminders(TODAY)
    assert counts["verwaltung"] == 2
    escalation = [m for m in mail.outbox if "lange überfällige" in m.subject]
    assert len(escalation) == 1
    assert sorted(escalation[0].to) == sorted([admin.email, manager.email])
    assert (
        a.copy.inventory_number in escalation[0].body
        and b.copy.inventory_number in escalation[0].body
    )
    mail.outbox.clear()
    send_reminders(TODAY)
    assert not [m for m in mail.outbox if "lange überfällige" in m.subject]


def test_returned_and_disabled_send_nothing():
    returned = loan_due(1)
    returned.status, returned.returned_at = "returned", timezone.now()
    returned.save()
    config = SchoolSettings.current()
    config.reminders_enabled = False
    config.save()
    loan_due(1)
    counts = send_reminders(TODAY)
    assert counts["vorher"] == counts["ueberfaellig"] == counts["verwaltung"] == 0
    assert not mail.outbox


def test_extend_resets_reminders():
    loan = loan_due(1)
    send_reminders(TODAY)
    loan = services.extend(loan, by=loan.borrower, today=TODAY)
    assert loan.reminder_sent_at is None


def test_scheduler_runs_once_per_day_after_hour(settings):
    settings.REMINDER_HOUR = 7
    loan_due(1)
    scheduler = Scheduler()
    scheduler.stdout = type("Out", (), {"write": lambda self, text: None})()
    tz = timezone.get_current_timezone()
    early = datetime.datetime(2026, 11, 10, 6, 30, tzinfo=tz)
    later = datetime.datetime(2026, 11, 10, 7, 5, tzinfo=tz)
    assert scheduler.tick(early) is False
    assert scheduler.tick(later) is True
    assert scheduler.tick(later + datetime.timedelta(hours=3)) is False
    assert SchoolSettings.current().last_reminder_run == TODAY


def test_send_reminders_command(capsys):
    call_command("send_reminders")
    assert "Erinnerungen:" in capsys.readouterr().out


def test_scheduler_writes_heartbeat(settings, tmp_path):
    settings.SCHEDULER_HEARTBEAT = str(tmp_path / "beat")
    scheduler = Scheduler()
    scheduler.heartbeat()
    assert (tmp_path / "beat").exists()
