"""Rechte der Betroffenen: Konto löschen und „Meine Daten“ (Auskunft).

Beim Löschen eines Kontos werden alle Ausleihen der Person anonymisiert, offene
Anfragen zurückgezogen und ihr Name aus dem Änderungsprotokoll entfernt.
"""

import csv
import io
import zipfile

from django.apps import apps
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _

from fundus.accounts.models import FailedLogin, User
from fundus.core import privacy


class AccountError(Exception):
    pass


def deletion_blockers(user, by):
    """Gründe, warum das Konto (noch) nicht gelöscht werden kann."""
    from fundus.loans.models import Loan

    reasons = []
    if user.pk == by.pk:
        reasons.append(_("Das eigene Konto kann man nicht selbst löschen."))
    if user.is_admin and User.objects.active_admins().exclude(pk=user.pk).count() == 0:
        reasons.append(_("Es muss mindestens eine Administratorin oder ein Administrator bleiben."))
    lent = Loan.objects.filter(borrower=user, status=Loan.Status.LENT).count()
    if lent:
        reasons.append(
            _("Die Person hat noch %(n)d Exemplar(e) ausgeliehen. Bitte erst zurückbuchen.")
            % {"n": lent}
        )
    return reasons


@transaction.atomic
def delete_account(user, by):
    from fundus.loans.models import Loan

    reasons = deletion_blockers(user, by)
    if reasons:
        raise AccountError(" ".join(reasons))
    Loan.objects.filter(borrower=user, status__in=Loan.OPEN).update(status=Loan.Status.WITHDRAWN)
    privacy.anonymize_loans(Loan.objects.filter(borrower=user).values_list("pk", flat=True))

    # Spuren in anderen Ausleihen und im Protokoll („genehmigt von“, „übergeben von“)
    HistoricalLoan = Loan.history.model
    for field in ("approved_by", "handed_over_by"):
        HistoricalLoan.objects.filter(**{field: user.pk}).update(**{field: None})
    for model in privacy.history_models():
        model.objects.filter(history_user=user.pk).update(history_user=None)
    FailedLogin.objects.filter(username__iexact=user.email).delete()
    name, pk = str(user), user.pk
    user.delete()
    # Erst danach: das Löschen selbst legt noch einen Protokolleintrag an.
    User.history.filter(id=pk).delete()
    apps.get_model("catalog", "HistoricalTeam_members").objects.filter(user=pk).delete()
    return name


# Auskunft


def _csv(header, rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(header)
    for row in rows:
        writer.writerow(["" if v is None else v for v in row])
    return "﻿" + buffer.getvalue()


def _date(value):
    if value is None:
        return ""
    if hasattr(value, "tzinfo"):
        return timezone.localtime(value).strftime("%d.%m.%Y %H:%M")
    return value.strftime("%d.%m.%Y")


def personal_data_zip(user):
    from fundus.loans.models import Loan
    from fundus.supplies.models import ReorderNotice

    files = {}
    files["konto.csv"] = _csv(
        [
            "E-Mail",
            "Vorname",
            "Nachname",
            "Rolle",
            "aktiv",
            "abwesend bis",
            "angelegt",
            "letzte Anmeldung",
        ],
        [
            [
                user.email,
                user.first_name,
                user.last_name,
                user.get_role_display(),
                _("ja") if user.is_active else _("nein"),
                _date(user.absent_until),
                _date(user.date_joined),
                _date(user.last_login),
            ]
        ],
    )
    files["teams.csv"] = _csv(["Team"], [[t.name] for t in user.teams.order_by("name")])

    loans = (
        Loan.objects.filter(borrower=user).select_related("title", "copy").order_by("created_at")
    )
    files["ausleihen_und_anfragen.csv"] = _csv(
        [
            "Titel",
            "Inventarnummer",
            "Status",
            "angefragt",
            "reserviert für",
            "Nachricht",
            "ausgeliehen",
            "Rückgabe geplant",
            "zurückgegeben",
            "Ablehnungsgrund",
        ],
        [
            [
                loan.title.title,
                loan.copy.inventory_number if loan.copy_id else "",
                loan.get_status_display(),
                _date(loan.requested_at),
                loan.period_display,
                loan.message,
                _date(loan.lent_at),
                _date(loan.due_date),
                _date(loan.returned_at),
                loan.rejection_reason,
            ]
            for loan in loans
        ],
    )

    handled = (
        Loan.objects.filter(Q(approved_by=user) | Q(handed_over_by=user))
        .select_related("title", "copy")
        .order_by("created_at")
    )
    files["fuer_andere_bearbeitet.csv"] = _csv(
        ["Titel", "Inventarnummer", "Status", "genehmigt von Ihnen", "übergeben von Ihnen", "am"],
        [
            [
                loan.title.title,
                loan.copy.inventory_number if loan.copy_id else "",
                loan.get_status_display(),
                _("ja") if loan.approved_by_id == user.pk else "",
                _("ja") if loan.handed_over_by_id == user.pk else "",
                _date(loan.decided_at or loan.lent_at),
            ]
            for loan in handled
        ],
    )

    notices = (
        ReorderNotice.objects.filter(Q(created_by=user) | Q(handled_by=user))
        .select_related("consumable")
        .order_by("created_at")
    )
    files["nachbestellungen.csv"] = _csv(
        ["Material", "Status", "gemeldet am", "von Ihnen gemeldet", "von Ihnen bearbeitet"],
        [
            [
                n.consumable.name,
                n.get_status_display(),
                _date(n.created_at),
                _("ja") if n.created_by_id == user.pk else "",
                _("ja") if n.handled_by_id == user.pk else "",
            ]
            for n in notices
        ],
    )

    changes = []
    for model in privacy.history_models():
        kind = model.instance_type._meta.verbose_name
        for row in model.objects.filter(history_user=user.pk).order_by("history_date"):
            changes.append(
                [_date(row.history_date), kind, str(row.instance), row.get_history_type_display()]
            )
    changes.sort(key=lambda r: r[0])
    files["aenderungsprotokoll.csv"] = _csv(["am", "Art", "Datensatz", "Vorgang"], changes)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        archive.writestr("LIESMICH.txt", README.format(date=_date(timezone.now())))
    return buffer.getvalue()


README = """Fundus – Ihre gespeicherten Daten (Stand {date})

konto.csv                    Ihr Konto (das Passwort ist nur als Prüfwert gespeichert
                             und deshalb nicht enthalten)
teams.csv                    Teams, in denen Sie Mitglied sind
ausleihen_und_anfragen.csv   Ihre Ausleihen, Anfragen und Reservierungen, soweit noch
                             nicht anonymisiert
fuer_andere_bearbeitet.csv   Anfragen, die Sie genehmigt oder übergeben haben
nachbestellungen.csv         Nachbestellhinweise, die Sie gemeldet oder bearbeitet haben
aenderungsprotokoll.csv      Änderungen, die mit Ihrem Namen protokolliert sind

Fehlgeschlagene Anmeldeversuche werden nach einem Tag gelöscht.
Fragen dazu beantwortet die Schulleitung bzw. die oder der Datenschutzbeauftragte.
"""
