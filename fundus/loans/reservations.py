"""Reservierungen: einen Titel für ganze Tage oder einzelne Stunden vormerken.

Eine Reservierung ist eine Ausleihe mit Status „reserviert“ und Zeitraum; sie
gilt dem Titel, das Exemplar steht erst bei der Abholung fest. Wer mehrere
Exemplare reserviert, bekommt je Exemplar einen Eintrag mit gemeinsamer Kennung.

Belegt ist ein Titel zu einem Zeitpunkt durch
- laufende Ausleihen (bis zum Ende ihres Rückgabetags, mindestens bis heute),
- Reservierungen und Anfragen mit Zeitraum.
Frei ist, was von der Zahl der Exemplare übrig bleibt.
"""

import datetime
import uuid

from django.db import transaction
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from fundus.catalog.models import Title
from fundus.loans.models import Loan
from fundus.loans.services import LoanError, anonymous_mode, clean_label

# Einträge, die einen Zeitraum blockieren, solange sie offen sind.
BLOCKING = (Loan.Status.RESERVED, Loan.Status.REQUESTED, Loan.Status.APPROVED)


# Zeiten


def day_start(day):
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time.min))


def day_end(day):
    """Ende eines Tages = Beginn des nächsten (ausschließlich)."""
    return day_start(day + datetime.timedelta(days=1))


def last_day(until):
    """Letzter belegter Tag eines Zeitraums mit ausschließlichem Ende."""
    return timezone.localtime(until - datetime.timedelta(microseconds=1)).date()


def days_period(first, last):
    if last < first:
        raise LoanError(_("„Bis“ liegt vor „von“."))
    return day_start(first), day_end(last)


def lessons_period(day, first, last, lessons):
    """Zeitraum und Bezeichnung für die Stunden first–last an einem Tag."""
    by_number = {n: (start, end) for n, start, end in lessons}
    if first not in by_number or last not in by_number:
        raise LoanError(_("Diese Stunde gibt es im Stundenraster nicht."))
    if last < first:
        raise LoanError(_("Die letzte Stunde liegt vor der ersten."))
    start = timezone.make_aware(datetime.datetime.combine(day, by_number[first][0]))
    end = timezone.make_aware(datetime.datetime.combine(day, by_number[last][1]))
    label = _("%(n)s. Stunde") % {"n": first} if first == last else f"{first}.–{last}. Stunde"
    return start, end, label


def describe_period(start, end, label=""):
    if start is None:
        return ""
    first = timezone.localtime(start).date()
    if label:
        return f"{date_format(first, 'SHORT_DATE_FORMAT')}, {label}"
    last = last_day(end)
    if first == last:
        return date_format(first, "SHORT_DATE_FORMAT")
    if first.year == last.year:
        return f"{first:%d.%m.}–{date_format(last, 'SHORT_DATE_FORMAT')}"
    return f"{date_format(first, 'SHORT_DATE_FORMAT')}–{date_format(last, 'SHORT_DATE_FORMAT')}"


# Belegung


def capacity(title):
    return title.copies.count()


def busy_intervals(title, exclude=(), now=None):
    """Alle belegten Zeiträume eines Titels als (Beginn, Ende, Ausleihe)."""
    now = now or timezone.now()
    today = timezone.localdate(now)
    exclude = {pk for pk in exclude if pk}
    intervals = []
    lent = Loan.objects.filter(title=title, status=Loan.Status.LENT).exclude(pk__in=exclude)
    for loan in lent:
        if (
            loan.period_label
            and loan.reserved_until
            and loan.due_date == last_day(loan.reserved_until)
        ):
            # Für Stunden abgeholt: belegt bis zum Ende der letzten Stunde.
            end = max(loan.reserved_until, now)
        else:
            end = day_end(max(loan.due_date or today, today))
        intervals.append((min(loan.lent_at, now), end, loan))
    reserved = (
        Loan.objects.filter(title=title, status__in=BLOCKING, reserved_from__isnull=False)
        .exclude(pk__in=exclude)
        .select_related("borrower")
    )
    for loan in reserved:
        intervals.append((loan.reserved_from, loan.reserved_until, loan))
    return intervals


