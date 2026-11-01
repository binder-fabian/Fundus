"""Sperre nach zu vielen falschen Passwörtern (je E-Mail-Adresse und je Gerät)."""

import datetime

from django.conf import settings
from django.utils import timezone

from fundus.accounts.models import FailedLogin


def client_ip(request):
    if request is None:
        return None
    if settings.BEHIND_HTTPS_PROXY:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _window_start():
    return timezone.now() - datetime.timedelta(minutes=settings.LOGIN_LOCK_MINUTES)


def is_locked(username, request):
    recent = FailedLogin.objects.filter(at__gte=_window_start())
    limit = settings.LOGIN_MAX_ATTEMPTS
    if recent.filter(username=(username or "").lower()).count() >= limit:
        return True
    ip = client_ip(request)
    # Je Gerät etwas großzügiger, weil sich z. B. ein ganzes Lehrerzimmer eine IP teilt.
    return bool(ip) and recent.filter(ip=ip).count() >= limit * 4


def record_failure(username, request):
    FailedLogin.objects.filter(at__lt=timezone.now() - datetime.timedelta(days=1)).delete()
    FailedLogin.objects.create(username=(username or "").lower()[:254], ip=client_ip(request))


def clear(username):
    FailedLogin.objects.filter(username=(username or "").lower()).delete()
