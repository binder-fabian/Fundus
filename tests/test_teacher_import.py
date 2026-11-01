import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from fundus.accounts import teacher_import
from fundus.accounts.models import Role, User
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_parse_semicolon_file_with_header_from_excel():
    UserFactory(email="vorhanden@schule.de")
    data = (
        "Nachname;Vorname;E-Mail\r\n"
        "Müller;Anna;Anna.Mueller@schule.de\r\n"
        "Schmidt;Bert;vorhanden@schule.de\r\n"
        "Klein;Carla;keine-adresse\r\n"
        "Müller;Anna;anna.mueller@schule.de\r\n"
        ";;\r\n"
    ).encode("cp1252")
    rows = teacher_import.parse(data)
    assert [(r.line, r.status) for r in rows] == [
        (2, teacher_import.NEW),
        (3, teacher_import.EXISTS),
        (4, teacher_import.INVALID),
        (5, teacher_import.DUPLICATE),
    ]
    assert rows[0].first_name == "Anna"
    assert rows[0].last_name == "Müller"
    assert rows[0].email == "anna.mueller@schule.de"


def test_parse_comma_file_without_header():
    rows = teacher_import.parse(
        "Anna,Müller,anna@schule.de\nBert,Schmidt,bert@schule.de\n".encode()
    )
    assert [r.email for r in rows] == ["anna@schule.de", "bert@schule.de"]
    assert all(r.status == teacher_import.NEW for r in rows)


def test_parse_utf8_with_bom():
    rows = teacher_import.parse("﻿Vorname;Nachname;Email\nJürgen;Groß;j@schule.de\n".encode())
    assert rows[0].first_name == "Jürgen"
    assert rows[0].last_name == "Groß"


def test_import_flow_creates_teachers_and_sends_invitations(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    upload = SimpleUploadedFile(
        "kollegium.csv",
        "Vorname;Nachname;E-Mail\nAnna;Müller;anna@schule.de\nBert;Schmidt;bert@schule.de\n".encode(),
    )
    response = client.post(reverse("teacher_import"), {"file": upload})
    assert "2 Lehrkräfte anlegen" in response.content.decode()
    assert not User.objects.filter(email="anna@schule.de").exists()

    response = client.post(reverse("teacher_import_confirm"), {"send_invitations": "1"})
    assert response.status_code == 302
    created = User.objects.filter(email__in=["anna@schule.de", "bert@schule.de"])
    assert created.count() == 2
    assert all(u.role == Role.TEACHER and u.invitation_pending for u in created)
    assert len(mail.outbox) == 2

    # Ein zweites Bestätigen ohne neue Vorschau legt nichts doppelt an.
    client.post(reverse("teacher_import_confirm"), {"send_invitations": "1"})
    assert User.objects.filter(email="anna@schule.de").count() == 1