def max_busy(intervals, start, end):
    """Höchste Zahl gleichzeitig belegter Exemplare im Zeitraum [start, end)."""
    events = []
    for a, b, _loan in intervals:
        a, b = max(a, start), min(b, end)
        if a < b:
            events.append((a, 1))
            events.append((b, -1))
    events.sort(key=lambda e: (e[0], e[1]))  # Enden vor Beginnen zur selben Zeit
    busy = peak = 0
    for _time, delta in events:
        busy += delta
        peak = max(peak, busy)
    return peak


def free_count(title, start, end, exclude=(), intervals=None):
    if intervals is None:
        intervals = busy_intervals(title, exclude)
    return capacity(title) - max_busy(intervals, start, end)


def next_free_start(title, start, end, quantity, intervals, whole_days):
    """Frühester Beginn ab `start`, zu dem ein gleich langer Zeitraum frei ist."""
    length = end - start
    total = capacity(title)
    candidates = sorted({b for _a, b, _l in intervals if b > start})
    for candidate in candidates:
        if whole_days and timezone.localtime(candidate).time() != datetime.time.min:
            candidate = day_end(timezone.localtime(candidate).date())
        if total - max_busy(intervals, candidate, candidate + length) >= quantity:
            return candidate
    return None


def first_conflict(title, since, exclude=(), extra=1):
    """Frühester Zeitpunkt ab `since`, an dem ein zusätzliches, offenes Ende
    belegtes Exemplar nicht mehr frei wäre – oder None."""
    intervals = busy_intervals(title, exclude)
    total = capacity(title)
    points = sorted({since} | {a for a, _b, _l in intervals if a > since})
    for point in points:
        # Belegung ab diesem Zeitpunkt bis zum nächsten Ereignis
        busy = sum(1 for a, b, _l in intervals if a <= point < b)
        if busy + extra > total:
            return point
    return None


def latest_due_date(title, since=None, exclude=()):
    """Spätestes Rückgabedatum für eine neue Ausleihe ab `since`, damit keine
    Reservierung platzt. None = unbegrenzt. Liegt das Ergebnis vor heute, ist
    gerade kein Exemplar für eine Ausleihe frei."""
    since = since or timezone.now()
    conflict = first_conflict(title, since, exclude)
    if conflict is None:
        return None
    return timezone.localtime(conflict).date() - datetime.timedelta(days=1)


def conflict_message(title, since=None, exclude=()):
    since = since or timezone.now()
    conflict = first_conflict(title, since, exclude)
    if conflict is None:
        return ""
    local = timezone.localtime(conflict)
    if local.time() == datetime.time.min:
        when = date_format(local.date(), "SHORT_DATE_FORMAT")
    else:
        when = f"{date_format(local.date(), 'SHORT_DATE_FORMAT')} {local:%H:%M}"
    return _("Ab %(when)s ist dieser Titel reserviert.") % {"when": when}


# Vorgänge


def pickup_candidate(title, borrower=None, label="", now=None):
    """Reservierung, die jetzt abgeholt werden kann: heute begonnen oder heute
    beginnend, noch nicht vorbei, für diese Person bzw. Klasse."""
    now = now or timezone.now()
    today = timezone.localdate(now)
    loans = Loan.objects.filter(
        title=title,
        status=Loan.Status.RESERVED,
        reserved_from__lt=day_end(today),
        reserved_until__gt=now,
    ).order_by("reserved_from")
    if borrower is not None:
        return loans.filter(borrower=borrower).first()
    if label:
        return loans.filter(borrower__isnull=True, borrower_label__iexact=label.strip()).first()
    return None


