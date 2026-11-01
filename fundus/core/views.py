from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.static import serve

from fundus.accounts.permissions import require
from fundus.core.forms import SchoolSettingsForm
from fundus.core.models import SchoolSettings


def home(request):
    # Vorerst ist der Katalog die Startseite; ab Phase 3 kommt hier der Scanner hin.
    return redirect("title_list")


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
    from fundus.catalog.numbering import preview_next

    form = SchoolSettingsForm(request.POST or None, instance=SchoolSettings.current())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Einstellungen gespeichert.")
        return redirect("school_settings")
    groups = [
        (
            "Nummernschema für neue Exemplare",
            [form["number_prefix"], form["number_digits"], form["next_number"]],
            f"Nächste vergebene Nummer: {preview_next()}",
        ),
        ("Katalog", [form["outdated_norm_years"], form["isbn_lookup_enabled"]], ""),
        ("Etikettendruck", [form["label_offset_x"], form["label_offset_y"]], ""),
    ]
    return render(request, "core/settings.html", {"form": form, "groups": groups})
