"""Vergabe neuer Inventarnummern nach dem Nummernschema der Schule.

Jede Kategorie kann ein eigenes Präfix haben (z. B. „B-“ für Bücher, „T-“ für
Tests); jede Präfix-Folge zählt für sich. Kategorien ohne eigenes Präfix
nutzen das allgemeine Präfix aus den Einstellungen.
"""

import re

from django.db import transaction

from fundus.catalog.models import Copy
from fundus.core.models import SchoolSettings


def highest_existing(prefix):
    """Größte laufende Nummer unter den vorhandenen Exemplaren mit diesem Präfix."""
    pattern = re.compile(re.escape(prefix) + r"(\d+)$", re.IGNORECASE)
    numbers = Copy.objects.filter(inventory_number__istartswith=prefix).values_list(
        "inventory_number", flat=True
    )
    found = [int(m.group(1)) for n in numbers if (m := pattern.match(n))]
    return max(found, default=0)


def prefix_for(settings, category=None):
    return (category.number_prefix if category else "") or settings.number_prefix


def _start(settings, prefix):
    start = highest_existing(prefix) + 1
    if prefix == settings.number_prefix:
        # Die gespeicherte nächste Nummer gilt nur für das allgemeine Präfix.
        start = max(start, settings.next_number)
    return start


def _format(settings, prefix, number):
    return f"{prefix}{number:0{settings.number_digits}d}"


def preview_next(category=None):
    settings = SchoolSettings.current()
    prefix = prefix_for(settings, category)
    return _format(settings, prefix, _start(settings, prefix))


@transaction.atomic
def allocate(count, category=None):
    """Reserviert `count` neue, noch freie Inventarnummern und gibt sie zurück.

    Muss in derselben Transaktion verwendet werden, die die Exemplare anlegt;
    die Sperre auf den Einstellungen verhindert doppelte Vergabe.
    """
    settings = SchoolSettings.objects.select_for_update().get(pk=SchoolSettings.current().pk)
    prefix = prefix_for(settings, category)
    number = _start(settings, prefix)
    numbers = []
    while len(numbers) < count:
        candidate = _format(settings, prefix, number)
        if not Copy.objects.filter(inventory_number__iexact=candidate).exists():
            numbers.append(candidate)
        number += 1
    if prefix == settings.number_prefix:
        settings.next_number = number
        settings.save(update_fields=["next_number"])
    return numbers
