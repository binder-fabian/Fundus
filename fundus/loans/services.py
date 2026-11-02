"""Ausleihen, Zurückgeben, Verlängern – mit allen Regeln an einer Stelle.

Die Oberfläche ruft nur diese Funktionen auf. Sie werfen `LoanError` mit
einer verständlichen Meldung, wenn etwas nicht erlaubt ist.
"""

import datetime

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from fundus.catalog.models import Copy
from fundus.core.models import SchoolSettings
from fundus.loans.models import Loan


class LoanError(Exception):
    pass


# Rechte


def is_responsible(user, title):
    """Mitglied des zuständigen Teams (auch bei Abwesenheit)."""
    return (
        user.is_authenticated
        and title.team_id is not None
        and title.team.members.filter(pk=user.pk).exists()
    )


def contact_for(title):
    """Wen Lehrkräfte bei freigabepflichtigen Titeln ansprechen."""
    return title.team or _("die Verwaltung")


def can_lend_for_others(user, title):
    """Verwalter immer, zuständige Person und Vertretung für ihre Titel."""
    return user.can_manage_catalog or is_responsible(user, title)


def can_see_borrower(user, title):
    """Einstellung der Schule: Namen nur für Verwaltung und zuständiges Team
    oder für alle angemeldeten Lehrkräfte."""
    if user.can_manage_catalog or is_responsible(user, title):
        return True
    config = SchoolSettings.current()
    return user.is_active and config.borrower_visibility == config.Visibility.ALL


def can_return(user, loan):
    """Entscheidung C: Freigabepflichtige Titel bucht nur die zuständige Person
    (bzw. Vertretung oder Verwaltung) zurück – wie bei der Übergabe. Alle anderen
    Titel darf jede angemeldete Person zurückbuchen, z. B. wenn ein Exemplar im
    Lehrerzimmer liegen geblieben ist."""
    title = loan.copy.title
    if title.approval_required:
        return can_lend_for_others(user, title)
    return user.is_authenticated and user.is_active


def can_extend(user, loan):
    """Die ausleihende Person oder die Verwaltung; Ausleihen ohne Namen
    (nur Klasse/Raum) darf verlängern, wer sie auch zurückbuchen darf."""
    if loan.borrower_id is None:
        return can_return(user, loan)
    return loan.borrower_id == user.pk or user.can_manage_catalog


def pending_request(copy):
    """Liegt für den Titel dieses Exemplars eine offene Anfrage vor?"""
    return Loan.objects.filter(title_id=copy.title_id, status__in=Loan.OPEN_REQUEST).exists()


# Vorgänge


def default_due_date(copy, today=None):
    return copy.title.default_due_date(today or timezone.localdate())


@transaction.atomic
def anonymous_mode():
    return SchoolSettings.current().anonymous_lending


def clean_label(label):
    label = " ".join((label or "").split())
    if not label:
        raise LoanError(_("Bitte Klasse oder Raum angeben."))
    return label[:100]


def lend(copy, by, borrower=None, due_date=None, label=""):
    """Leiht ein Exemplar aus – für `borrower` (Standard: `by`) oder, im Modus
    ohne Namen, für eine Klasse bzw. einen Raum (`label`)."""
    copy = (
        Copy.objects.select_for_update(of=("self",))
        .select_related("title__category")
        .get(pk=copy.pk)
    )
    title = copy.title
    anonymous = anonymous_mode()
    if anonymous:
        label = clean_label(label)
        borrower = None
    else:
        borrower = borrower or by
    if not title.lendable:
        raise LoanError(_("Dieser Titel ist nicht zum Ausleihen vorgesehen."))
    if copy.loans.filter(status=Loan.Status.LENT).exists():
        raise LoanError(_("Dieses Exemplar ist bereits ausgeliehen."))
    if borrower and not borrower.is_active:
        raise LoanError(_("Dieses Konto ist deaktiviert."))
    if borrower and borrower != by and not can_lend_for_others(by, title):
        raise LoanError(_("Sie können nur für sich selbst ausleihen."))
    if title.approval_required and not can_lend_for_others(by, title):
        raise LoanError(_("Freigabepflichtig: Bitte an %(p)s wenden.") % {"p": contact_for(title)})

    today = timezone.localdate()
    due_date = due_date or default_due_date(copy, today)
    if due_date < today:
        raise LoanError(_("Das Rückgabedatum liegt in der Vergangenheit."))

    loan = Loan(
        copy=copy,
        borrower=borrower,
        borrower_label=label if anonymous else "",
        status=Loan.Status.LENT,
        lent_at=timezone.now(),
        due_date=due_date,
        handed_over_by=(
            by if not anonymous and (by != borrower or title.approval_required) else None
        ),
    )
    try:
        with transaction.atomic():
            loan.save()
    except IntegrityError as error:
        raise LoanError(_("Dieses Exemplar ist bereits ausgeliehen.")) from error
    return loan


@transaction.atomic
def return_copy(copy, by, complete=None, missing=()):
    """Bucht ein Exemplar zurück. `complete` (True/False/None) ist das Ergebnis
    der Inhaltsprüfung bei Testkoffern; `missing` die fehlenden Teile."""
    copy = Copy.objects.select_for_update(of=("self",)).select_related("title").get(pk=copy.pk)
    loan = copy.loans.filter(status=Loan.Status.LENT).select_related("borrower").first()
    if loan is None:
        raise LoanError(_("Dieses Exemplar ist nicht ausgeliehen."))
    if not can_return(by, loan):
        raise LoanError(
            _("Freigabepflichtig: Zurückbuchen bitte über %(p)s.")
            % {"p": contact_for(loan.copy.title)}
        )

    loan.status = Loan.Status.RETURNED
    loan.returned_at = timezone.now()
    loan.save(update_fields=["status", "returned_at", "updated_at"])

    if complete is False:
        copy.incomplete = True
        if missing:
            line = _("Fehlt seit %(d)s: %(parts)s") % {
                "d": date_format(timezone.localdate(), "SHORT_DATE_FORMAT"),
                "parts": ", ".join(missing),
            }
            copy.note = f"{copy.note}\n{line}".strip()
        copy._change_reason = "Rückgabe: unvollständig"
        copy.save()
    elif complete is True and copy.incomplete:
        copy.incomplete = False
        copy._change_reason = "Rückgabe: vollständig"
        copy.save()
    return loan


@transaction.atomic
def extend(loan, by, today=None):
    loan = (
        Loan.objects.select_for_update(of=("self",))
        .select_related("copy__title__category")
        .get(pk=loan.pk)
    )
    if loan.status != Loan.Status.LENT:
        raise LoanError(_("Nur laufende Ausleihen können verlängert werden."))
    if not can_extend(by, loan):
        raise LoanError(_("Nur die ausleihende Person kann verlängern."))
    if pending_request(loan.copy):
        raise LoanError(
            _("Für dieses Exemplar liegt eine Anfrage vor; Verlängern ist nicht möglich.")
        )
    today = today or timezone.localdate()
    new_due = default_due_date(loan.copy, today)
    if loan.due_date and new_due <= loan.due_date:
        new_due = loan.due_date + datetime.timedelta(
            days=loan.copy.title.category.default_loan_days
        )
    loan.due_date = new_due
    loan.reminder_sent_at = None
    loan.overdue_notice_sent_at = None
    loan.escalated_at = None
    loan.save()
    return loan
