import datetime

import pytest
from django.urls import reverse

from fundus.catalog.models import SupportFocus
from fundus.catalog.search import search_titles
from fundus.catalog.text import normalize
from tests.factories import (
    CategoryFactory,
    CopyFactory,
    LoanFactory,
    LocationFactory,
    TitleFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


def found(**params):
    _form, titles = search_titles(params)
    return sorted(t.title for t in titles)


def test_normalize_umlauts_and_case():
    assert normalize("Übungen für Müller, Straße") == "uebungen fuer mueller, strasse"


def test_search_ignores_case_and_umlauts():
    TitleFactory(title="Übungsheft Lesen", author="Müller, A.")
    TitleFactory(title="Rechnen")
    assert found(q="übungsheft") == ["Übungsheft Lesen"]
    assert found(q="ÜBUNGSHEFT") == ["Übungsheft Lesen"]
    assert found(q="mueller") == ["Übungsheft Lesen"]
    assert found(q="Müller") == ["Übungsheft Lesen"]


def test_all_words_must_match():
    TitleFactory(title="Lesetest Klasse 3", author="Schmidt")
    TitleFactory(title="Lesetest Klasse 5", author="Huber")
    assert found(q="lesetest schmidt") == ["Lesetest Klasse 3"]


def test_search_by_isbn_with_or_without_hyphens():
    TitleFactory(title="Mit ISBN", isbn="978-3-16-148410-0")
    assert found(q="9783161484100") == ["Mit ISBN"]
    assert found(q="978-3-16-148410-0") == ["Mit ISBN"]


def test_search_by_inventory_number_part_without_duplicates():
    title = TitleFactory(title="Koffer")
    CopyFactory(title=title, inventory_number="FS-0101")
    CopyFactory(title=title, inventory_number="FS-0102")
    assert found(q="fs-01") == ["Koffer"]


def test_search_text_follows_edits():
    title = TitleFactory(title="Alt")
    title.title = "Neu"
    title.save()
    assert found(q="neu") == ["Neu"]
    assert found(q="alt") == []


def test_filters():
    tests = CategoryFactory(name="Tests")
    room = LocationFactory(room="Raum 12")
    a = TitleFactory(title="A", category=tests)
    CopyFactory(title=a, location=room)
    b = TitleFactory(title="B")
    LoanFactory(copy=CopyFactory(title=b))
    TitleFactory(title="C", lendable=False)
    assert found(kategorie=tests.pk) == ["A"]
    assert found(standort=room.pk) == ["A"]
    assert found(verfuegbarkeit="verfuegbar") == ["A"]
    assert found(verfuegbarkeit="ausgeliehen") == ["B"]


def test_support_focus_filter():
    title = TitleFactory(title="Sprachförderung")
    focus = SupportFocus.objects.get(name="Sprache")
    title.support_focuses.add(focus)
    TitleFactory(title="Anderes")
    assert found(foerderschwerpunkt=focus.pk) == ["Sprachförderung"]


def test_outdated_filter(settings):
    settings.OUTDATED_NORM_YEARS = 10
    year = datetime.date.today().year
    TitleFactory(title="Alt", norm_year=year - 15)
    TitleFactory(title="Aktuell", norm_year=year - 3)
    TitleFactory(title="Ohne Norm")
    assert found(veraltet="on") == ["Alt"]


def test_exact_inventory_number_opens_copy(client):
    client.force_login(UserFactory())
    copy = CopyFactory(inventory_number="FS-0042")
    response = client.get(reverse("title_list"), {"q": "fs-0042"})
    assert response["Location"] == reverse("copy_detail", args=[copy.pk])


def test_live_search_returns_partial_with_exact_hit(client):
    client.force_login(UserFactory())
    copy = CopyFactory(inventory_number="FS-0042", title__title="Testkoffer")
    response = client.get(reverse("title_list"), {"q": "FS-0042"}, HTTP_HX_REQUEST="true")
    content = response.content.decode()
    assert response.status_code == 200
    assert "<html" not in content
    assert "Exemplar gefunden" in content and copy.title.title in content


def test_list_page_keeps_filters_in_pagination(client, settings):
    client.force_login(UserFactory())
    category = CategoryFactory()
    for i in range(55):
        TitleFactory(title=f"T{i:02d}", category=category)
    response = client.get(reverse("title_list"), {"kategorie": category.pk})
    assert f"kategorie={category.pk}&amp;seite=2" in response.content.decode()
