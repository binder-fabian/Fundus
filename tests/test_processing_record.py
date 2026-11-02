import io

import pytest
from django.urls import reverse
from docx import Document
from docx.enum.text import WD_COLOR_INDEX

from fundus.accounts.models import Role
from fundus.core.models import SchoolSettings
from fundus.core.processing_record import processing_record_docx
from tests.factories import UserFactory
from tests.test_settings_numbering import settings_data

pytestmark = pytest.mark.django_db


def text_of(content):
    doc = Document(io.BytesIO(content))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        parts += [cell.text for row in table.rows for cell in row.cells]
    return "\n".join(parts), doc


def test_document_reflects_settings():
    config = SchoolSettings.current()
    text, doc = text_of(processing_record_docx(config))
    assert "Kurzbeschreibung der Verarbeitung" in text
    assert "nach 1 Jahr automatisch entfernt" in text
    assert "nur die Verwaltung und das für den Titel zuständige Team" in text
    assert "Täglich; die letzten 14 werden aufbewahrt (etwa 14 Tage)" in text
    assert "keine Daten von Schülerinnen und Schülern" in text
    assert "an die Deutsche Nationalbibliothek und Open Library" in text
    assert "Google Books" not in text
    highlighted = [
        run.text
        for p in doc.paragraphs
        for run in p.runs
        if run.font.highlight_color == WD_COLOR_INDEX.YELLOW
    ]
    assert any("Datenschutzgesetz des Landes" in t for t in highlighted)

    config.anonymous_lending = True
    config.borrower_visibility = config.Visibility.ALL
    config.anonymize_after_days = 90
    config.isbn_lookup_enabled = False
    config.save()
    text, _doc = text_of(processing_record_docx(config))
    assert "ohne Namen erfasst, nur mit Klasse oder Raum" in text
    assert "sehen alle angemeldeten Lehrkräfte" in text
    assert "nach 90 Tagen automatisch entfernt" in text
    assert "ISBN-Abruf bei externen Diensten ist abgeschaltet" in text


def test_download_admin_only_and_hint_after_change(client):
    client.force_login(UserFactory(role=Role.MANAGER))
    assert client.get(reverse("processing_record")).status_code == 403

    client.force_login(UserFactory(role=Role.ADMIN))
    response = client.get(reverse("processing_record"))
    assert response["Content-Type"].endswith("wordprocessingml.document")
    assert "verarbeitungsbeschreibung" in response["Content-Disposition"]
    assert reverse("processing_record") in client.get(reverse("school_settings")).content.decode()

    page = client.post(
        reverse("school_settings"), settings_data(anonymize_after_days="200"), follow=True
    ).content.decode()
    assert "Verarbeitungsbeschreibung neu herunterladen" in page
    page = client.post(
        reverse("school_settings"), settings_data(outdated_norm_years="9"), follow=True
    ).content.decode()
    assert "Verarbeitungsbeschreibung neu herunterladen" not in page


def test_document_names_login_services(settings):
    settings.OIDC_RP_CLIENT_ID = "fundus"
    settings.OIDC_ISSUER = "https://login.example.org/schule"
    settings.LDAP_SERVER_URI = "ldaps://schulserver.local"
    config = SchoolSettings.current()
    config.password_login = config.PasswordLogin.ADMINS
    config.save()
    text, _doc = text_of(processing_record_docx(config))
    assert "Anmeldung mit Schulkonto über login.example.org" in text
    assert "Schulserver schulserver.local (LDAP, verschlüsselt)" in text
    assert "nur für Administratoren (Notzugang)" in text
    assert "Reservierungen" in text


def test_document_without_login_services():
    text, _doc = text_of(processing_record_docx(SchoolSettings.current()))
    assert "Anmeldung mit Schulkonto über" not in text
    assert "Notzugang" not in text
