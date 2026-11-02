from django.core.management.base import BaseCommand, CommandError

from fundus.core.backup import BackupError, create_backup


class Command(BaseCommand):
    help = "Legt sofort eine Sicherung in BACKUP_DIR an und löscht überzählige alte."

    def handle(self, *args, **options):
        try:
            path = create_backup()
        except BackupError as error:
            raise CommandError(f"Sicherung fehlgeschlagen: {error}") from error
        self.stdout.write(f"Sicherung angelegt: {path}")
