from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache


def home(request):
    return render(request, "core/home.html")


@never_cache
def health(request):
    """Für Healthchecks von Container und Reverse Proxy: prüft die Datenbank."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        return JsonResponse({"status": "error", "database": "unreachable"}, status=503)
    return JsonResponse({"status": "ok"})
