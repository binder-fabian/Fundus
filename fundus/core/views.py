from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.views.static import serve

from fundus.accounts.permissions import require
from fundus.core import backup, privacy
from fundus.core.daily import describe
from fundus.core.forms import SchoolSettingsForm
from fundus.core.models import SchoolSettings


@login_not_required
@never_cache
def health(request):
    """Für Healthchecks von Container und Reverse Proxy: prüft die Datenbank."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        return JsonResponse({"status": "error", "database": "unreachable"}, status=503)
    return JsonResponse({"status": "ok"})


def media(request, path):
    """Liefert hochgeladene Dateien (Coverbilder) aus dem Datenverzeichnis aus.

    Für die erwarteten Datenmengen einer Schule reicht das; wer mag, lässt
    stattdessen den Reverse Proxy /media/ direkt ausliefern.
    """
    return serve(request, path, document_root=settings.MEDIA_ROOT)


@require("is_admin")
def school_settings(request):
    from fundus.catalog.models import Category
    from fundus.catalog.numbering import preview_next
    from fundus.supplies.services import order_handlers_configured

    form = SchoolSettingsForm(request.POST or None, instance=SchoolSettings.current())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Einstellungen gespeichert.")
        return redirect("school_settings")
    groups = [
        ("Schule", [form["school_name"]], ""),
        (
            "Nummernschema für neue Exemplare",
            [form["number_prefix"], form["number_digits"], form["next_number"]],
            "Nächste Nummer mit dem allgemeinen Präfix: "
            + preview_next()
            + "".join(
                f" · {c.name}: {preview_next(c)}"
                for c in Category.objects.exclude(number_prefix="")
            )
            + ". Eigene Präfixe je Kategorie unter Stammdaten → Kategorien.",
        ),
        ("Katalog", [form["outdated_norm_years"], form["isbn_lookup_enabled"]], ""),
        (
            "Erinnerungen per E-Mail",
            [
                form["reminders_enabled"],
                form["reminder_days_before"],
                form["overdue_notice_days"],
                form["escalate_days"],
            ],
            "Werden einmal täglich verschickt (Dienst „scheduler“).",
        ),
        (
            "Anfragen für freigabepflichtige Titel",
            [form["request_reminder_days"], form["request_pickup_days"]],
            "",
        ),
        (
            "Verbrauchsmaterial",
            [form["reorder_email"]],
            ""
            if order_handlers_configured()
            else "Achtung: Es gibt noch kein Konto mit der Rolle „Sekretariat“ und keine "
            "Adresse für Nachbestellungen. Hinweise gehen deshalb an die Verwaltung.",
        ),
        (
            "Datenschutz",
            [
                form["borrower_visibility"],
                form["anonymous_lending"],
                form["anonymize_after_days"],
                form["history_names_days"],
            ],
            privacy_note(form.instance),
        ),
        ("Sicherung", [form["backup_interval"], form["backup_keep"]], backup_note(form.instance)),
        ("Etikettendruck", [form["label_offset_x"], form["label_offset_y"]], ""),
    ]
    return render(request, "core/settings.html", {"form": form, "groups": groups})


def privacy_note(config):
    due = privacy.loans_due(config=config).count()
    last = config.last_privacy_run
    text = (
        f"Beim nächsten täglichen Lauf werden {due} Ausleihen anonymisiert. "
        if due
        else "Zurzeit ist keine Ausleihe zur Anonymisierung fällig. "
    )
    if last:
        text += f"Letzte Bereinigung: {timezone.localtime(last):%d.%m.%Y %H:%M}."
    else:
        text += "Bisher lief noch keine Bereinigung."
    return text


@require("is_admin")
@require_POST
def privacy_run_now(request):
    counts = privacy.run()
    messages.success(request, "Bereinigung erledigt. " + describe(counts) + ".")
    return redirect("school_settings")


def backup_note(config):
    files = backup.existing_backups()
    text = f"Ablage: {settings.BACKUP_DIR} ({len(files)} Sicherungen vorhanden). "
    if config.last_backup_at:
        text += f"Letzte Sicherung: {timezone.localtime(config.last_backup_at):%d.%m.%Y %H:%M}. "
    if config.last_backup_error:
        text += f"Achtung: Die letzte Sicherung ist fehlgeschlagen ({config.last_backup_error}). "
    elif backup.is_overdue(config=config):
        text += "Achtung: Es gibt keine aktuelle Sicherung. "
    text += (
        "Die Dateien enthalten alle Daten einschließlich der Passwort-Prüfwerte. "
        "Bitte zusätzlich außerhalb des Servers aufbewahren, z. B. auf einem NAS."
    )
    return text


@require("is_admin")
@require_POST
def backup_now(request):
    try:
        path = backup.create_backup()
    except backup.BackupError as error:
        messages.error(request, f"Sicherung fehlgeschlagen: {error}")
    else:
        messages.success(request, f"Sicherung angelegt: {path.name}")
    return redirect("school_settings")
