import datetime
import zipfile

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from fundus.accounts.models import Role, User
from fundus.catalog.models import Title
from fundus.core import backup
from fundus.core.models import SchoolSettings
from fundus.loans import services
from fundus.loans.models import Loan
from tests.factories import CopyFactory, TitleFactory, UserFactory

pytestmark = pytest.mark.django_db(transaction=True)

HOUR = datetime.timedelta(hours=1)


def test_backup_contains_database_files_and_export(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    (settings.MEDIA_ROOT / "cover").mkdir(parents=True)
    (settings.MEDIA_ROOT / "cover" / "a.jpg").write_bytes(b"jpg")
    UserFactory(email="a@schule.de")
    path = backup.create_backup()
    assert path.parent == settings.BACKUP_DIR
    names = zipfile.ZipFile(path).namelist()
    assert {"datenbank.json", "version.json", "export.zip", "dateien/cover/a.jpg"} <= set(names)
    data = zipfile.ZipFile(path).read("datenbank.json").decode()
    user = User.objects.get(email="a@schule.de")
    assert user.email in data and user.password in data  # Passwort-Prüfwert ist dabei
    assert SchoolSettings.current().last_backup_at is not None


def test_old_backups_are_pruned():
    config = SchoolSettings.current()
    config.backup_keep = 2
    config.save()
    now = timezone.now()
    for i in range(4):
        backup.create_backup(now + i * HOUR)
    files = backup.existing_backups()
    assert len(files) == 2
    assert files[0].name > files[1].name


def test_schedule():
    config = SchoolSettings.current()
    now = timezone.now()
    assert backup.is_due(now, config)
    config.last_backup_at = now - 20 * HOUR
    assert backup.is_due(now, config)  # täglich, mit Spielraum
    config.last_backup_at = now - 2 * HOUR
    assert not backup.is_due(now, config)
    config.backup_interval = config.BackupInterval.WEEKLY
    config.last_backup_at = now - 3 * 24 * HOUR
    assert not backup.is_due(now, config)
    config.backup_interval = config.BackupInterval.OFF
    assert not backup.is_due(now, config) and not backup.is_overdue(now, config)


def test_daily_tasks_back_up_once(capsys):
    call_command("daily_tasks")
    call_command("daily_tasks")
    assert len(backup.existing_backups()) == 1
    assert "Sicherungen angelegt: 1" in capsys.readouterr().out


def test_restore_into_empty_database_and_replace(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    teacher = UserFactory(email="lehrerin@schule.de")
    copy = CopyFactory(title=TitleFactory(title="Rechentest"))
    services.lend(copy, by=teacher)
    history_rows = Title.history.count()
    path = backup.create_backup()

    with pytest.raises(backup.BackupError, match="schon Daten"):
        backup.restore(path)

    Title.objects.create(title="Danach angelegt", category=copy.title.category)
    backup.restore(path, replace=True)
    assert not Title.objects.filter(title="Danach angelegt").exists()
    restored = User.objects.get(email="lehrerin@schule.de")
    assert restored.check_password("geheim-1234")
    assert Loan.objects.get().borrower == restored
    assert Title.history.count() == history_rows
    # Neue Datensätze bekommen danach freie Nummern (Sequenzen in PostgreSQL)
    assert UserFactory().pk > restored.pk


def test_restore_command_refuses_newer_backup(tmp_path):
    path = backup.create_backup()
    with zipfile.ZipFile(path) as archive:
        contents = {n: archive.read(n) for n in archive.namelist()}
    contents["version.json"] = b'{"erstellt": "2030-01-01", "migrationen": ["core.9999_zukunft"]}'
    newer = tmp_path / "neuer.zip"
    with zipfile.ZipFile(newer, "w") as archive:
        for name, data in contents.items():
            archive.writestr(name, data)
    with pytest.raises(Exception, match="neueren Fundus-Version"):
        call_command("restore_backup", str(newer), "--ersetzen")


def test_settings_show_backup_state_and_backup_now(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    page = client.get(reverse("school_settings")).content.decode()
    assert "Es gibt keine aktuelle Sicherung" in page
    response = client.post(reverse("backup_now"), follow=True)
    assert "Sicherung angelegt: fundus-sicherung-" in response.content.decode()
    assert "1 Sicherungen vorhanden" in response.content.decode()


def test_failed_backup_is_reported(client, monkeypatch):
    def broken(archive, now):
        raise OSError("Datenträger voll")

    monkeypatch.setattr(backup, "_write_backup", broken)
    assert backup.run() == {"sicherung_fehlgeschlagen": 1}
    assert not list(backup.existing_backups())
    client.force_login(UserFactory(role=Role.ADMIN))
    assert "Datenträger voll" in client.get(reverse("school_settings")).content.decode()
