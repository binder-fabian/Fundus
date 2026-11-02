from django.core.management.base import BaseCommand, CommandError

from fundus.core.backup import BackupError, restore


class Command(BaseCommand):
    help = (
        "Spielt eine Fundus-Sicherung (ZIP) ein. Standardmäßig nur in eine leere Datenbank; "
        "mit --ersetzen werden vorhandene Daten vorher gelöscht. Vorher „migrate“ ausführen."
    )

    def add_arguments(self, parser):
        parser.add_argument("datei", help="Pfad zur Sicherung (fundus-sicherung-….zip)")
        parser.add_argument(
            "--ersetzen",
            action="store_true",
            help="Alle vorhandenen Daten löschen und durch die Sicherung ersetzen.",
        )

    def handle(self, *args, **options):
        try:
            version = restore(options["datei"], replace=options["ersetzen"])
        except BackupError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(
            f"Sicherung vom {version['erstellt'][:16].replace('T', ' ')} eingespielt. "
            "Alle Personen müssen sich neu anmelden."
        )
