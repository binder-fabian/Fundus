import datetime
import signal
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from fundus.core.daily import describe, run_daily
from fundus.core.models import SchoolSettings


class Command(BaseCommand):
    help = (
        "Läuft dauerhaft und erledigt einmal täglich ab REMINDER_HOUR (Standard 7 Uhr) die "
        "täglichen Aufgaben (siehe daily_tasks). Für den Container-Dienst „scheduler“."
    )

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Nur einmal prüfen, dann beenden.")

    def handle(self, *args, **options):
        self.running = True
        signal.signal(signal.SIGTERM, self._stop)
        signal.signal(signal.SIGINT, self._stop)
        self.stdout.write(f"Zeitplan aktiv: täglich ab {settings.REMINDER_HOUR}:00 Uhr.")
        while self.running:
            close_old_connections()
            self.tick()
            self.heartbeat()
            if options["once"]:
                break
            for _ in range(60):
                if not self.running:
                    break
                time.sleep(1)

    def tick(self, now=None):
        now = timezone.localtime(now)
        if now.hour < settings.REMINDER_HOUR:
            return False
        if SchoolSettings.current().last_reminder_run == now.date():
            return False
        self.stdout.write(f"{now:%d.%m.%Y %H:%M} {describe(run_daily(now.date()))}")
        return True

    def heartbeat(self):
        """Lebenszeichen für den Healthcheck des Containers."""
        Path(settings.SCHEDULER_HEARTBEAT).touch()

    def _stop(self, *args):
        self.running = False


def next_run(now):
    """Nur zur Anzeige/Doku: nächster Lauf nach `now`."""
    run = now.replace(hour=settings.REMINDER_HOUR, minute=0, second=0, microsecond=0)
    return run if run > now else run + datetime.timedelta(days=1)
