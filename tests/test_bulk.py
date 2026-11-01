import pytest
from django.urls import reverse

from fundus.accounts.models import Role
from fundus.catalog import bulk
from fundus.catalog.models import Copy, IsbnLookupCache, Title
from fundus.core.models import SchoolSettings
from tests.factories import CategoryFactory, LocationFactory, TitleFactory, UserFactory
from tests.test_isbn_lookup import ALL_SOURCES, cover_bytes, fake_internet

pytestmark = pytest.mark.django_db

HOBBIT = "9783423214124"
UNKNOWN = "9780000000002"


def cache(isbn, title="", author=""):
    data = {"title": title, "author": author} if title else {}
    IsbnLookupCache.objects.create(
        isbn=isbn,
        result={"data": data, "sources": ["DNB"] if title else [], "cover_url": ""},
        fetched_at="2026-11-02T08:00:00Z",
    )


def test_parse_isbns_counts_repeats_and_reports_invalid():
    text = f"978-3-423-21412-4\n{HOBBIT}\n3-499-13599-X\n9783161484101\nhallo\n"
    rows, invalid = bulk.parse_isbns(text)
    assert rows == [(HOBBIT, 2), ("349913599X", 1)]
    assert invalid == ["9783161484101"]


def test_parse_isbns_from_csv_columns():
    rows, _ = bulk.parse_isbns('"Titel";"ISBN"\n"Hobbit";"978-3-423-21412-4"\n')
    assert rows == [(HOBBIT, 1)]


def test_create_uses_lookup_numbering_and_extends_existing():
    s = SchoolSettings.current()
    s.number_prefix, s.next_number = "B-", 1
    s.save()
    cache(HOBBIT, "Der kleine Hobbit", "Tolkien")
    cache(UNKNOWN)
    existing = TitleFactory(title="Schon da", isbn="9783161484100")
    category, location = CategoryFactory(), LocationFactory()

    new, extended, copies, missing = bulk.create(
        [(HOBBIT, 2), ("9783161484100", 1), (UNKNOWN, 1)], category, location, lendable=True
    )
    assert [t.title for t in new] == ["Der kleine Hobbit"]
    assert extended == [existing]
    assert missing == [UNKNOWN]
    assert [c.inventory_number for c in copies] == ["B-0001", "B-0002", "B-0003"]
    hobbit = Title.objects.get(isbn=HOBBIT)
    assert hobbit.lendable and hobbit.category == category
    assert hobbit.copies.count() == 2 and existing.copies.count() == 1
    assert all(c.location == location for c in copies)


def test_bulk_flow(client, monkeypatch):
    fake_internet(monkeypatch, ALL_SOURCES)
    client.force_login(UserFactory(role=Role.MANAGER))
    response = client.post(reverse("bulk_start"), {"isbns": f"{HOBBIT}\n{HOBBIT}\n"})
    assert response["Location"] == reverse("bulk_preview")

    preview = client.get(reverse("bulk_preview")).content.decode()
    assert "wird abgerufen" in preview and "zusammen 2 Exemplare" in preview
    row = client.get(reverse("bulk_row", args=[HOBBIT])).content.decode()
    assert "Der kleine Hobbit" in row and "checked" in row

    category = CategoryFactory()
    done = client.post(
        reverse("bulk_preview"),
        {"category": category.pk, f"include_{HOBBIT}": "1", f"count_{HOBBIT}": "3"},
    ).content.decode()
    assert "3 Exemplare angelegt" in done
    assert Copy.objects.filter(title__isbn=HOBBIT).count() == 3
    assert "Etiketten drucken" in done


def test_fetch_cover_after_bulk(client, monkeypatch, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    IsbnLookupCache.objects.create(
        isbn=HOBBIT,
        result={
            "data": {"title": "Der kleine Hobbit"},
            "sources": ["Open Library"],
            "cover_url": f"https://covers.openlibrary.org/b/isbn/{HOBBIT}-L.jpg?default=false",
        },
        fetched_at="2099-01-01T00:00:00Z",
    )
    fake_internet(monkeypatch, {"covers.openlibrary.org": cover_bytes()})
    title = TitleFactory(isbn=HOBBIT)
    client.force_login(UserFactory(role=Role.MANAGER))
    response = client.post(reverse("fetch_cover", args=[title.pk]))
    assert response.content.decode() == "Cover übernommen"
    title.refresh_from_db()
    assert title.cover


def test_bulk_is_for_managers_only(client):
    client.force_login(UserFactory(role=Role.TEACHER))
    assert client.get(reverse("bulk_start")).status_code == 403
