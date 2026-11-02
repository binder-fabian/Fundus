"""Statistik: wie oft wurde was ausgeliehen?

Gezählt wird aus dem Ausleihprotokoll, auch nach der Anonymisierung. Bewusst
gibt es keine Auswertung nach Personen (Leistungs- und Verhaltenskontrolle).
"""

import datetime
import io
from collections import Counter, defaultdict
from dataclasses import dataclass

from django.utils import timezone
from django.utils.translation import gettext as _

from fundus.catalog.models import Title
from fundus.loans.models import Loan

LENT_STATES = (Loan.Status.LENT, Loan.Status.RETURNED)


@dataclass
class Period:
    start: datetime.date
    end: datetime.date
    label: str

    @property
    def filename_part(self):
        return f"{self.start:%Y-%m-%d}_{self.end:%Y-%m-%d}"


def school_year_start(day, month_day=(8, 1)):
    """Beginn des Schuljahrs, in dem `day` liegt."""
    month, first = month_day
    year = day.year if (day.month, day.day) >= (month, first) else day.year - 1
    return datetime.date(year, month, first)


def presets(today=None, config=None):
    """Vorgegebene Zeiträume: aktuelles und letztes Schuljahr, beide Halbjahre.
    Beginn von Schuljahr und 2. Halbjahr stehen in den Einstellungen."""
    from fundus.core.models import SchoolSettings

    today = today or timezone.localdate()
    year_md, half_md = (config or SchoolSettings.current()).school_year_dates
    start = school_year_start(today, year_md)
    year = start.year
    next_start = datetime.date(year + 1, *year_md)
    end = next_start - datetime.timedelta(days=1)
    half_year = year if half_md > year_md else year + 1
    half = datetime.date(half_year, *half_md)
    previous = datetime.date(year - 1, *year_md)
    one_day = datetime.timedelta(days=1)
    return {
        "schuljahr": Period(start, end, _("Schuljahr %(y)s") % {"y": _sy(year)}),
        "halbjahr1": Period(start, half - one_day, _("1. Halbjahr %(y)s") % {"y": _sy(year)}),
        "halbjahr2": Period(half, end, _("2. Halbjahr %(y)s") % {"y": _sy(year)}),
        "vorjahr": Period(previous, start - one_day, _("Schuljahr %(y)s") % {"y": _sy(year - 1)}),
    }


def _sy(year):
    return f"{year}/{str(year + 1)[-2:]}"


def period_from(params, today=None):
    """Zeitraum aus den GET-Parametern (zeitraum=… oder von/bis)."""
    options = presets(today)
    key = params.get("zeitraum", "schuljahr")
    if key == "frei":
        try:
            start = datetime.date.fromisoformat(params.get("von", ""))
            end = datetime.date.fromisoformat(params.get("bis", ""))
        except ValueError:
            return "schuljahr", options["schuljahr"]
        if end < start:
            start, end = end, start
        label = _("%(a)s bis %(b)s") % {"a": f"{start:%d.%m.%Y}", "b": f"{end:%d.%m.%Y}"}
        return "frei", Period(start, end, label)
    if key not in options:
        key = "schuljahr"
    return key, options[key]


def _days(loan_lent_at, loan_returned_at):
    return (loan_returned_at - loan_lent_at).total_seconds() / 86400


