from django.db import migrations

# Startwerte; die Schule kann sie jederzeit ändern oder löschen.
# Fristen laut Entscheidung vom 1. November 2026: Tests und Technik 14 Tage,
# Bücher und Material 28 Tage.
CATEGORIES = [
    ("Bücher", 28),
    ("Diagnostik/Tests", 14),
    ("Fördermaterial", 28),
    ("Technik", 14),
]

SUPPORT_FOCUSES = [
    "Lernen",
    "Sprache",
    "Emotionale und soziale Entwicklung",
    "Geistige Entwicklung",
    "Körperliche und motorische Entwicklung",
    "Hören",
    "Sehen",
]


def seed(apps, schema_editor):
    School = apps.get_model("core", "School")
    Category = apps.get_model("catalog", "Category")
    SupportFocus = apps.get_model("catalog", "SupportFocus")
    for school in School.objects.all():
        for name, days in CATEGORIES:
            Category.objects.get_or_create(
                school=school, name=name, defaults={"default_loan_days": days}
            )
        for name in SUPPORT_FOCUSES:
            SupportFocus.objects.get_or_create(school=school, name=name)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0001_initial"),
        ("core", "0002_default_school"),
    ]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
