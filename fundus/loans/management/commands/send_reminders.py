from django.core.management.base import BaseCommand

from fundus.loans.reminders import send_reminders


class Command(BaseCommand):
    help = "Verschickt fällige E-Mail-Erinnerungen (einmal täglich aufrufen, z. B. per Cron)."

    def handle(self, *args, **options):
        counts = send_reminders()
        self.stdout.write(
            f"Erinnerungen: {counts['vorher']} vor Ablauf, {counts['ueberfaellig']} überfällig, "
            f"{counts['verwaltung']} an die Verwaltung gemeldet."
        )
