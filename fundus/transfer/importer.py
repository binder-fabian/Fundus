"""Import vorhandener Bestände aus CSV- oder Excel-Dateien.

Ablauf: Datei lesen → Spalten zuordnen → jede Zeile prüfen (Vorschau) →
in einer Transaktion importieren. Eine Zeile ergibt ein Exemplar; Titel
werden über die ISBN oder über Titel + Autor zusammengeführt.
"""

import csv
import datetime
import io
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from fundus.catalog.isbn import normalize_isbn, validate_isbn
from fundus.catalog.models import Category, Copy, Location, SupportFocus, Title
from fundus.catalog.text import normalize

# Zielfelder in der Reihenfolge des Assistenten. Pflicht: Inventarnummer, Titel.
FIELDS = {
    "inventory_number": _("Inventarnummer"),
    "title": _("Titel"),
    "subtitle": _("Untertitel"),
    "author": _("Autor/Herausgeber"),
    "publisher": _("Verlag"),
    "isbn": _("ISBN"),
    "edition": _("Auflage"),
    "category": _("Kategorie"),
    "support_focus": _("Förderschwerpunkte (mit Komma getrennt)"),
    "room": _("Standort: Raum"),
    "shelf": _("Standort: Regal/Fach"),
    "description": _("Beschreibung"),
    "norm_year": _("Normjahr"),
    "contents": _("Inhaltsliste"),
    "lendable": _("ausleihbar (ja/nein)"),
    "note": _("Notiz zum Exemplar"),
}
REQUIRED = ("inventory_number", "title")

# Spaltennamen, die automatisch erkannt werden (klein geschrieben).
# Microsoft Lists nennen die erste Spalte immer „Title“.
ALIASES = {
    "inventory_number": {
        "inventarnummer",
        "inventar-nr",
        "inventar-nr.",
        "inv.-nr.",
        "inv-nr",
        "invnr",
        "nummer",
        "signatur",
        "barcode",
        "id-nummer",
    },
    "title": {"titel", "title", "name", "bezeichnung", "werk", "material"},
    "subtitle": {"untertitel", "subtitle"},
    "author": {"autor", "autorin", "autor/in", "author", "verfasser", "herausgeber", "autoren"},
    "publisher": {"verlag", "publisher", "hersteller"},
    "isbn": {"isbn", "isbn-13", "isbn13", "isbn-10"},
    "edition": {"auflage", "edition", "ausgabe"},
    "category": {"kategorie", "category", "art", "typ", "medienart", "gruppe"},
    "support_focus": {"förderschwerpunkt", "förderschwerpunkte", "foerderschwerpunkt"},
    "room": {"standort", "raum", "ort", "location", "aufbewahrungsort"},
    "shelf": {"regal", "fach", "regal/fach", "shelf"},
    "description": {"beschreibung", "description", "inhalt kurz", "bemerkung zum titel"},
    "norm_year": {"normjahr", "normierung", "normen", "norm"},
    "contents": {"inhaltsliste", "inhalt", "bestandteile", "contents"},
    "lendable": {"ausleihbar", "verleihbar", "lendable"},
    "note": {"notiz", "bemerkung", "kommentar", "anmerkung", "note"},
}

TRUE_VALUES = {"ja", "j", "yes", "y", "x", "1", "true", "wahr"}


class SemicolonDialect(csv.excel):
    delimiter = ";"


class ImportFileError(Exception):
    pass


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, datetime.datetime | datetime.date):
        return value.strftime("%d.%m.%Y")
    return str(value).strip()


