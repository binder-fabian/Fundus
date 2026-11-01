from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from fundus.transfer.exporter import export_filename, write_export


class Command(BaseCommand):
    help = "Exportiert alle Daten als ZIP (CSV pro Tabelle, JSON, Katalogliste, Bilder)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            help="Zieldatei oder -verzeichnis. Standard: <DATA_DIR>/exporte/",
        )

    def handle(self, *args, **options):
        target = Path(options["output"] or settings.DATA_DIR / "exporte")
        if target.suffix.lower() != ".zip":
            target.mkdir(parents=True, exist_ok=True)
            target = target / export_filename()
        target.parent.mkdir(parents=True, exist_ok=True)
        write_export(target)
        self.stdout.write(self.style.SUCCESS(f"Export geschrieben: {target}"))
