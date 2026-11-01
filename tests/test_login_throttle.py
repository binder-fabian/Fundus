import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from fundus.accounts.models import FailedLogin
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def attempt(client, password, email="anna@schule.de", ip="10.0.0.1"):
    return client.post(reverse("login"), {"username": email, "password": password}, REMOTE_ADDR=ip)


def test_lock_after_five_wrong_passwords(client, settings):
    settings.LOGIN_MAX_ATTEMPTS = 5
    UserFactory(email="anna@schule.de")
    for _ in range(5):
        assert "stimmen nicht" in attempt(client, "falsch").content.decode()
    response = attempt(client, "geheim-1234")  # jetzt auch mit richtigem Passwort gesperrt
    assert "Zu viele falsche Versuche" in response.content.decode()
    assert client.get(reverse("title_list")).status_code == 302


def test_lock_expires(client, settings):
    settings.LOGIN_MAX_ATTEMPTS = 2
    settings.LOGIN_LOCK_MINUTES = 15
    UserFactory(email="anna@schule.de")
    attempt(client, "x")
    attempt(client, "x")
    FailedLogin.objects.update(at=timezone.now() - datetime.timedelta(minutes=16))
    assert attempt(client, "geheim-1234").status_code == 302


def test_success_clears_failures(client, settings):
    settings.LOGIN_MAX_ATTEMPTS = 3
    UserFactory(email="anna@schule.de")
    attempt(client, "x")
    attempt(client, "x")
    assert attempt(client, "geheim-1234").status_code == 302
    assert not FailedLogin.objects.filter(username="anna@schule.de").exists()


def test_case_of_email_does_not_bypass_lock(client, settings):
    settings.LOGIN_MAX_ATTEMPTS = 2
    UserFactory(email="anna@schule.de")
    attempt(client, "x", email="ANNA@schule.de", ip="10.0.0.1")
    attempt(client, "x", email="Anna@Schule.de", ip="10.0.0.2")
    response = attempt(client, "geheim-1234", ip="10.0.0.3")
    assert "Zu viele falsche Versuche" in response.content.decode()


def test_many_failures_from_one_device_lock_that_device(client, settings):
    settings.LOGIN_MAX_ATTEMPTS = 2
    UserFactory(email="anna@schule.de")
    for i in range(8):
        attempt(client, "x", email=f"raten{i}@schule.de", ip="10.0.0.9")
    assert "Zu viele" in attempt(client, "geheim-1234", ip="10.0.0.9").content.decode()
    assert attempt(client, "geheim-1234", ip="10.0.0.10").status_code == 302


def test_forwarded_ip_only_trusted_behind_proxy(rf, settings):
    from fundus.accounts.throttle import client_ip

    request = rf.get("/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="203.0.113.5, 10.0.0.1")
    settings.BEHIND_HTTPS_PROXY = False
    assert client_ip(request) == "10.0.0.1"
    settings.BEHIND_HTTPS_PROXY = True
    assert client_ip(request) == "203.0.113.5"


def test_old_entries_are_removed(client):
    old = FailedLogin.objects.create(username="alt@schule.de")
    FailedLogin.objects.filter(pk=old.pk).update(at=timezone.now() - datetime.timedelta(days=2))
    attempt(client, "x")
    assert not FailedLogin.objects.filter(pk=old.pk).exists()
