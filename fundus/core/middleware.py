from django.utils.cache import patch_vary_headers

from fundus.core.views import health


class HealthCheckMiddleware:
    """Beantwortet /health vor der Prüfung von ALLOWED_HOSTS.

    Healthchecks von Container und Orchestrierung rufen Fundus über 127.0.0.1
    oder eine interne Adresse auf, die nicht in ALLOWED_HOSTS steht.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/health":
            return health(request)
        return self.get_response(request)


class HtmxMiddleware:
    """Setzt `request.htmx`, wenn die Anfrage von htmx kommt (Teilseite nachladen)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.htmx = request.headers.get("HX-Request") == "true"
        response = self.get_response(request)
        patch_vary_headers(response, ["HX-Request"])
        return response
