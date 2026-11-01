"""Vergabe neuer Inventarnummern nach dem Nummernschema der Schule."""

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


def preview_next():
    settings = SchoolSettings.current()
    start = max(settings.next_number, highest_existing(settings.number_prefix) + 1)
    return settings.format_number(start)


@transaction.atomic
def allocate(count):
    """Reserviert `count` neue, noch freie Inventarnummern und gibt sie zurück.

    Muss in derselben Transaktion verwendet werden, die die Exemplare anlegt;
    die Sperre auf den Einstellungen verhindert doppelte Vergabe.
    """
    settings = SchoolSettings.objects.select_for_update().get(pk=SchoolSettings.current().pk)
    number = max(settings.next_number, highest_existing(settings.number_prefix) + 1)
    numbers = []
    while len(numbers) < count:
        candidate = settings.format_number(number)
        if not Copy.objects.filter(inventory_number__iexact=candidate).exists():
            numbers.append(candidate)
        number += 1
    settings.next_number = number
    settings.save(update_fields=["next_number"])
    return numbers
