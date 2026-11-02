"""Anfragen für freigabepflichtige Titel: anfragen, genehmigen/ablehnen,
übergeben (Scan durch das Team), zurückziehen, verfallen lassen.

Eine Anfrage gilt dem Titel. Ausgeliehen ist erst, wenn jemand aus dem Team
bei der Übergabe ein freies Exemplar scannt.
"""

import datetime
import logging
import smtplib

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from fundus.accounts.models import Role, User
from fundus.catalog.models import Copy, Title
from fundus.core.models import SchoolSettings
from fundus.loans.models import Loan
from fundus.loans.services import (
    LoanError,
    anonymous_mode,
    can_lend_for_others,
    clean_label,
    default_due_date,
)

logger = logging.getLogger(__name__)


def _url(path):
    return settings.SITE_URL.rstrip("/") + path


def _mail(template, recipients, context):
    recipients = [r for r in recipients if r]
    if not recipients:
        return False
    with translation.override(settings.LANGUAGE_CODE):
        context = {**context, "site_url": settings.SITE_URL}
        subject = render_to_string(f"loans/email/{template}_subject.txt", context).strip()
        body = render_to_string(f"loans/email/{template}_body.txt", context)
    try:
        send_mail(subject, body, None, recipients)
    except (smtplib.SMTPException, OSError):
        logger.exception("E-Mail „%s“ an %s fehlgeschlagen", template, recipients)
        return False
    return True


def deciders(title, today=None):
    """Wer eine Anfrage bekommt: anwesende Teammitglieder, sonst die Verwaltung."""
    if title.team_id:
        people = list(title.team.available_members(today))
        if people:
            return people
    return list(User.objects.filter(is_active=True, role__in=[Role.ADMIN, Role.MANAGER]))


def open_request(title, user):
    """Offene Anfrage „so bald wie möglich“ (ohne Zeitraum) dieser Person."""
    return Loan.objects.filter(
        title=title, borrower=user, status__in=Loan.OPEN_REQUEST, reserved_from__isnull=True
    ).first()


def period_requests(title, user):
    """Offene Anfragen dieser Person für einen bestimmten Zeitraum."""
    return Loan.objects.filter(
        title=title, borrower=user, status__in=Loan.OPEN_REQUEST, reserved_from__isnull=False
    ).order_by("reserved_from")


def _check_decider(loan, by):
    if not can_lend_for_others(by, loan.title):
        raise LoanError(_("Über diese Anfrage entscheidet das zuständige Team."))


@transaction.atomic
def request_title(title, by, message="", start=None, end=None, period_label=""):
    """Anfrage an das Team: ohne Zeitraum „so bald wie möglich“, mit Zeitraum
    als Reservierung, die schon während der Prüfung vorgemerkt ist."""
    from fundus.loans import reservations

    title = Title.objects.select_for_update().get(pk=title.pk)
    if not (title.lendable and title.approval_required):
        raise LoanError(_("Für diesen Titel ist keine Anfrage nötig."))
    if start is None:
        if open_request(title, by):
            raise LoanError(_("Sie haben diesen Titel bereits angefragt."))
    else:
        reservations.check_period(title, start, end)
    loan = Loan.objects.create(
        title=title,
        borrower=by,
        status=Loan.Status.REQUESTED,
        requested_at=timezone.now(),
        reserved_from=start,
        reserved_until=end,
        period_label=period_label if start else "",
        message=message.strip(),
    )
    _mail(
        "request_new",
        [p.email for p in deciders(title)],
        {"loan": loan, "link": _url(reverse("home"))},
    )
    return loan


@transaction.atomic
def approve(loan, by, new_period=None):
    """Genehmigt eine Anfrage. `new_period` = (Beginn, Ende) schlägt einen
    anderen Zeitraum vor (ganze Tage), z. B. wenn der gewünschte vorbei ist."""
    from fundus.loans import reservations

    loan = (
        Loan.objects.select_for_update(of=("self",))
        .select_related("title", "borrower")
        .get(pk=loan.pk)
    )
    _check_decider(loan, by)
    if loan.status != Loan.Status.REQUESTED:
        raise LoanError(_("Diese Anfrage ist schon bearbeitet."))
    loan.period_changed = False
    if new_period:
        Title.objects.select_for_update().filter(pk=loan.title_id).first()
        reservations.check_period(loan.title, *new_period, exclude=[loan.pk])
        loan.reserved_from, loan.reserved_until = new_period
        loan.period_label = ""
        loan.start_reminded_at = None
        loan.period_changed = True
    elif loan.reserved_until and loan.reserved_until <= timezone.now():
        raise LoanError(_("Der gewünschte Zeitraum ist vorbei. Bitte einen neuen angeben."))
    loan.status = Loan.Status.APPROVED
    loan.approved_by = by
    loan.decided_at = timezone.now()
    loan.save()
    _mail(
        "request_approved",
        [loan.borrower.email],
        {
            "loan": loan,
            "days": SchoolSettings.current().request_pickup_days,
            "link": _url(reverse("title_detail", args=[loan.title_id])),
        },
    )
    return loan


@transaction.atomic
def reject(loan, by, reason=""):
    loan = (
        Loan.objects.select_for_update(of=("self",))
        .select_related("title", "borrower")
        .get(pk=loan.pk)
    )
    _check_decider(loan, by)
    if loan.status not in Loan.OPEN_REQUEST:
        raise LoanError(_("Diese Anfrage ist schon bearbeitet."))
    loan.status = Loan.Status.REJECTED
    loan.approved_by = by
    loan.decided_at = timezone.now()
    loan.rejection_reason = reason.strip()
    loan.save()
    _mail("request_rejected", [loan.borrower.email], {"loan": loan})
    return loan


