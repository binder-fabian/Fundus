from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from fundus.catalog.models import Category, Copy, Location, SupportFocus, Title

# Erfundene Beispieldaten zum Ausprobieren. Keine echten Personen.
LOCATIONS = [
    ("Raum 104", "Testschrank"),
    ("Raum 104", "Regal 2"),
    ("Bibliothek", ""),
    ("Raum 9", ""),
]

TITLES = [
    {
        "title": "Lesetest 2–4 (Beispiel)",
        "author": "Muster, M.",
        "category": "Diagnostik/Tests",
        "norm_year": 2019,
        "contents": "Manual\nTestheft A\nTestheft B\nAuswertungsschablone",
        "lendable": True,
        "focuses": ["Lernen", "Sprache"],
        "copies": [("DEMO-0001", 0), ("DEMO-0002", 0)],
    },
    {
        "title": "Rechentest 1 (Beispiel)",
        "author": "Beispiel, B.",
        "category": "Diagnostik/Tests",
        "norm_year": 2009,
        "contents": "Manual\nProtokollbögen\nMaterialkoffer",
        "lendable": True,
        "focuses": ["Lernen"],
        "copies": [("DEMO-0003", 0)],
    },
    {
        "title": "Gefühlekarten für die Klasse",
        "author": "Team Fördermaterial",
        "category": "Fördermaterial",
        "lendable": True,
        "focuses": ["Emotionale und soziale Entwicklung"],
        "copies": [("DEMO-0010", 1)],
    },
    {
        "title": "Wortschatzspiel Tiere",
        "category": "Fördermaterial",
        "focuses": ["Sprache"],
        "copies": [("DEMO-0011", 1), ("DEMO-0012", 1)],
    },
    {
        "title": "Das kleine Buch vom Mut",
        "author": "Erfunden, E.",
        "publisher": "Beispielverlag",
        "category": "Bücher",
        "copies": [("DEMO-0100", 2), ("DEMO-0101", 2), ("DEMO-0102", 2)],
    },
    {
        "title": "Tablet-Koffer (8 Geräte)",
        "category": "Technik",
        "contents": "8 Tablets\n8 Ladekabel\nLadestation",
        "lendable": True,
        "copies": [("DEMO-0200", 3)],
    },
]


class Command(BaseCommand):
    help = "Legt erfundene Beispieldaten an, um Fundus auszuprobieren."

    @transaction.atomic
    def handle(self, *args, **options):
        if Copy.objects.filter(inventory_number__startswith="DEMO-").exists():
            raise CommandError("Beispieldaten sind schon vorhanden.")
        locations = [Location.objects.get_or_create(room=r, shelf=s)[0] for r, s in LOCATIONS]
        for data in TITLES:
            data = dict(data)
            focuses = data.pop("focuses", [])
            copies = data.pop("copies")
            data["category"] = Category.objects.get_or_create(name=data["category"])[0]
            title = Title.objects.create(**data)
            title.support_focuses.set(SupportFocus.objects.filter(name__in=focuses))
            for number, location in copies:
                Copy.objects.create(
                    title=title, inventory_number=number, location=locations[location]
                )
        self.stdout.write(self.style.SUCCESS(f"{len(TITLES)} Beispieltitel angelegt."))