def check_period(title, start, end, quantity=1, exclude=(), whole_days=None):
    """Prüft einen Zeitraum: liegt er nicht in der Vergangenheit und sind genug
    Exemplare frei? Wirft LoanError mit dem frühesten freien Beginn."""
    if not title.lendable:
        raise LoanError(_("Dieser Titel ist nicht zum Ausleihen vorgesehen."))
    if end <= timezone.now():
        raise LoanError(_("Dieser Zeitraum liegt in der Vergangenheit."))
    if end <= start:
        raise LoanError(_("Das Ende liegt vor dem Beginn."))
    total = capacity(title)
    if quantity < 1:
        raise LoanError(_("Bitte mindestens ein Exemplar reservieren."))
    if quantity > total:
        raise LoanError(_("Von diesem Titel gibt es nur %(n)d Exemplar(e).") % {"n": total})
    if whole_days is None:
        whole_days = timezone.localtime(start).time() == datetime.time.min
    intervals = busy_intervals(title, exclude)
    free = total - max_busy(intervals, start, end)
    if free >= quantity:
        return
    hint = ""
    alternative = next_free_start(title, start, end, quantity, intervals, whole_days)
    if alternative:
        local = timezone.localtime(alternative)
        hint = " " + _("Frühestens wieder ab %(when)s.") % {
            "when": date_format(local.date(), "SHORT_DATE_FORMAT")
            + ("" if whole_days else f" {local:%H:%M}")
        }
    if free <= 0:
        raise LoanError(_("In diesem Zeitraum ist kein Exemplar frei.") + hint)
    raise LoanError(_("In diesem Zeitraum sind nur %(n)d Exemplar(e) frei.") % {"n": free} + hint)


@transaction.atomic
def reserve(title, by, start, end, quantity=1, label="", period_label=""):
    title = Title.objects.select_for_update().get(pk=title.pk)
    if title.approval_required:
        raise LoanError(_("Freigabepflichtige Titel bitte anfragen."))
    anonymous = anonymous_mode()
    if anonymous:
        label = clean_label(label)
    check_period(title, start, end, quantity, whole_days=not period_label)

    group = uuid.uuid4() if quantity > 1 else None
    created = []
    for _i in range(quantity):
        created.append(
            Loan.objects.create(
                title=title,
                borrower=None if anonymous else by,
                borrower_label=label if anonymous else "",
                status=Loan.Status.RESERVED,
                reserved_from=start,
                reserved_until=end,
                period_label=period_label,
                group=group,
            )
        )
    return created


def group_of(loan):
    if loan.group:
        return Loan.objects.filter(group=loan.group)
    return Loan.objects.filter(pk=loan.pk)


def can_cancel(user, loan):
    if user.can_manage_catalog:
        return True
    if loan.borrower_id is None:
        return user.is_authenticated and user.is_active
    return loan.borrower_id == user.pk


@transaction.atomic
def cancel(loan, by):
    """Storniert eine Reservierung (alle noch nicht abgeholten Exemplare)."""
    loan = Loan.objects.select_for_update().get(pk=loan.pk)
    if loan.status != Loan.Status.RESERVED:
        raise LoanError(_("Diese Reservierung ist nicht mehr offen."))
    if not can_cancel(by, loan):
        raise LoanError(_("Nur die Person, die reserviert hat, kann stornieren."))
    return (
        group_of(loan)
        .filter(status=Loan.Status.RESERVED)
        .update(status=Loan.Status.WITHDRAWN, updated_at=timezone.now())
    )


def my_reservations(user):
    """Offene Reservierungen einer Person, je Gruppe ein Eintrag mit Anzahl."""
    rows = (
        Loan.objects.filter(borrower=user, status=Loan.Status.RESERVED)
        .select_related("title")
        .order_by("reserved_from", "pk")
    )
    return collapse(rows)