@transaction.atomic
def withdraw(loan, by):
    loan = Loan.objects.select_for_update().get(pk=loan.pk)
    if loan.borrower_id != by.pk:
        raise LoanError(_("Nur die anfragende Person kann zurückziehen."))
    if loan.status not in Loan.OPEN_REQUEST:
        raise LoanError(_("Diese Anfrage ist nicht mehr offen."))
    loan.status = Loan.Status.WITHDRAWN
    loan.save()
    return loan


@transaction.atomic
def hand_over(loan, copy, by, due_date=None, label=""):
    """Übergabe: Das Team scannt ein freies Exemplar und bucht es für die
    anfragende Person aus. Eine noch nicht genehmigte Anfrage gilt damit
    als genehmigt.

    Im Modus ohne Namen trägt das Team Klasse oder Raum ein; alle Angaben zu
    Personen werden dabei aus der Ausleihe und ihrem Protokoll entfernt."""
    loan = (
        Loan.objects.select_for_update(of=("self",))
        .select_related("title__category")
        .get(pk=loan.pk)
    )
    copy = Copy.objects.select_for_update().get(pk=copy.pk)
    _check_decider(loan, by)
    if loan.status not in Loan.OPEN_REQUEST:
        raise LoanError(_("Diese Anfrage ist nicht mehr offen."))
    if copy.title_id != loan.title_id:
        raise LoanError(_("Dieses Exemplar gehört zu einem anderen Titel."))
    if copy.loans.filter(status=Loan.Status.LENT).exists():
        raise LoanError(_("Dieses Exemplar ist bereits ausgeliehen."))
    anonymous = anonymous_mode()
    if anonymous:
        label = clean_label(label)

    today = timezone.localdate()
    from fundus.loans import reservations

    if due_date is None:
        due_date = default_due_date(copy, today)
        if loan.reserved_until and reservations.last_day(loan.reserved_until) >= today:
            due_date = reservations.last_day(loan.reserved_until)

    latest = reservations.latest_due_date(loan.title, exclude=[loan.pk])
    if latest is not None:
        if latest < today:
            raise LoanError(
                reservations.conflict_message(loan.title, exclude=[loan.pk])
                + " "
                + _("Zurzeit ist kein Exemplar frei.")
            )
        due_date = min(due_date, latest)
    now = timezone.now()
    loan.copy = copy
    loan.status = Loan.Status.LENT
    loan.lent_at = now
    loan.due_date = due_date
    loan.handed_over_by = by
    if not loan.approved_by_id:
        loan.approved_by = by
        loan.decided_at = now
    if anonymous:
        personal = {
            "borrower": None,
            "approved_by": None,
            "handed_over_by": None,
            "message": "",
        }
        for field, value in personal.items():
            setattr(loan, field, value)
        loan.borrower_label = label
        loan.save()
        Loan.history.filter(id=loan.pk).update(history_user=None, **personal)
        return loan
    loan.save()
    return loan


def daily_request_tasks(today=None):
    """Täglich: liegen gebliebene Anfragen beim Team anmahnen, nicht abgeholte
    Genehmigungen verfallen lassen. Gibt die Anzahl je Art zurück."""
    today = today or timezone.localdate()
    config = SchoolSettings.current()
    now = timezone.now()
    counts = {"anfrage_erinnert": 0, "verfallen": 0}

    stale = Loan.objects.filter(
        status=Loan.Status.REQUESTED,
        request_reminded_at__isnull=True,
        requested_at__date__lte=today - datetime.timedelta(days=config.request_reminder_days),
    ).select_related("title", "borrower")
    for loan in stale:
        if _mail(
            "request_pending",
            [p.email for p in deciders(loan.title, today)],
            {"loan": loan, "link": _url(reverse("home"))},
        ):
            loan.request_reminded_at = now
            loan.save(update_fields=["request_reminded_at"])
            counts["anfrage_erinnert"] += 1

    # Anfragen mit Zeitraum: das Team am Vortag des Beginns erinnern, wenn noch
    # niemand entschieden hat. Sie verfallen nie, solange das Team nicht reagiert.
    from fundus.loans import reservations

    tomorrow = today + datetime.timedelta(days=1)
    starting = Loan.objects.filter(
        status=Loan.Status.REQUESTED,
        start_reminded_at__isnull=True,
        reserved_from__gte=reservations.day_start(tomorrow),
        reserved_from__lt=reservations.day_end(tomorrow),
    ).select_related("title", "borrower")
    for loan in starting:
        if _mail(
            "request_starts",
            [p.email for p in deciders(loan.title, today)],
            {"loan": loan, "link": _url(reverse("home"))},
        ):
            loan.start_reminded_at = now
            loan.save(update_fields=["start_reminded_at"])
            counts["anfrage_erinnert"] += 1

    # Genehmigt, aber nicht abgeholt: ohne Zeitraum nach der eingestellten Frist,
    # mit Zeitraum an dessen Ende.
    expired = (
        Loan.objects.filter(
            status=Loan.Status.APPROVED,
            reserved_from__isnull=True,
            decided_at__date__lte=today - datetime.timedelta(days=config.request_pickup_days),
        )
        | Loan.objects.filter(status=Loan.Status.APPROVED, reserved_until__lte=now)
    ).select_related("title", "borrower")
    for loan in expired:
        loan.status = Loan.Status.EXPIRED
        loan.save(update_fields=["status", "updated_at"])
        recipients = [loan.borrower.email] if loan.borrower_id else []
        if loan.reserved_from:
            recipients += [p.email for p in deciders(loan.title, today)]
        _mail("request_expired", recipients, {"loan": loan})
        counts["verfallen"] += 1
    return counts
