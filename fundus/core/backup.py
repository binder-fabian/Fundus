"""Automatische Sicherung und Wiederherstellung.

Eine Sicherung ist eine ZIP-Datei mit
- datenbank.json   allen Tabellen (django dumpdata, unabhängig von SQLite/PostgreSQL),
                   einschließlich der Passwort-Prüfwerte,
- version.json     Zeitpunkt und Stand der Datenbank-Migrationen,
- dateien/         den hochgeladenen Bildern,
- export.zip       dem lesbaren Export (CSV/JSON) wie unter „Import/Export“.
"""

import datetime
import io
import json
import logging
import shutil
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.db import connection, transaction
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

from fundus.core.models import SchoolSettings

logger = logging.getLogger(__name__)

PREFIX = "fundus-sicherung-"
# Sitzungen nicht: nach einer Wiederherstellung melden sich alle neu an.
EXCLUDE = ["sessions"]
INTERVAL_DAYS = {
    SchoolSettings.BackupInterval.DAILY: 1,
    SchoolSettings.BackupInterval.WEEKLY: 7,
    SchoolSettings.BackupInterval.MONTHLY: 30,
}


class BackupError(Exception):
    pass


def backup_dir():
    path = Path(settings.BACKUP_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def existing_backups():
    """Vorhandene Sicherungen, neueste zuerst."""
    path = Path(settings.BACKUP_DIR)
    if not path.exists():
        return []
    return sorted(path.glob(f"{PREFIX}*.zip"), reverse=True)


def applied_migrations():
    return sorted(
        f"{app}.{name}" for app, name in MigrationRecorder(connection).applied_migrations()
    )


def _write_backup(archive, now):
    data = io.StringIO()
    # Mit den internen Nummern (pk) aller Tabellen, auch Inhaltstypen und
    # Berechtigungen – so passen alle Verweise nach dem Einspielen exakt.
    call_command("dumpdata", exclude=EXCLUDE, stdout=data, verbosity=0)
    archive.writestr("datenbank.json", data.getvalue())
    archive.writestr(
        "version.json",
        json.dumps(
            {
                "erstellt": now.isoformat(),
                "datenbank": connection.vendor,
                "migrationen": applied_migrations(),
            },
            indent=1,
        ),
    )
    media_root = Path(settings.MEDIA_ROOT)
    if media_root.exists():
        for file in sorted(media_root.rglob("*")):
            if file.is_file():
                archive.write(file, f"dateien/{file.relative_to(media_root)}")

    from fundus.transfer.exporter import write_export

    export = io.BytesIO()
    write_export(export)
    archive.writestr("export.zip", export.getvalue())


def create_backup(now=None):
    """Legt eine Sicherung an und löscht überzählige alte. Gibt den Pfad zurück."""
    now = now or timezone.now()
    config = SchoolSettings.current()
    target = backup_dir() / f"{PREFIX}{timezone.localtime(now):%Y-%m-%d-%H%M%S}.zip"
    partial = target.with_suffix(".zip.part")
    try:
        with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            _write_backup(archive, now)
        partial.replace(target)
    except Exception as error:
        partial.unlink(missing_ok=True)
        logger.exception("Sicherung fehlgeschlagen")
        SchoolSettings.objects.filter(pk=config.pk).update(last_backup_error=str(error)[:2000])
        raise BackupError(str(error)) from error
    SchoolSettings.objects.filter(pk=config.pk).update(last_backup_at=now, last_backup_error="")
    prune(config.backup_keep)
    return target


def prune(keep):
    removed = []
    for old in existing_backups()[keep:]:
        old.unlink()
        removed.append(old)
    return removed


def is_due(now=None, config=None):
    now = now or timezone.now()
    config = config or SchoolSettings.current()
    days = INTERVAL_DAYS.get(config.backup_interval)
    if days is None:
        return False
    if config.last_backup_at is None:
        return True
    # Etwas Spielraum, damit die tägliche Sicherung nicht wegen Minuten ausfällt.
    return now - config.last_backup_at >= datetime.timedelta(days=days, hours=-6)


def is_overdue(now=None, config=None):
    """Für die Warnung in den Einstellungen: deutlich älter als geplant?"""
    now = now or timezone.now()
    config = config or SchoolSettings.current()
    days = INTERVAL_DAYS.get(config.backup_interval)
    if days is None:
        return False
    if config.last_backup_at is None:
        return True
    return now - config.last_backup_at > datetime.timedelta(days=days + 1)


def run(now=None):
    """Teil der täglichen Aufgaben: sichert, wenn es laut Zeitplan fällig ist."""
    if not is_due(now):
        return {"sicherung": 0}
    try:
        create_backup(now)
    except BackupError:
        return {"sicherung_fehlgeschlagen": 1}
    return {"sicherung": 1}


# Wiederherstellung


def read_version(path):
    with zipfile.ZipFile(path) as archive:
        return json.loads(archive.read("version.json"))


def database_is_empty():
    from fundus.accounts.models import User
    from fundus.catalog.models import Title

    return not User.objects.exists() and not Title.objects.exists()


def restore(path, replace=False):
    """Spielt eine Sicherung in die (bereits migrierte) Datenbank ein.

    Ohne `replace` nur in eine leere Datenbank; mit `replace` werden alle
    vorhandenen Daten vorher gelöscht."""
    path = Path(path)
    if not zipfile.is_zipfile(path):
        raise BackupError(f"{path} ist keine Fundus-Sicherung.")
    version = read_version(path)
    missing = sorted(set(version["migrationen"]) - set(applied_migrations()))
    if missing:
        raise BackupError(
            "Die Sicherung stammt aus einer neueren Fundus-Version. Bitte erst Fundus "
            f"aktualisieren. Fehlende Migrationen: {', '.join(missing[:5])}"
        )
    if not database_is_empty() and not replace:
        raise BackupError(
            "Die Datenbank enthält schon Daten. Zum Überschreiben --ersetzen angeben."
        )

    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(path) as archive:
            archive.extractall(tmp)
        with transaction.atomic():
            call_command("flush", interactive=False, verbosity=0)
            # flush legt Inhaltstypen und Berechtigungen neu an; die aus der
            # Sicherung bringen ihre eigenen Nummern mit.
            Permission.objects.all().delete()
            ContentType.objects.all().delete()
            call_command("loaddata", str(Path(tmp) / "datenbank.json"), verbosity=0)
        files = Path(tmp) / "dateien"
        if files.exists():
            shutil.copytree(files, settings.MEDIA_ROOT, dirs_exist_ok=True)
    return version
