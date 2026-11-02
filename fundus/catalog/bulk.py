"""Massenerfassung: viele ISBNs nacheinander scannen und auf einmal übernehmen."""

import re
from collections import Counter

from django.db import transaction

from fundus.catalog import isbn_lookup, numbering
from fundus.catalog.isbn import normalize_isbn, validate_isbn
from fundus.catalog.models import Copy, Title

ISBN_TOKEN = re.compile(r"(?<![\dXx])(?:97[89][\d-]{10,14}|[\d-]{9,12}[\dXx])(?![\dXx])")
MAX_ISBNS = 300


def parse_isbns(text):
    """Findet ISBNs im Text (eine pro Zeile, aus einer CSV-Spalte oder gemischt).

    Gibt [(isbn, anzahl), ...] in der Reihenfolge des ersten Auftretens und
    die Liste ungültiger Einträge zurück. Mehrfach gescannt = mehrere Exemplare.
    """
    valid, invalid = [], []
    for token in ISBN_TOKEN.findall(text or ""):
        isbn = normalize_isbn(token)
        try:
            validate_isbn(isbn)
        except Exception:
            invalid.append(token)
        else:
            valid.append(isbn)
    counts = Counter(valid)
    ordered = list(dict.fromkeys(valid))[:MAX_ISBNS]
    return [(isbn, counts[isbn]) for isbn in ordered], invalid


def existing_title(isbn):
    return Title.objects.filter(isbn=isbn).first()


@transaction.atomic
def create(rows, category, location=None, lendable=False):
    """Legt Titel und Exemplare an.

    `rows` ist eine Liste von (isbn, anzahl). Vorhandene Titel mit gleicher
    ISBN bekommen nur neue Exemplare. Gibt (neue_titel, ergänzte_titel,
    exemplare, nicht_gefunden) zurück.
    """
    new_titles, extended, missing = [], [], []
    plan = []
    for isbn, count in rows:
        title = existing_title(isbn)
        if title:
            extended.append(title)
        else:
            result = isbn_lookup.lookup(isbn)
            if not result.found:
                missing.append(isbn)
                continue
            data = result.data
            edition = ", ".join(v for v in (data.get("edition", ""), data.get("year", "")) if v)
            title = Title(
                isbn=isbn,
                title=data["title"][:300],
                subtitle=data.get("subtitle", "")[:300],
                author=data.get("author", "")[:300],
                publisher=data.get("publisher", "")[:200],
                edition=edition[:100],
                category=category,
                lendable=lendable,
            )
            title._change_reason = "Massenerfassung"
            title.save()
            new_titles.append(title)
        plan.append((title, count))

    copies = []
    for title, count in plan:
        for number in numbering.allocate(count, title.category):
            copy = Copy(title=title, inventory_number=number, location=location)
            copy._change_reason = "Massenerfassung"
            copy.save()
            copies.append(copy)
    return new_titles, extended, copies, missing
