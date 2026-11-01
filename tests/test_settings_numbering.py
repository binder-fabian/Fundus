import pytest
from django.urls import reverse

from fundus.accounts.models import Role
from fundus.catalog import numbering
from fundus.catalog.models import Copy
from fundus.core.models import SchoolSettings
from tests.factories import CopyFactory, TitleFactory, UserFactory

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
    assert "Nächste vergebene Nummer: FS-0001" in page
    response = client.post(
        reverse("school_settings"),
        {
            "school_name": "Musterschule",
            "number_prefix": "B-",
            "number_digits": "5",
            "next_number": "20",
            "outdated_norm_years": "8",
            "isbn_lookup_enabled": "",
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