def read_table(name, data):
    """Liest CSV oder .xlsx und gibt (Kopfzeile, Datenzeilen) als Texte zurück."""
    if name.lower().endswith(".xlsx"):
        try:
            from openpyxl import load_workbook

            workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as error:
            raise ImportFileError(_("Die Excel-Datei konnte nicht gelesen werden.")) from error
        rows = [
            [_cell(v) for v in row] for row in workbook.worksheets[0].iter_rows(values_only=True)
        ]
    elif name.lower().endswith((".csv", ".txt")):
        for encoding in ("utf-8-sig", "cp1252"):
            try:
                text = data.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ImportFileError(_("Unbekannte Zeichenkodierung."))
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=";,\t")
        except csv.Error:
            dialect = SemicolonDialect
        rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(text), dialect)]
    else:
        raise ImportFileError(_("Bitte eine CSV- oder Excel-Datei (.xlsx) wählen."))

    rows = [r for r in rows if any(r)]
    if len(rows) < 2:
        raise ImportFileError(_("Die Datei braucht eine Kopfzeile und mindestens eine Datenzeile."))
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    header = [h or f"Spalte {i + 1}" for i, h in enumerate(rows[0])]
    return header, rows[1:]


def guess_mapping(header):
    mapping = {}
    used = set()
    for target, aliases in ALIASES.items():
        for index, name in enumerate(header):
            if index not in used and name.strip().lower() in aliases:
                mapping[target] = index
                used.add(index)
                break
    return mapping


@dataclass
class Options:
    default_category: Category | None = None
    create_missing: bool = True
    lendable_default: bool = False


@dataclass
class RowResult:
    line: int
    values: dict
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    title_key: tuple | None = None
    existing_title_id: int | None = None
    first_line_of_title: int | None = None

    @property
    def ok(self):
        return not self.errors


def _title_key(values):
    if values["isbn"]:
        return ("isbn", values["isbn"])
    return ("name", normalize(values["title"]), normalize(values["author"]))


def _existing_titles():
    by_key = {}
    for pk, isbn, title, author in Title.objects.values_list("pk", "isbn", "title", "author"):
        if isbn:
            by_key.setdefault(("isbn", isbn), pk)
        by_key.setdefault(("name", normalize(title), normalize(author)), pk)
    return by_key


def analyze(rows, mapping, options):
    """Prüft alle Zeilen, ohne etwas zu speichern."""
    existing_numbers = set(
        Copy.objects.annotate(n=Lower("inventory_number")).values_list("n", flat=True)
    )
    existing_titles = _existing_titles()
    categories = {normalize(c.name): c for c in Category.objects.all()}
    seen_numbers = {}
    seen_titles = {}
    results = []

    for offset, row in enumerate(rows, start=2):
        values = {f: (row[mapping[f]] if mapping.get(f) is not None else "") for f in FIELDS}
        result = RowResult(offset, values)

        number = values["inventory_number"]
        if not number:
            result.errors.append(_("Inventarnummer fehlt"))
        elif len(number) > 50 or " " in number:
            result.errors.append(_("Inventarnummer ungültig (Leerzeichen oder zu lang)"))
        elif number.lower() in existing_numbers:
            result.errors.append(_("Inventarnummer ist schon im Katalog"))
        elif number.lower() in seen_numbers:
            result.errors.append(
                _("Inventarnummer doppelt (wie Zeile %(n)d)") % {"n": seen_numbers[number.lower()]}
            )
        else:
            seen_numbers[number.lower()] = offset

        if not values["title"]:
            result.errors.append(_("Titel fehlt"))
        if len(values["title"]) > 300:
            result.errors.append(_("Titel zu lang (höchstens 300 Zeichen)"))

        if values["isbn"]:
            try:
                validate_isbn(values["isbn"])
                values["isbn"] = normalize_isbn(values["isbn"])
            except ValidationError:
                result.warnings.append(_("ISBN ungültig, wird weggelassen"))
                values["isbn"] = ""

        if values["norm_year"]:
            year = values["norm_year"][:4]
            if year.isdigit() and 1900 <= int(year) <= 2100:
                values["norm_year"] = year
            else:
                result.warnings.append(_("Normjahr unverständlich, wird weggelassen"))
                values["norm_year"] = ""

        category_name = values["category"]
        if category_name and normalize(category_name) not in categories:
            if options.create_missing:
                result.warnings.append(
                    _("Kategorie „%(c)s“ wird neu angelegt") % {"c": category_name}
                )
            elif options.default_category:
                values["category"] = ""
            else:
                result.errors.append(_("Unbekannte Kategorie „%(c)s“") % {"c": category_name})
        if not values["category"] and not options.default_category:
            result.errors.append(_("Kategorie fehlt (oder Standard-Kategorie wählen)"))

        if result.ok:
            key = _title_key(values)
            result.title_key = key
            if key in existing_titles:
                result.existing_title_id = existing_titles[key]
            elif key in seen_titles:
                result.first_line_of_title = seen_titles[key]
            else:
                seen_titles[key] = offset
        results.append(result)
    return results