def compute(period):
    lent = Loan.objects.filter(
        status__in=LENT_STATES,
        lent_at__date__gte=period.start,
        lent_at__date__lte=period.end,
    ).values_list("title_id", "lent_at", "returned_at")

    per_title = Counter()
    durations = defaultdict(list)
    last_lent = {}
    for title_id, lent_at, returned_at in lent:
        per_title[title_id] += 1
        if returned_at:
            durations[title_id].append(_days(lent_at, returned_at))
        if title_id not in last_lent or lent_at > last_lent[title_id]:
            last_lent[title_id] = lent_at

    titles = {
        t.pk: t
        for t in Title.objects.filter(pk__in=per_title)
        .select_related("category")
        .prefetch_related("support_focuses")
    }

    rows = []
    per_category = Counter()
    per_focus = Counter()
    for title_id, count in per_title.items():
        title = titles[title_id]
        days = durations[title_id]
        rows.append(
            {
                "title": title,
                "count": count,
                "avg_days": sum(days) / len(days) if days else None,
                "last_lent": timezone.localtime(last_lent[title_id]).date(),
            }
        )
        per_category[title.category.name] += count
        for focus in title.support_focuses.all():
            per_focus[focus.name] += count
    rows.sort(key=lambda r: (-r["count"], r["title"].title.lower()))

    never = (
        Title.objects.filter(lendable=True)
        .exclude(pk__in=per_title)
        .select_related("category")
        .order_by("title")
    )

    all_days = [d for values in durations.values() for d in values]
    requests = Counter(
        Loan.objects.filter(
            requested_at__date__gte=period.start, requested_at__date__lte=period.end
        ).values_list("status", flat=True)
    )
    handed_over = requests[Loan.Status.LENT] + requests[Loan.Status.RETURNED]
    return {
        "period": period,
        "total": sum(per_title.values()),
        "title_count": len(per_title),
        "avg_days": sum(all_days) / len(all_days) if all_days else None,
        "rows": rows,
        "per_category": sorted(per_category.items(), key=lambda i: (-i[1], i[0].lower())),
        "per_focus": sorted(per_focus.items(), key=lambda i: (-i[1], i[0].lower())),
        "never": never,
        "requests": {
            "total": sum(requests.values()),
            "handed_over": handed_over,
            "open": requests[Loan.Status.REQUESTED] + requests[Loan.Status.APPROVED],
            "rejected": requests[Loan.Status.REJECTED],
            "withdrawn": requests[Loan.Status.WITHDRAWN],
            "expired": requests[Loan.Status.EXPIRED],
        },
    }


def _round(value):
    return round(value, 1) if value is not None else None


def workbook(data):
    """Excel-Datei mit einer Tabelle je Auswertung."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    book = Workbook()
    bold = Font(bold=True)

    def sheet(name, header, rows, first=False):
        ws = book.active if first else book.create_sheet()
        ws.title = name
        ws.append(header)
        for cell in ws[1]:
            cell.font = bold
        for row in rows:
            ws.append(list(row))
        for column, width in zip("ABCDEF", (40, 22, 12, 22, 14, 14), strict=False):
            ws.column_dimensions[column].width = width
        return ws

    req = data["requests"]
    sheet(
        _("Übersicht"),
        [_("Kennzahl"), _("Wert")],
        [
            (_("Zeitraum"), data["period"].label),
            (_("von"), data["period"].start),
            (_("bis"), data["period"].end),
            (_("Ausleihen"), data["total"]),
            (_("verschiedene Titel"), data["title_count"]),
            (_("durchschnittliche Ausleihdauer (Tage)"), _round(data["avg_days"])),
            (_("Anfragen"), req["total"]),
            (_("davon übergeben"), req["handed_over"]),
            (_("davon offen"), req["open"]),
            (_("davon abgelehnt"), req["rejected"]),
            (_("davon zurückgezogen"), req["withdrawn"]),
            (_("davon verfallen"), req["expired"]),
        ],
        first=True,
    )
    sheet(
        _("Titel"),
        [_("Titel"), _("Kategorie"), _("Ausleihen"), _("Ø Tage"), _("zuletzt ausgeliehen")],
        (
            (
                r["title"].title,
                r["title"].category.name,
                r["count"],
                _round(r["avg_days"]),
                r["last_lent"],
            )
            for r in data["rows"]
        ),
    )
    sheet(_("Kategorien"), [_("Kategorie"), _("Ausleihen")], data["per_category"])
    sheet(_("Förderschwerpunkte"), [_("Förderschwerpunkt"), _("Ausleihen")], data["per_focus"])
    sheet(
        _("Nicht ausgeliehen"),
        [_("Titel"), _("Kategorie")],
        ((t.title, t.category.name) for t in data["never"]),
    )
    for ws in book.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, datetime.date):
                    cell.number_format = "DD.MM.YYYY"
    buffer = io.BytesIO()
    book.save(buffer)
    buffer.seek(0)
    return buffer
