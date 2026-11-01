import io
from pathlib import Path

import pytest
from django.urls import reverse
from PIL import Image

from fundus.accounts.models import Role
from fundus.catalog import isbn_lookup
from fundus.catalog.models import IsbnLookupCache, Title
from fundus.core.models import SchoolSettings
from tests.factories import CategoryFactory, UserFactory

pytestmark = pytest.mark.django_db

FIXTURES = Path(__file__).parent / "fixtures"
ISBN = "9783423214124"


def fake_internet(monkeypatch, responses):
    calls = []

    def fake_get(url, accept="application/json"):
        calls.append(url)
        for part, body in responses.items():
            if part in url:
                if isinstance(body, Exception):
                    raise body
                return body
        raise OSError("unerwartete URL " + url)

    monkeypatch.setattr(isbn_lookup, "_get", fake_get)
    return calls


def cover_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (400, 600), "blue").save(buffer, format="JPEG")
    return buffer.getvalue()


ALL_SOURCES = {
    "services.dnb.de": (FIXTURES / "dnb_9783423214124.xml").read_bytes(),
    "openlibrary.org/api": (FIXTURES / "openlibrary_9783423214124.json").read_bytes(),
}


def test_parse_dnb_marc_record():
    data = isbn_lookup.parse_dnb((FIXTURES / "dnb_9783423214124.xml").read_bytes())
    assert data["title"] == "Der kleine Hobbit"  # Steuerzeichen um „Der“ entfernt
    assert data["author"] == "Tolkien, J. R. R."
    assert data["publisher"] == "Dt. Taschenbuch-Verl."
    assert data["edition"] == "Neuausg."
    assert data["year"] == "2012"


def test_parse_dnb_without_hit():
    assert isbn_lookup.parse_dnb((FIXTURES / "dnb_empty.xml").read_bytes()) == {}


def test_parse_openlibrary():
    payload = (FIXTURES / "openlibrary_9783423214124.json").read_bytes()
    data, _cover = isbn_lookup.parse_openlibrary(payload, ISBN)
    assert data["title"] == "Der kleine Hobbit"
    assert data["author"] == "J.R.R. Tolkien"


def test_lookup_merges_sources_in_order_and_caches(monkeypatch):
    calls = fake_internet(monkeypatch, ALL_SOURCES)
    result = isbn_lookup.lookup("978-3-423-21412-4")
    assert result.found
    assert result.sources == ["DNB", "Open Library"]
    assert result.data["author"] == "Tolkien, J. R. R."  # DNB gewinnt
    assert len(calls) == 2

    again = isbn_lookup.lookup(ISBN)
    assert again.data == result.data
    assert len(calls) == 2  # aus dem Zwischenspeicher


def test_google_only_with_key(monkeypatch, settings):
    calls = fake_internet(monkeypatch, {**ALL_SOURCES, "googleapis.com": b'{"items": []}'})
    isbn_lookup.lookup(ISBN)
    assert not any("googleapis" in c for c in calls)
    settings.GOOGLE_BOOKS_API_KEY = "abc"
    IsbnLookupCache.objects.all().delete()
    isbn_lookup.lookup(ISBN)
    assert any("googleapis" in c and "key=abc" in c for c in calls)


def test_failed_source_is_not_cached(monkeypatch):
    fake_internet(
        monkeypatch,
        {"services.dnb.de": OSError("timeout"), "openlibrary.org/api": b"{}"},
    )
    result = isbn_lookup.lookup(ISBN)
    assert not result.found and result.failed == ["DNB"]
    assert not IsbnLookupCache.objects.exists()


def lookup_post(client, **extra):
    data = {"isbn": "978-3-423-21412-4", "category": CategoryFactory().pk, "lookup": "1"}
    data.update(extra)
    return client.post(reverse("title_create"), data)


def test_lookup_button_fills_form_without_saving(client, monkeypatch):
    fake_internet(monkeypatch, ALL_SOURCES)
    client.force_login(UserFactory(role=Role.MANAGER))
    content = lookup_post(client, author="Eigene Angabe").content.decode()
    assert 'value="Der kleine Hobbit"' in content
    assert 'value="Eigene Angabe"' in content  # Eingegebenes wird nicht überschrieben
    assert 'value="Neuausg., 2012"' in content
    assert "Daten von DNB, Open Library übernommen" in content
    assert not Title.objects.exists()


def test_lookup_without_connection_shows_hint(client):
    client.force_login(UserFactory(role=Role.MANAGER))
    content = lookup_post(client).content.decode()
    assert "Abruf gerade nicht möglich" in content


def test_lookup_rejects_invalid_isbn(client):
    client.force_login(UserFactory(role=Role.MANAGER))
    content = lookup_post(client, isbn="12345").content.decode()
    assert "gültige ISBN" in content


def test_cover_from_open_library_is_saved_with_title(client, monkeypatch, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    fake_internet(monkeypatch, {"covers.openlibrary.org": cover_bytes()})
    client.force_login(UserFactory(role=Role.MANAGER))
    client.post(
        reverse("title_create"),
        {
            "title": "Der kleine Hobbit",
            "category": CategoryFactory().pk,
            "cover_url": f"https://covers.openlibrary.org/b/isbn/{ISBN}-L.jpg?default=false",
        },
    )
    title = Title.objects.get()
    with Image.open(title.cover.path) as image:
        assert image.size == (400, 600)


def test_cover_from_other_hosts_is_ignored(client, monkeypatch):
    calls = fake_internet(monkeypatch, {})
    assert isbn_lookup.download_cover("https://example.org/cover.jpg") is None
    assert calls == []


def test_lookup_button_hidden_when_disabled(client):
    settings_row = SchoolSettings.current()
    settings_row.isbn_lookup_enabled = False
    settings_row.save()
    client.force_login(UserFactory(role=Role.MANAGER))
    assert "Daten zur ISBN abrufen" not in client.get(reverse("title_create")).content.decode()
    lookup_post(client)
    assert not IsbnLookupCache.objects.exists()
