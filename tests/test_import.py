import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook

from fundus.accounts.models import Role
from fundus.catalog.models import Category, Copy, Location, Title
from fundus.transfer import importer
from fundus.transfer.models import ImportTemplate
from tests.factories import CategoryFactory, CopyFactory, TitleFactory, UserFactory

pytestmark = pytest.mark.django_db

MS_LIST_CSV = (
    "Title;Inventarnummer;Autor;ISBN;Kategorie;Standort;Regal;Normjahr;Ausleihbar\r\n"
    "ELFE II;FS-0001;Lenhard;978-3-16-148410-0;Diagnostik/Tests;Raum 104;R1;2017;ja\r\n"
    "ELFE II;FS-0002;Lenhard;9783161484100;Diagnostik/Tests;Raum 104;R1;2017;ja\r\n"
    "Bildkarten Tiere;FS-0003;;;Spiele;Raum 9;;;nein\r\n"
    "Ohne Nummer;;;;Bücher;;;;\r\n"
    "Doppelt;FS-0001;;;Bücher;;;;\r\n"
    "Kaputte ISBN;FS-0004;;12345;Bücher;;;20xx;\r\n"
).encode("cp1252")


def table(data=MS_LIST_CSV, name="liste.csv"):
    return importer.read_table(name, data)


def test_read_csv_and_guess_mapping():
    header, rows = table()
    assert header[0] == "Title"
    assert len(rows) == 6
    mapping = importer.guess_mapping(header)
    assert mapping["title"] == 0
    assert mapping["inventory_number"] == 1
    assert mapping["room"] == 5 and mapping["shelf"] == 6
    assert mapping["lendable"] == 8


def test_read_xlsx_converts_numbers():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Titel", "Inventarnummer", "ISBN", "Normjahr"])
    sheet.append(["Buch", 1001, 9783161484100, 2015.0])
    buffer = io.BytesIO()
    workbook.save(buffer)
    header, rows = importer.read_table("bestand.xlsx", buffer.getvalue())
    assert header == ["Titel", "Inventarnummer", "ISBN", "Normjahr"]
    assert rows == [["Buch", "1001", "9783161484100", "2015"]]


def test_rejects_unknown_file_type():
    with pytest.raises(importer.ImportFileError):
        importer.read_table("bestand.pdf", b"%PDF")


def test_analyze_reports_problems_and_merges_titles():
    header, rows = table()
    results = importer.analyze(rows, importer.guess_mapping(header), importer.Options())
    by_line = {r.line: r for r in results}
    assert by_line[2].ok and by_line[3].ok
    assert by_line[3].first_line_of_title == 2  # gleiche ISBN, anders geschrieben
    assert "Inventarnummer fehlt" in map(str, by_line[5].errors)
    assert any("doppelt" in str(e) for e in by_line[6].errors)
    assert any("ISBN ungültig" in str(w) for w in by_line[7].warnings)
    assert any("Normjahr" in str(w) for w in by_line[7].warnings)
    assert any("Spiele" in str(w) for w in by_line[4].warnings)
    summary = importer.summarize(results)
    assert summary == {
        "rows": 6,
        "copies": 4,
        "new_titles": 3,
        "existing_titles": 0,
        "errors": 2,
    }


def test_run_import_creates_titles_copies_and_masterdata():
    header, rows = table()
    options = importer.Options()
    results = importer.analyze(rows, importer.guess_mapping(header), options)
    counts = importer.run_import(results, options)
    assert counts == {"copies": 4, "titles": 3}

    elfe = Title.objects.get(title="ELFE II")
    assert elfe.isbn == "9783161484100"
    assert elfe.norm_year == 2017 and elfe.lendable
    assert list(elfe.copies.values_list("inventory_number", flat=True)) == ["FS-0001", "FS-0002"]
    assert elfe.copies.first().location == Location.objects.get(room="Raum 104", shelf="R1")
    assert Category.objects.filter(name="Spiele").exists()
    assert not Title.objects.get(title="Bildkarten Tiere").lendable
    assert Title.objects.get(title="Kaputte ISBN").isbn == ""
    assert elfe.history.first().history_change_reason == "Import"


