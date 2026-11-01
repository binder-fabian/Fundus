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
