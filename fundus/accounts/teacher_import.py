"""Massenanlage von Lehrkräften aus einer CSV-Datei (Vorname, Nachname, E-Mail)."""

import csv
import io
from dataclasses import asdict, dataclass

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from fundus.accounts.models import User

HEADER_ALIASES = {
    "first_name": {"vorname", "first name", "firstname", "given name"},
    "last_name": {"nachname", "name", "familienname", "last name", "lastname", "surname"},
    "email": {"e-mail", "email", "mail", "e-mail-adresse", "emailadresse", "e-mail adresse"},
}

NEW = "new"
EXISTS = "exists"
DUPLICATE = "duplicate"
INVALID = "invalid"


class SemicolonDialect(csv.excel):
    delimiter = ";"


@dataclass
class Row:
    line: int
    first_name: str
    last_name: str
    email: str
    status: str
    message: str = ""


def decode(data):
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Unbekannte Zeichenkodierung")


def _column_map(header):
    normalized = [cell.strip().lower() for cell in header]
    mapping = {}
    for field, aliases in HEADER_ALIASES.items():
        for index, cell in enumerate(normalized):
            if cell in aliases:
                mapping[field] = index
                break
    return mapping if len(mapping) == 3 else None


def parse(data):
    """Liest die Datei und bewertet jede Zeile. Gibt eine Liste von `Row` zurück."""
    text = decode(data)
    try:
        dialect = csv.Sniffer().sniff(text[:2048], delimiters=";,\t")
    except csv.Error:
        dialect = SemicolonDialect
    records = [r for r in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in r)]
    if not records:
        return []

    mapping = _column_map(records[0])
    start = 1 if mapping else 0
    mapping = mapping or {"first_name": 0, "last_name": 1, "email": 2}

    existing = {e.lower() for e in User.objects.values_list("email", flat=True)}
    seen = set()
    rows = []
    for offset, record in enumerate(records[start:], start=start + 1):

        def cell(field, record=record):
            index = mapping[field]
            return record[index].strip() if index < len(record) else ""

        row = Row(offset, cell("first_name"), cell("last_name"), cell("email").lower(), NEW)
        try:
            validate_email(row.email)
        except ValidationError:
            row.status, row.message = INVALID, "E-Mail-Adresse fehlt oder ist ungültig"
        else:
            if row.email in existing:
                row.status, row.message = EXISTS, "Konto existiert bereits"
            elif row.email in seen:
                row.status, row.message = DUPLICATE, "Doppelt in der Datei"
        if row.status == NEW and not (row.first_name or row.last_name):
            row.status, row.message = INVALID, "Name fehlt"
        seen.add(row.email)
        rows.append(row)
    return rows


def to_session(rows):
    return [asdict(r) for r in rows if r.status == NEW]