def test_existing_title_and_numbers_are_respected():
    TitleFactory(title="ELFE II", isbn="9783161484100")
    CopyFactory(inventory_number="fs-0003")
    header, rows = table()
    options = importer.Options()
    results = importer.analyze(rows, importer.guess_mapping(header), options)
    by_line = {r.line: r for r in results}
    assert by_line[2].existing_title_id
    assert "schon im Katalog" in str(by_line[4].errors[0])
    importer.run_import(results, options)
    assert Title.objects.filter(title="ELFE II").count() == 1


def test_missing_category_needs_default_or_creation():
    header, rows = importer.read_table("a.csv", b"Titel;Inventarnummer\nBuch;A-1\n")
    mapping = importer.guess_mapping(header)
    results = importer.analyze(rows, mapping, importer.Options())
    assert "Kategorie fehlt" in str(results[0].errors[0])
    default = CategoryFactory()
    results = importer.analyze(rows, mapping, importer.Options(default_category=default))
    assert results[0].ok


def test_report_lists_every_row():
    header, rows = table()
    results = importer.analyze(rows, importer.guess_mapping(header), importer.Options())
    report = importer.report_csv(results)
    assert report.startswith("﻿Zeile;")
    assert "übersprungen" in report and "importiert" in report


def test_import_is_admin_only(client):
    client.force_login(UserFactory(role=Role.MANAGER))
    assert client.get(reverse("import_upload")).status_code == 403


def test_wizard_end_to_end(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    upload = SimpleUploadedFile("liste.csv", MS_LIST_CSV)
    response = client.post(reverse("import_upload"), {"file": upload})
    assert response["Location"] == reverse("import_mapping")
    page = client.get(reverse("import_mapping")).content.decode()
    assert "6 Zeilen" in page

    header, _rows = table()
    mapping = {f"map_{k}": v for k, v in importer.guess_mapping(header).items()}
    response = client.post(
        reverse("import_mapping"),
        {**mapping, "create_missing": "1", "save_template": "Microsoft-List-Export"},
    )
    assert response["Location"] == reverse("import_preview")
    assert ImportTemplate.objects.get(name="Microsoft-List-Export").mapping["title"] == "Title"

    preview = client.get(reverse("import_preview")).content.decode()
    assert "4</strong> Exemplare" in preview
    assert Copy.objects.count() == 0

    done = client.post(reverse("import_confirm")).content.decode()
    assert "4 Exemplare zu 3 Titeln" in done
    assert Copy.objects.count() == 4
    report = client.get(reverse("import_report"))
    assert report["Content-Type"] == "text/csv"

    # Erneutes Bestätigen importiert nichts doppelt.
    client.post(reverse("import_confirm"))
    assert Copy.objects.count() == 4


def test_mapping_requires_title_and_number(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    client.post(reverse("import_upload"), {"file": SimpleUploadedFile("l.csv", MS_LIST_CSV)})
    response = client.post(reverse("import_mapping"), {"map_title": "0"}, follow=True)
    assert "Bitte Spalten zuordnen für: Inventarnummer" in response.content.decode()


def test_saved_template_is_applied_by_column_name(client):
    client.force_login(UserFactory(role=Role.ADMIN))
    template = ImportTemplate.objects.create(
        name="Alt", mapping={"title": "Title", "inventory_number": "Regal"}
    )
    client.post(reverse("import_upload"), {"file": SimpleUploadedFile("l.csv", MS_LIST_CSV)})
    client.post(reverse("import_mapping"), {"apply_template": template.pk})
    assert client.session["catalog_import"]["mapping"] == {"title": 0, "inventory_number": 6}
