from unittest import mock

from django.db import DatabaseError


def test_health_ok(client, db):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_reports_database_error(client, db):
    with mock.patch("fundus.core.views.connection.cursor", side_effect=DatabaseError):
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "error"


def test_home_leads_to_catalog_in_german(client, db):
    from tests.factories import UserFactory

    client.force_login(UserFactory())
    response = client.get("/", follow=True)
    assert response.redirect_chain[-1][0] == "/katalog/"
    content = response.content.decode()
    assert '<html lang="de">' in content
    assert "Katalog" in content


def test_stylesheet_is_found_by_collectstatic():
    from django.contrib.staticfiles import finders

    assert finders.find("fundus/fundus.css")


def test_health_answers_for_hosts_outside_allowed_hosts(client, db, settings):
    settings.ALLOWED_HOSTS = ["fundus.meine-schule.de"]
    assert client.get("/health", HTTP_HOST="127.0.0.1:8000").status_code == 200
    assert client.get("/anmelden/", HTTP_HOST="127.0.0.1:8000").status_code == 400
