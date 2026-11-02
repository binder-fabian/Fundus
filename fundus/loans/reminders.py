"""E-Mail-Erinnerungen: vor Ablauf, bei Überfälligkeit, danach an die Verwaltung.

Jede Nachricht geht pro Ausleihe höchstens einmal raus (Zeitstempel an der
Ausleihe). Verlängern setzt die Zeitstempel zurück.
"""

import datetime
import logging
import smtplib

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone, translation

from fundus.accounts.models import Role, User
from fundus.core.models import SchoolSettings
from fundus.loans.models import Loan

logger = logging.getLogger(__name__)


def _url(path):
    return settings.SITE_URL.rstrip("/") + path


def _send(template, recipients, context):
    context = {**context, "site_url": settings.SITE_URL}
    subject = render_to_string(f"loans/email/{template}_subject.txt", context).strip()
    body = render_to_string(f"loans/email/{template}_body.txt", context)
    try:
        send_mail(subject, body, None, recipients)
    except (smtplib.SMTPException, OSError):
        logger.exception("E-Mail „%s“ an %s fehlgeschlagen", template, recipients)
        return False
    return True


def _open_loans():
    return (
        Loan.objects.filter(status=Loan.Status.LENT, borrower__isnull=False, due_date__isnull=False)
        .exclude(borrower__email="")
        .select_related("copy__title", "borrower")
    )


def send_reminders(today=None):
    """Verschickt alle fälligen Erinnerungen. Gibt die Anzahl je Art zurück."""
    with translation.override(settings.LANGUAGE_CODE):
        return _send_reminders(today or timezone.localdate())


def _send_reminders(today):
    config = SchoolSettings.current()
    counts = {"vorher": 0, "ueberfaellig": 0, "verwaltung": 0}
    if not config.reminders_enabled:
        return counts
    now = timezone.now()

    upcoming = _open_loans().filter(
        reminder_sent_at__isnull=True,
        due_date__gte=today,
        due_date__lte=today + datetime.timedelta(days=config.reminder_days_before),
    )
    for loan in upcoming:
        context = {"loan": loan, "link": _url(reverse("copy_detail", args=[loan.copy_id]))}
        if _send("reminder", [loan.borrower.email], context):
            loan.reminder_sent_at = now
            loan.save(update_fields=["reminder_sent_at"])
            counts["vorher"] += 1

    overdue = _open_loans().filter(
        overdue_notice_sent_at__isnull=True,
        due_date__lte=today - datetime.timedelta(days=config.overdue_notice_days),
    )
    for loan in overdue:
        context = {
            "loan": loan,
            "days": (today - loan.due_date).days,
            "link": _url(reverse("copy_detail", args=[loan.copy_id])),
        }
        if _send("overdue", [loan.borrower.email], context):
            loan.overdue_notice_sent_at = now
            loan.save(update_fields=["overdue_notice_sent_at"])
            counts["ueberfaellig"] += 1

    escalate = list(
        Loan.objects.filter(
            status=Loan.Status.LENT,
            escalated_at__isnull=True,
            due_date__lte=today - datetime.timedelta(days=config.escalate_days),
        ).select_related("copy__title", "borrower")
    )
    managers = list(
        User.objects.filter(is_active=True, role__in=[Role.ADMIN, Role.MANAGER])
        .exclude(email="")
        .values_list("email", flat=True)
    )
    if escalate and managers:
        context = {
            "loans": escalate,
            "today": today,
            "link": _url(reverse("loan_overview") + "?ansicht=ueberfaellig"),
        }
        if _send("escalation", managers, context):
            Loan.objects.filter(pk__in=[loan.pk for loan in escalate]).update(escalated_at=now)
            counts["verwaltung"] = len(escalate)

    config.last_reminder_run = today
    config.save(update_fields=["last_reminder_run"])
    return counts
