from django.db import migrations


def person(user):
    name = f"{user.first_name} {user.last_name}".strip()
    return name or user.email


def responsible_to_teams(apps, schema_editor):
    """Übernimmt „zuständige Person + Vertretung“ als kleines Team."""
    Title = apps.get_model("catalog", "Title")
    Team = apps.get_model("catalog", "Team")
    teams = {}
    titles = Title.objects.exclude(responsible__isnull=True, deputy__isnull=True)
    for title in titles.select_related("responsible", "deputy"):
        people = [p for p in (title.responsible, title.deputy) if p is not None]
        key = (title.school_id, tuple(sorted({p.pk for p in people})))
        if key not in teams:
            base = "Team " + " / ".join(person(p) for p in people)
            name, n = base[:100], 2
            while Team.objects.filter(school_id=title.school_id, name=name).exists():
                name, n = f"{base[:95]} ({n})", n + 1
            team = Team.objects.create(school_id=title.school_id, name=name)
            team.members.set(people)
            teams[key] = team
        title.team = teams[key]
        title.save(update_fields=["team"])


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0007_teams"),
        ("accounts", "0004_absent_until"),
    ]

    operations = [
        migrations.RunPython(responsible_to_teams, migrations.RunPython.noop),
    ]
