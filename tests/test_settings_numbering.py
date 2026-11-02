import pytest
from django.urls import reverse

from fundus.accounts.models import Role
from fundus.catalog import numbering
from fundus.catalog.models import Copy
from fundus.core.models import SchoolSettings
from tests.factories import CategoryFactory, CopyFactory, TitleFactory, UserFactory

pytestmark = pytest.mark.django_db


def configure(prefix="FS-", digits=4, next_number=1):
    s = SchoolSettings.current()
    s.number_prefix, s.number_digits, s.next_number = prefix, digits, next_number
    s.save()
    return s


def test_allocate_continues_after_highest_existing_number():
    configure()
    CopyFactory(inventory_number="FS-0099")
    CopyFactory(inventory_number="fs-0100")
    CopyFactory(inventory_number="X-5000")
    CopyFactory(inventory_number="FS-0100a")
    assert numbering.preview_next() == "FS-0101"
    assert numbering.allocate(3) == ["FS-0101", "FS-0102", "FS-0103"]
    assert SchoolSettings.current().next_number == 104
    assert numbering.allocate(1) == ["FS-0104"]


def test_allocate_respects_higher_next_number():
    configure(prefix="", digits=1, next_number=5000)
    CopyFactory(inventory_number="1001")
    assert numbering.allocate(2) == ["5000", "5001"]


def test_allocate_skips_numbers_taken_in_other_format():
    configure(prefix="B", digits=2, next_number=1)
    CopyFactory(inventory_number="B01x")  # zählt nicht als laufende Nummer
    CopyFactory(inventory_number="b02")
    assert numbering.allocate(2) == ["B03", "B04"]


def test_copies_add_with_automatic_numbers(client):
    configure(next_number=7)
    client.force_login(UserFactory(role=Role.MANAGER))
    title = TitleFactory()
    page = client.get(reverse("copies_add", args=[title.pk])).content.decode()
    assert "beginnend mit FS-0007" in page
    client.post(reverse("copies_add", args=[title.pk]), {"auto_count": "2"})
    assert list(title.copies.values_list("inventory_number", flat=True)) == ["FS-0007", "FS-0008"]


def test_automatic_and_own_numbers_are_exclusive(client):
    configure()
    client.force_login(UserFactory(role=Role.MANAGER))
    title = TitleFactory()
    response = client.post(
        reverse("copies_add", args=[title.pk]), {"auto_count": "2", "numbers": "A-1"}
    )
    assert "nicht beides" in response.content.decode()
    assert not Copy.objects.filter(title=title).exists()


def test_settings_page_is_admin_only_and_saves(client):
    client.force_login(UserFactory(role=Role.MANAGER))
    assert client.get(reverse("school_settings")).status_code == 403

    client.force_login(UserFactory(role=Role.ADMIN))
    page = client.get(reverse("school_settings")).content.decode()
    assert "Nächste Nummer mit dem allgemeinen Präfix: FS-0001" in page
    response = client.post(
        reverse("school_settings"),
        {
            "school_name": "Musterschule",
            "number_prefix": "B-",
            "number_digits": "5",
            "next_number": "20",
            "outdated_norm_years": "8",
            "isbn_lookup_enabled": "",
            "reminders_enabled": "on",
            "reminder_days_before": "1",
            "overdue_notice_days": "3",
            "escalate_days": "14",
            "label_offset_x": "0.5",
            "label_offset_y": "-1",
        },
    )
    assert response.status_code == 302
    s = SchoolSettings.current()
    assert (s.number_prefix, s.number_digits, s.next_number) == ("B-", 5, 20)
    assert s.outdated_norm_years == 8 and not s.isbn_lookup_enabled
    assert numbering.preview_next() == "B-00020"
    assert s.school.name == "Musterschule"


def test_category_prefix_has_its_own_sequence():
    configure(prefix="FS-", next_number=50)
    books = CategoryFactory(number_prefix="B-")
    tests = CategoryFactory(number_prefix="T-")
    plain = CategoryFactory()
    CopyFactory(inventory_number="B-0007")
    assert numbering.allocate(2, books) == ["B-0008", "B-0009"]
    assert numbering.allocate(1, tests) == ["T-0001"]
    assert numbering.allocate(1, plain) == ["FS-0050"]
    # Die Folge einer Kategorie richtet sich nach den vorhandenen Exemplaren.
    CopyFactory(inventory_number="B-0009")
    assert numbering.preview_next(books) == "B-0010"
    # Kategorie-Folgen verändern die allgemeine Nummer nicht.
    assert SchoolSettings.current().next_number == 51


def test_copies_add_uses_prefix_of_title_category(client):
    configure()
    client.force_login(UserFactory(role=Role.MANAGER))
    title = TitleFactory(category=CategoryFactory(number_prefix="IT-"))
    page = client.get(reverse("copies_add", args=[title.pk])).content.decode()
    assert "beginnend mit IT-0001" in page
    client.post(reverse("copies_add", args=[title.pk]), {"auto_count": "2"})
    assert list(title.copies.values_list("inventory_number", flat=True)) == ["IT-0001", "IT-0002"]


def test_title_create_with_automatic_numbers_uses_chosen_category(client):
    configure()
    client.force_login(UserFactory(role=Role.MANAGER))
    category = CategoryFactory(number_prefix="T-")
    client.post(
        reverse("title_create"),
        {"title": "ELFE II", "category": category.pk, "copies-auto_count": "2"},
    )
    assert sorted(Copy.objects.values_list("inventory_number", flat=True)) == ["T-0001", "T-0002"]


def test_category_prefix_is_validated_and_shown(client):
    client.force_login(UserFactory(role=Role.MANAGER))
    url = reverse("masterdata_create", args=["kategorien"])
    response = client.post(url, {"name": "Spiele", "default_loan_days": 14, "number_prefix": "S P"})
    assert "keine Leerzeichen" in response.content.decode()
    client.post(url, {"name": "Spiele", "default_loan_days": 14, "number_prefix": "SP-"})
    listing = client.get(reverse("masterdata_list", args=["kategorien"])).content.decode()
    assert "Nummern SP-…" in listing
