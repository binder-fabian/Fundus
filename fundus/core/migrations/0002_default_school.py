from django.db import migrations


def create_default_school(apps, schema_editor):
    School = apps.get_model("core", "School")
    if not School.objects.exists():
        School.objects.create(name="Meine Schule")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_default_school, migrations.RunPython.noop),
    ]
