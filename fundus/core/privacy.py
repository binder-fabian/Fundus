"""Datenschutz: Namen nach Ablauf der Fristen entfernen.

- Abgeschlossene Ausleihen verlieren nach `anonymize_after_days` alle Angaben zu
  Personen – auch in ihren Zeilen im Änderungsprotokoll. Titel, Exemplar und
  Daten bleiben für die Statistik.
- Im Änderungsprotokoll aller Datensätze wird nach `history_names_days` die
  ändernde Person („wer“) entfernt.
- Erledigte Nachbestellhinweise verlieren nach der Ausleihfrist ihre Namen,
  abgelaufene Abwesenheiten werden gelöscht.

Bereinigt wird mit `update()`, damit dabei keine neuen Protokollzeilen entstehen.
"""

import datetime

from django.apps import apps
from django.db import transaction
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from fundus.core.models import SchoolSettings

# Felder einer Ausleihe mit Personenbezug und ihr Wert nach der Anonymisierung.
LOAN_PERSONAL_FIELDS = {
    "borrower": None,
    "borrower_label": "",
    "approved_by": None,
    "handed_over_by": None,
    "message": "",
    "rejection_reason": "",
}


def _loan_models():
    from fundus.loans.models import Loan

    return Loan, Loan.history.model


def closed_loans():
    """Abgeschlossene, noch nicht anonymisierte Ausleihen mit Abschlussdatum."""
    Loan, _history = _loan_models()
    return Loan.objects.filter(
        status__in=[
            Loan.Status.RETURNED,
            Loan.Status.REJECTED,
            Loan.Status.WITHDRAWN,
            Loan.Status.EXPIRED,
        ],
        anonymized_at__isnull=True,
    ).annotate(closed_at=Coalesce("returned_at", "updated_at"))


def loans_due(now=None, config=None):
    now = now or timezone.now()
    config = config or SchoolSettings.current()
    cutoff = now - datetime.timedelta(days=config.anonymize_after_days)
    return closed_loans().filter(closed_at__lte=cutoff)


@transaction.atomic
def anonymize_loans(loan_ids, now=None):
    """Entfernt alle Angaben zu Personen aus den Ausleihen und ihrem Protokoll."""
    Loan, HistoricalLoan = _loan_models()
    loan_ids = list(loan_ids)
    if not loan_ids:
        return 0
    now = now or timezone.now()
    count = Loan.objects.filter(pk__in=loan_ids).update(anonymized_at=now, **LOAN_PERSONAL_FIELDS)
    HistoricalLoan.objects.filter(id__in=loan_ids).update(
        history_user=None, anonymized_at=now, **LOAN_PERSONAL_FIELDS
    )
    return count


def history_models():
    """Alle Tabellen des Änderungsprotokolls mit „wer hat geändert“."""
    return [
        m
        for m in apps.get_models()
        if m.__name__.startswith("Historical") and hasattr(m, "history_user")
    ]


def strip_history_users(now=None, config=None):
    now = now or timezone.now()
    config = config or SchoolSettings.current()
    cutoff = now - datetime.timedelta(days=config.history_names_days)
    total = 0
    for model in history_models():
        total += model.objects.filter(history_user__isnull=False, history_date__lte=cutoff).update(
            history_user=None
        )
    return total


def strip_reorder_names(now=None, config=None):
    from fundus.supplies.models import ReorderNotice

    now = now or timezone.now()
    config = config or SchoolSettings.current()
    cutoff = now - datetime.timedelta(days=config.anonymize_after_days)
    return (
        ReorderNotice.objects.exclude(status__in=ReorderNotice.OPEN)
        .filter(created_at__lte=cutoff)
        .filter(Q(created_by__isnull=False) | Q(handled_by__isnull=False))
        .update(created_by=None, handled_by=None)
    )


def clear_past_absences(today=None):
    from fundus.accounts.models import User

    today = today or timezone.localdate()
    return User.objects.filter(absent_until__lt=today).update(absent_until=None)


def run(now=None):
    """Tägliche Bereinigung. Gibt die Anzahl je Art zurück."""
    now = now or timezone.now()
    config = SchoolSettings.current()
    counts = {
        "ausleihen_anonymisiert": anonymize_loans(
            loans_due(now, config).values_list("pk", flat=True), now
        ),
        "protokoll_namen_entfernt": strip_history_users(now, config),
        "nachbestellungen_bereinigt": strip_reorder_names(now, config),
        "abwesenheiten_geloescht": clear_past_absences(timezone.localdate(now)),
    }
    # update() statt save(): kein neuer Eintrag im Änderungsprotokoll der Einstellungen
    SchoolSettings.objects.filter(pk=config.pk).update(last_privacy_run=now)
    return counts