def summarize(results):
    ok = [r for r in results if r.ok]
    return {
        "rows": len(results),
        "copies": len(ok),
        "new_titles": sum(1 for r in ok if not r.existing_title_id and not r.first_line_of_title),
        "existing_titles": len({r.existing_title_id for r in ok if r.existing_title_id}),
        "errors": len(results) - len(ok),
    }


def _yes(value, default):
    return value.strip().lower() in TRUE_VALUES if value.strip() else default


@transaction.atomic
def run_import(results, options):
    """Legt Titel, Exemplare und fehlende Stammdaten an. Alles oder nichts."""
    categories = {normalize(c.name): c for c in Category.objects.all()}
    focuses = {normalize(f.name): f for f in SupportFocus.objects.all()}
    locations = {}
    titles = {}
    created_copies = 0

    for result in results:
        if not result.ok:
            continue
        v = result.values

        if result.existing_title_id:
            title = titles.setdefault(
                result.title_key, Title.objects.get(pk=result.existing_title_id)
            )
        elif result.title_key in titles:
            title = titles[result.title_key]
        else:
            category = options.default_category
            if v["category"]:
                category = categories.get(normalize(v["category"]))
                if category is None:
                    category = Category.objects.create(name=v["category"][:100])
                    categories[normalize(category.name)] = category
            title = Title(
                title=v["title"],
                subtitle=v["subtitle"][:300],
                author=v["author"][:300],
                publisher=v["publisher"][:200],
                isbn=v["isbn"],
                edition=v["edition"][:100],
                category=category,
                description=v["description"],
                norm_year=int(v["norm_year"]) if v["norm_year"] else None,
                contents=v["contents"].replace(";", "\n")
                if "\n" not in v["contents"]
                else v["contents"],
                lendable=_yes(v["lendable"], options.lendable_default),
            )
            title._change_reason = "Import"
            title.save()
            for name in filter(None, (n.strip() for n in v["support_focus"].split(","))):
                focus = focuses.get(normalize(name))
                if focus is None and options.create_missing:
                    focus = SupportFocus.objects.create(name=name[:100])
                    focuses[normalize(name)] = focus
                if focus:
                    title.support_focuses.add(focus)
            titles[result.title_key] = title

        location = None
        if v["room"]:
            key = (normalize(v["room"]), normalize(v["shelf"]))
            if key not in locations:
                location = Location.objects.filter(
                    room__iexact=v["room"], shelf__iexact=v["shelf"]
                ).first() or Location.objects.create(room=v["room"][:100], shelf=v["shelf"][:100])
                locations[key] = location
            location = locations[key]

        copy = Copy(
            title=title, inventory_number=v["inventory_number"], location=location, note=v["note"]
        )
        copy._change_reason = "Import"
        copy.save()
        created_copies += 1
    return {"copies": created_copies, "titles": len(titles)}


def report_csv(results):
    """Importbericht als CSV (Semikolon, für Excel)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(["Zeile", "Inventarnummer", "Titel", "Ergebnis", "Hinweise"])
    for r in results:
        status = "importiert" if r.ok else "übersprungen"
        notes = "; ".join(str(m) for m in [*r.errors, *r.warnings])
        writer.writerow([r.line, r.values["inventory_number"], r.values["title"], status, notes])
    return "﻿" + buffer.getvalue()
