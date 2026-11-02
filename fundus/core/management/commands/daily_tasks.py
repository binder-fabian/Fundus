from django.core.management.base import BaseCommand

from fundus.core.daily import describe, run_daily


class Command(BaseCommand):
    help = (
        "Tägliche Aufgaben: Erinnerungen und Anfragen per E-Mail, Namen nach Ablauf der "
        "Löschfristen entfernen. Einmal täglich aufrufen, z. B. per Cron. Im Container "
        "erledigt das der Dienst „scheduler“."
    )

    def handle(self, *args, **options):
        self.stdout.write(describe(run_daily()))
