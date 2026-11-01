import csv
import io
import json
import zipfile

import pytest
from django.core.management import call_command
from django.urls import reverse

from fundus.accounts.models import Role
from fundus.catalog.models import Copy, SupportFocus, Title
from fundus.loans.models import Loan
from fundus.transfer import importer
from fundus.transfer.exporter import write_export
from tests.factories import (
    CategoryFactory,
    CopyFactory,
    LoanFactory,
    LocationFactory,
    TitleFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


def build_catalog():
    tests = CategoryFactory(name="Diagnostik")
    room = LocationFactory(room="Raum 104", shelf="R2")
    elfe = TitleFactory(
        title="ELFE II",
        author="Lenhard",
        isbn="9783161484100",
        category=tests,
        norm_year=2017,
        contents="Manual\nTestheft",
        lendable=True,
    )
    elfe.support_focuses.add(SupportFocus.objects.get(name="Lernen"))
    CopyFactory(title=elfe, inventory_number="FS-1", location=room, note="Ecke geknickt")
    CopyFactory(title=elfe, inventory_number="FS-2", location=room)
    CopyFactory(
        title=TitleFactory(title="Bildkarten", category=tests, lendable=False),
        inventory_number="FS-3",
        location=None,
    )
    LoanFactory(copy=Copy.objects.get(inventory_number="FS-1"))


def export_zip():
    buffer = io.BytesIO()
    write_export(buffer)
    buffer.seek(0)
    return zipfile.ZipFile(buffer)


def read_csv(archive, name):
    text = archive.read(name).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text), delimiter=";"))


def test_export_contains_all_tables_without_passwords():
    build_catalog()
    archive = export_zip()
    names = set(archive.namelist())
    for table in ("titel", "exemplare", "ausleihen", "benutzer", "kategorien", "standorte"):
        assert f"csv/{table}.csv" in names
    assert "csv/protokoll_titel.csv" in names
    assert {"katalog.csv", "fundus.json", "LIESMICH.txt"} <= names

    users = read_csv(archive, "csv/benutzer.csv")
    assert users and "password" not in users[0]
    assert "email" in users[0]
    assert "search_text" not in read_csv(archive, "csv/titel.csv")[0]

    data = json.loads(archive.read("fundus.json"))
    assert data["meta"]["fundus_export_version"] == 1
    assert len(data["tables"]["exemplare"]) == 3
    assert len(data["tables"]["ausleihen"]) == 1
    assert all("password" not in u for u in data["tables"]["benutzer"])


def test_catalog_csv_round_trip_through_import():
    build_catalog()
    archive = export_zip()
    catalog = archive.read("katalog.csv")
    before = sorted(
        Copy.objects.values_list(
            "inventory_number",
            "title__title",
            "title__isbn",
            "title__norm_year",
            "title__contents",
            "title__lendable",
            "location__room",
            "location__shelf",
            "note",
        )
    )

    # Ausleihen schützen Exemplare vor dem Löschen, daher zuerst entfernen.
    Loan.objects.all().delete()
    Copy.objects.all().delete()
    Title.objects.all().delete()

    header, rows = importer.read_table("katalog.csv", catalog)
    mapping = importer.guess_mapping(header)
    results = importer.analyze(rows, mapping, importer.Options())
    assert all(r.ok for r in results), [r.errors for r in results]
    importer.run_import(results, importer.Options())

    after = sorted(
        Copy.objects.values_list(
            "inventory_number",
            "title__title",
            "title__isbn",
            "title__norm_year",
            "title__contents",
            "title__lendable",
            "location__room",
            "location__shelf",
            "note",
        )
    )
    assert after == before
    assert Title.objects.count() == 2
    elfe = Title.objects.get(title="ELFE II")
    assert [f.name for f in elfe.support_focuses.all()] == ["Lernen"]


def test_export_command_writes_zip(tmp_path):
    build_catalog()
    call_command("export_all", output=str(tmp_path))
    files = list(tmp_path.glob("fundus-export-*.zip"))
    assert len(files) == 1
    assert "katalog.csv" in zipfile.ZipFile(files[0]).namelist()


def test_export_download_is_admin_only(client):
    build_catalog()
    client.force_login(UserFactory(role=Role.MANAGER))
    assert client.post(reverse("export_page")).status_code == 403

    client.force_login(UserFactory(role=Role.ADMIN))
    response = client.post(reverse("export_page"))
    assert response.status_code == 200
    assert response["Content-Disposition"].startswith('attachment; filename="fundus-export-')
    archive = zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content)))
    assert "katalog.csv" in archive.namelist()
