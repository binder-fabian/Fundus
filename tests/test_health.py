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


def test_home_renders_in_german(client, db):
    response = client.get("/")
    assert response.status_code == 200
    assert "Willkommen bei Fundus" in response.content.decode()


def test_stylesheet_is_found_by_collectstatic():
    from django.contrib.staticfiles import finders

    assert finders.find("fundus/fundus.css")
