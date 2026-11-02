"""Vollständiger Export aller Daten als ZIP: eine CSV-Datei pro Tabelle, eine
JSON-Datei mit allem, eine flache Katalogliste und die hochgeladenen Bilder.

Die CSV-Dateien nutzen Semikolon und UTF-8 mit BOM, damit Excel sie direkt
richtig öffnet. Passwörter werden nie exportiert.
"""

import csv
import datetime
import io
import json
import zipfile

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

from fundus.accounts.models import User
from fundus.catalog.models import Category, Copy, Location, SupportFocus, Team, Title
from fundus.core.models import School
from fundus.loans.models import Loan
from fundus.transfer.models import ImportTemplate

EXPORT_VERSION = 1

# Dateiname → Modell. Reihenfolge = Reihenfolge im ZIP.
TABLES = {
    "schulen": School,
    "kategorien": Category,
    "foerderschwerpunkte": SupportFocus,
    "standorte": Location,
    "teams": Team,
    "team_mitglieder": Team.members.through,
    "titel": Title,
    "titel_foerderschwerpunkte": Title.support_focuses.through,
    "exemplare": Copy,
    "ausleihen": Loan,
    "benutzer": User,
    "importvorlagen": ImportTemplate,
}
HISTORY = {
    "protokoll_titel": Title,
    "protokoll_exemplare": Copy,
    "protokoll_kategorien": Category,
    "protokoll_foerderschwerpunkte": SupportFocus,
    "protokoll_standorte": Location,
    "protokoll_teams": Team,
    "protokoll_ausleihen": Loan,
    "protokoll_benutzer": User,
}
NEVER_EXPORT = {"password", "search_text"}

CATALOG_COLUMNS = [
    "Inventarnummer",
    "Titel",
    "Untertitel",
    "Autor",
    "Verlag",
    "ISBN",
    "Auflage",
    "Kategorie",
    "Förderschwerpunkte",
    "Standort",
    "Regal",
    "Beschreibung",
    "Normjahr",
    "Inhaltsliste",
    "Ausleihbar",
    "Notiz",
    "Zustand",
    "Unvollständig",
]


def _columns(model):
    return [f.attname for f in model._meta.concrete_fields if f.attname not in NEVER_EXPORT]


def _rows(model):
    columns = _columns(model)
    return columns, list(model._default_manager.order_by("pk").values_list(*columns))


def _csv_value(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime.datetime | datetime.date):
        return value.isoformat()
    if isinstance(value, dict | list):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _csv(columns, rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_csv_value(v) for v in row])
    return "﻿" + buffer.getvalue()


def catalog_rows():
    """Eine Zeile pro Exemplar mit allen Titeldaten – passt zum Import-Assistenten."""
    copies = Copy.objects.select_related("title__category", "location").prefetch_related(
        "title__support_focuses"
    )
    for c in copies.order_by("inventory_number"):
        t = c.title
        yield [
            c.inventory_number,
            t.title,
            t.subtitle,
            t.author,
            t.publisher,
            t.isbn,
            t.edition,
            t.category.name,
            ", ".join(f.name for f in t.support_focuses.all()),
            c.location.room if c.location else "",
            c.location.shelf if c.location else "",
            t.description,
            t.norm_year or "",
            t.contents,
            "ja" if t.lendable else "nein",
            c.note,
            c.get_condition_display(),
            "ja" if c.incomplete else "nein",
        ]


def write_export(target):
    """Schreibt das ZIP in `target` (Pfad oder Datei-Objekt)."""
    now = timezone.now()
    everything = {
        "meta": {
            "fundus_export_version": EXPORT_VERSION,
            "exported_at": now,
            "hinweis": "Passwörter sind nicht enthalten.",
        },
        "tables": {},
    }
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, model in TABLES.items():
            columns, rows = _rows(model)
            archive.writestr(f"csv/{name}.csv", _csv(columns, rows))
            everything["tables"][name] = [dict(zip(columns, r, strict=True)) for r in rows]
        for name, model in HISTORY.items():
            history_model = model.history.model
            columns, rows = _rows(history_model)
            archive.writestr(f"csv/{name}.csv", _csv(columns, rows))
            everything["tables"][name] = [dict(zip(columns, r, strict=True)) for r in rows]

        archive.writestr("katalog.csv", _csv(CATALOG_COLUMNS, catalog_rows()))
        archive.writestr(
            "fundus.json",
            json.dumps(everything, cls=DjangoJSONEncoder, ensure_ascii=False, indent=1),
        )
        archive.writestr("LIESMICH.txt", README.format(date=now.strftime("%d.%m.%Y %H:%M")))

        media_root = settings.MEDIA_ROOT
        if media_root.exists():
            for path in sorted(media_root.rglob("*")):
                if path.is_file():
                    archive.write(path, f"dateien/{path.relative_to(media_root)}")


def export_filename():
    return f"fundus-export-{timezone.localtime():%Y-%m-%d-%H%M}.zip"


README = """Fundus – vollständiger Export vom {date}

katalog.csv     Eine Zeile pro Exemplar mit allen Titeldaten. Lässt sich in Excel
                öffnen und über „Import“ wieder in Fundus einlesen.
csv/            Eine Datei pro Tabelle (Semikolon-getrennt, UTF-8). Spalten mit
                „_id“ verweisen auf die Spalte „id“ der jeweiligen Tabelle.
                protokoll_*.csv enthalten das Änderungsprotokoll.
fundus.json     Alle Tabellen in einer Datei, für Programme.
dateien/        Hochgeladene Bilder (Cover).

Passwörter sind nicht enthalten.
"""
