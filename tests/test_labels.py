import base64
import re
import zlib

import pytest
from django.urls import reverse
from reportlab.lib.units import mm

from fundus.accounts.models import Role
from fundus.catalog import labels
from fundus.catalog.models import Copy
from tests.factories import CategoryFactory, CopyFactory, TitleFactory, UserFactory

pytestmark = pytest.mark.django_db


def page_count(pdf):
    return len(re.findall(rb"/Type /Page\b(?!s)", pdf))


def pdf_text(pdf):
    """Entpackt die Seiteninhalte (ReportLab: ASCII85 + Flate) für Textvergleiche."""
    chunks = []
    for raw in re.findall(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        try:
            chunks.append(zlib.decompress(base64.a85decode(raw.strip(), adobe=True)))
        except ValueError:
            chunks.append(raw)
    return b"\n".join(chunks)


@pytest.mark.parametrize("fmt", labels.FORMATS.values(), ids=lambda f: f.code)
def test_formats_fit_on_a4(fmt):
    assert fmt.left + (fmt.columns - 1) * fmt.pitch_x + fmt.width <= 210.5
    assert fmt.top + (fmt.rows - 1) * fmt.pitch_y + fmt.height <= 297.5
    assert fmt.pitch_x >= fmt.width and fmt.pitch_y >= fmt.height


def test_positions_start_top_left_row_by_row():
    fmt = labels.FORMATS["3474"]
    positions = list(labels._positions(fmt, 0, 0))
    assert len(positions) == 24
    (x1, y1), (x2, y2), (_x4, y4) = positions[0], positions[1], positions[3]
    assert round(x1 / mm, 1) == 0.0 and round(x2 / mm, 1) == 70.0
    assert y1 == y2 and y4 < y1  # vierte Etikette: zweite Zeile, weiter unten


def test_offset_moves_labels():
    fmt = labels.FORMATS["4780"]
    (x0, y0) = next(labels._positions(fmt, 0, 0))
    (x1, y1) = next(labels._positions(fmt, 1.5, 2))
    assert round((x1 - x0) / mm, 2) == 1.5
    assert round((y0 - y1) / mm, 2) == 2.0


def test_labels_pdf_contains_numbers_and_breaks_pages():
    title = TitleFactory(
        title="Ein sehr langer Titel für ein ganz kleines Etikett mit Umlauten äöü"
    )
    copies = [CopyFactory(title=title, inventory_number=f"FS-{i:04d}") for i in range(1, 84)]
    pdf = labels.labels_pdf(copies, labels.FORMATS["4732"], start=1)
    assert pdf.startswith(b"%PDF")
    assert b"(FS-0001)" in pdf_text(pdf) and b"(FS-0083)" in pdf_text(pdf)
    assert page_count(pdf) == 2  # 80 je Blatt


def test_start_position_uses_partial_sheet():
    copies = [CopyFactory(inventory_number=f"X-{i}") for i in range(3)]
    pdf = labels.labels_pdf(copies, labels.FORMATS["3474"], start=23)
    assert page_count(pdf) == 2  # Etikett 23 und 24 auf Blatt 1, das dritte auf Blatt 2


def test_label_page_flow(client):
    client.force_login(UserFactory(role=Role.MANAGER))
    category = CategoryFactory()
    printed = CopyFactory(inventory_number="A-1", title__category=category)
    printed.label_printed_at = "2026-01-01T00:00:00Z"
    printed.save()
    CopyFactory(inventory_number="A-2", title__category=category)
    CopyFactory(inventory_number="A-3")

    page = client.get(reverse("labels") + "?auswahl=neu&action=show").content.decode()
    assert "<strong>2</strong> Etiketten" in page

    base = {"auswahl": "neu", "format": "4780", "start": "1"}
    pdf = client.post(reverse("labels"), {**base, "action": "pdf"})
    assert pdf["Content-Type"] == "application/pdf"
    assert b"(A-2)" in pdf_text(pdf.content) and b"(A-1)" not in pdf_text(pdf.content)

    client.post(reverse("labels"), {**base, "action": "mark"})
    assert not Copy.objects.filter(label_printed_at__isnull=True).exists()

    by_category = client.post(
        reverse("labels"),
        {**base, "auswahl": "kategorie", "kategorie": category.pk, "action": "pdf"},
    )
    text = pdf_text(by_category.content)
    assert b"(A-1)" in text and b"(A-3)" not in text


def test_single_copy_and_test_page(client):
    client.force_login(UserFactory(role=Role.MANAGER))
    copy = CopyFactory(inventory_number="Z-9")
    single = client.post(
        reverse("labels"),
        {
            "auswahl": "exemplar",
            "exemplar": [copy.pk],
            "format": "3474",
            "start": "1",
            "action": "pdf",
        },
    )
    assert b"(Z-9)" in pdf_text(single.content)
    test = client.post(
        reverse("labels"), {"auswahl": "alle", "format": "3474", "start": "1", "action": "test"}
    )
    assert b"Testseite" in pdf_text(test.content)


def test_start_beyond_sheet_is_rejected(client):
    client.force_login(UserFactory(role=Role.MANAGER))
    response = client.post(
        reverse("labels"), {"auswahl": "alle", "format": "3474", "start": "30", "action": "pdf"}
    )
    assert "nur 24 Etiketten" in response.content.decode()


def test_poster_contains_site_url(client, settings):
    settings.SITE_URL = "https://fundus.meine-schule.de"
    client.force_login(UserFactory(role=Role.MANAGER))
    response = client.get(reverse("poster"))
    assert response["Content-Type"] == "application/pdf"
    assert b"https://fundus.meine-schule.de" in pdf_text(response.content)


def test_labels_for_managers_only(client):
    client.force_login(UserFactory(role=Role.TEACHER))
    assert client.get(reverse("labels")).status_code == 403
    assert client.get(reverse("poster")).status_code == 403
