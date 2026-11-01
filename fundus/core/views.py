from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views.decorators.cache import never_cache
from django.views.static import serve


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
