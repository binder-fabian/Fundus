from fundus.core.management.commands.daily_tasks import Command as DailyTasks


class Command(DailyTasks):
    help = "Alter Name für „daily_tasks“ (bleibt, damit bestehende Cron-Einträge weiterlaufen)."
