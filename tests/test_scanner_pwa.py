import json

import pytest
from django.urls import reverse

from fundus.accounts.models import Role
from fundus.catalog.models import IsbnLookupCache
from fundus.supplies.models import Consumable
from tests.factories import CopyFactory, TitleFactory, UserFactory

pytestmark = pytest.mark.django_db


def test_scanner_page_uses_local_library(client):
    client.force_login(UserFactory())
    page = client.get(reverse("scanner")).content.decode()
    assert 'data-mode="exemplar"' in page
    assert 'data-target="/s/__CODE__"' in page
    assert "barcode-detector-3.2.2.ponyfill.js" in page
    assert "zxing-wasm-3.1.3-reader.wasm" in page
    assert "http://" not in page.split("<body>")[1].replace("http://localhost", "")
    assert "https://" not in page


def test_isbn_mode_returns_to_local_form_only(client):
    client.force_login(UserFactory(role=Role.MANAGER))
    page = client.get(reverse("scanner"), {"ziel": "isbn", "zurueck": "/katalog/neu/"})
    assert 'data-target="/katalog/neu/?isbn=__CODE__"' in page.content.decode()
    evil = client.get(reverse("scanner"), {"ziel": "isbn", "zurueck": "//boese.example/"})
    assert "boese" not in evil.content.decode()


def test_title_create_with_scanned_isbn_prefills(client):
    client.force_login(UserFactory(role=Role.MANAGER))
    IsbnLookupCache.objects.create(
        isbn="9783423214124",
        result={"data": {"title": "Der kleine Hobbit"}, "sources": ["DNB"], "cover_url": ""},
        fetched_at="2099-01-01T00:00:00Z",
    )
    page = client.get(reverse("title_create"), {"isbn": "9783423214124"}).content.decode()
    assert 'value="Der kleine Hobbit"' in page
    assert "ISBN mit Kamera scannen" in page


def test_manifest_and_service_worker_are_public(client):
    manifest = client.get(reverse("manifest"))
    assert manifest["Content-Type"] == "application/manifest+json"
    data = json.loads(manifest.content)
    assert data["display"] == "standalone" and data["lang"] == "de"
    assert any(i.get("purpose") == "maskable" for i in data["icons"])

    worker = client.get("/sw.js")
    assert worker.status_code == 200
    assert worker["Service-Worker-Allowed"] == "/"
    assert "/offline/" in worker.content.decode()
    assert client.get(reverse("offline")).status_code == 200


def test_tabbar_for_logged_in_users(client):
    client.force_login(UserFactory())
    page = client.get(reverse("home")).content.decode()
    assert 'class="tabbar"' in page and 'rel="manifest"' in page


def test_scan_box_suggests_copies_and_supplies_while_typing(client):
    client.force_login(UserFactory())
    title = TitleFactory(title="Rechentest für Klasse 3")
    CopyFactory(title=title, inventory_number="FS-0003")
    CopyFactory(inventory_number="FS-0100")
    Consumable.objects.create(name="Protokollbögen Rechentest", code="NB-0001")
    url = reverse("scan_suggestions")

    page = client.get(url, {"nummer": "0003"}).content.decode()
    assert "FS-0003" in page and "FS-0100" not in page

    page = client.get(url, {"nummer": "rechen"}).content.decode()
    assert "FS-0003" in page and "NB-0001" in page and "FS-0100" not in page

    assert client.get(url, {"nummer": "f"}).content.decode().strip() == ""
    home = client.get(reverse("home")).content.decode()
    assert 'hx-get="' + url + '"' in home
