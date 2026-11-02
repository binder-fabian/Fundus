"""Der Wunschzeitraum von Anfragen wird zur Reservierung (ganze Tage)."""

import datetime

from django.db import migrations
from django.utils import timezone


def forwards(apps, schema_editor):
    Loan = apps.get_model("loans", "Loan")
    loans = Loan.objects.filter(wished_from__isnull=False) | Loan.objects.filter(
        wished_until__isnull=False
    )
    for loan in loans:
        moment = loan.requested_at or loan.created_at
        first = loan.wished_from or timezone.localtime(moment).date()
        last = max(loan.wished_until or first, first)
        start = datetime.datetime.combine(first, datetime.time.min)
        end = datetime.datetime.combine(last + datetime.timedelta(days=1), datetime.time.min)
        Loan.objects.filter(pk=loan.pk).update(
            reserved_from=timezone.make_aware(start), reserved_until=timezone.make_aware(end)
        )


class Migration(migrations.Migration):
    dependencies = [("loans", "0006_reservations")]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
        migrations.RemoveField(model_name="historicalloan", name="wished_from"),
        migrations.RemoveField(model_name="historicalloan", name="wished_until"),
        migrations.RemoveField(model_name="loan", name="wished_from"),
        migrations.RemoveField(model_name="loan", name="wished_until"),
    ]