def collapse(rows):
    seen = {}
    result = []
    for loan in rows:
        key = loan.group or loan.pk
        if key in seen:
            seen[key].quantity += 1
            continue
        loan.quantity = 1
        seen[key] = loan
        result.append(loan)
    return result


# Kalender


def week_start(day):
    return day - datetime.timedelta(days=day.weekday())


def week_grid(title, monday, lessons, now=None):
    """Belegung einer Woche: je Tag ganzer Tag und jede Unterrichtsstunde mit
    Zahl der freien Exemplare. Samstag/Sonntag nur, wenn dort etwas reserviert ist."""
    now = now or timezone.now()
    intervals = busy_intervals(title, now=now)
    total = capacity(title)
    days = []
    for offset in range(7):
        day = monday + datetime.timedelta(days=offset)
        start, end = day_start(day), day_end(day)
        whole = total - max_busy(intervals, start, end)
        if offset >= 5 and not any(
            loan.status != Loan.Status.LENT and a < end and b > start for a, b, loan in intervals
        ):
            continue
        cells = []
        for number, first, last in lessons:
            a = timezone.make_aware(datetime.datetime.combine(day, first))
            b = timezone.make_aware(datetime.datetime.combine(day, last))
            cells.append(
                {
                    "number": number,
                    "free": total - max_busy(intervals, a, b),
                    "past": b <= now,
                }
            )
        days.append(
            {"day": day, "whole": whole, "cells": cells, "past": end <= now, "total": total}
        )
    rows = [
        {
            "number": number,
            "time": f"{first:%H:%M}–{last:%H:%M}",
            "cells": [d["cells"][i] | {"day": d["day"]} for d in days],
        }
        for i, (number, first, last) in enumerate(lessons)
    ]
    return {"days": days, "rows": rows, "total": total}


# Täglich


def daily_tasks(today=None, now=None):
    """Erinnerung am Vortag, Hinweis „noch nicht abgeholt“, Verfall am Ende
    des Zeitraums. Gibt die Anzahl je Art zurück."""
    from django.urls import reverse

    from fundus.core.models import SchoolSettings
    from fundus.loans.requests import _mail, _url

    now = now or timezone.now()
    today = today or timezone.localdate(now)
    counts = {"reservierung_erinnert": 0, "reservierung_nicht_abgeholt": 0}

    if SchoolSettings.current().reservation_reminders:
        tomorrow = today + datetime.timedelta(days=1)
        upcoming = Loan.objects.filter(
            status__in=[Loan.Status.RESERVED, Loan.Status.APPROVED],
            borrower__isnull=False,
            start_reminded_at__isnull=True,
            reserved_from__gte=day_start(tomorrow),
            reserved_from__lt=day_end(tomorrow),
        ).select_related("title", "borrower")
        for loan in collapse(upcoming):
            if _mail(
                "reservation_tomorrow",
                [loan.borrower.email],
                {
                    "loan": loan,
                    "quantity": loan.quantity,
                    "link": _url(reverse("reserve", args=[loan.title_id])),
                },
            ):
                group_of(loan).update(start_reminded_at=now)
                counts["reservierung_erinnert"] += 1

        missed = Loan.objects.filter(
            status=Loan.Status.RESERVED,
            borrower__isnull=False,
            missed_notice_at__isnull=True,
            reserved_from__lt=day_start(today),
            reserved_until__gt=now,
        ).select_related("title", "borrower")
        for loan in collapse(missed):
            if _mail(
                "reservation_missed",
                [loan.borrower.email],
                {"loan": loan, "link": _url(reverse("reserve", args=[loan.title_id]))},
            ):
                group_of(loan).update(missed_notice_at=now)
                counts["reservierung_nicht_abgeholt"] += 1

    counts["reservierung_verfallen"] = Loan.objects.filter(
        status=Loan.Status.RESERVED, reserved_until__lte=now
    ).update(status=Loan.Status.EXPIRED, updated_at=now)
    return counts
