import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from fundus.accounts.models import Role
from fundus.catalog.models import Category, Copy, Location, Title
from tests.factories import (
    CategoryFactory,
    CopyFactory,
    LoanFactory,
    LocationFactory,
    TitleFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def manager_client(client):
    client.force_login(UserFactory(role=Role.MANAGER))
    return client


@pytest.fixture
def teacher_client(client):
    client.force_login(UserFactory(role=Role.TEACHER))
    return client


def title_data(category, **extra):
    data = {"title": "ELFE II", "author": "Lenhard, W.", "category": category.pk}
    data.update(extra)
    return data


def test_teacher_reads_catalog_but_cannot_change_it(teacher_client):
    copy = CopyFactory()
    assert teacher_client.get(reverse("title_list")).status_code == 200
    assert teacher_client.get(reverse("title_detail", args=[copy.title_id])).status_code == 200
    assert teacher_client.get(reverse("copy_detail", args=[copy.pk])).status_code == 200
    for url in (
        reverse("title_create"),
        reverse("title_edit", args=[copy.title_id]),
        reverse("copies_add", args=[copy.title_id]),
        reverse("copy_edit", args=[copy.pk]),
        reverse("masterdata_list", args=["standorte"]),
        reverse("history", args=["titel", copy.title_id]),
    ):
        assert teacher_client.get(url).status_code == 403, url
    detail = teacher_client.get(reverse("title_detail", args=[copy.title_id])).content.decode()
    assert "Bearbeiten" not in detail


def test_title_list_shows_availability(teacher_client):
    title = TitleFactory(title="Testkoffer ABC")
    CopyFactory(title=title)
    LoanFactory(copy=CopyFactory(title=title))
    content = teacher_client.get(reverse("title_list")).content.decode()
    assert "Testkoffer ABC" in content
    assert "1 von 2 verfügbar" in content


def test_create_title_with_copy_series(manager_client):
    category = CategoryFactory()
    location = LocationFactory()
    data = title_data(
        category,
        **{
            "copies-prefix": "FS-",
            "copies-start": "0099",
            "copies-count": "3",
            "copies-location": location.pk,
        },
    )
    response = manager_client.post(reverse("title_create"), data)
    title = Title.objects.get(title="ELFE II")
    assert response["Location"] == reverse("title_detail", args=[title.pk])
    numbers = list(title.copies.values_list("inventory_number", "location"))
    assert numbers == [("FS-0099", location.pk), ("FS-0100", location.pk), ("FS-0101", location.pk)]


def test_create_title_without_copies(manager_client):
    manager_client.post(reverse("title_create"), title_data(CategoryFactory()))
    assert Title.objects.get(title="ELFE II").copies.count() == 0


def test_create_title_rejects_taken_inventory_number(manager_client):
    CopyFactory(inventory_number="FS-1")
    data = title_data(CategoryFactory(), **{"copies-numbers": "fs-1\nFS-2"})
    response = manager_client.post(reverse("title_create"), data)
    assert "Schon vergeben: FS-1" in response.content.decode()
    assert not Title.objects.filter(title="ELFE II").exists()


def test_copies_add_rejects_duplicates_in_input(manager_client):
    title = TitleFactory()
    response = manager_client.post(reverse("copies_add", args=[title.pk]), {"numbers": "A-1\na-1"})
    assert "Doppelt eingegeben" in response.content.decode()


def test_copies_add_from_list(manager_client):
    title = TitleFactory()
    manager_client.post(reverse("copies_add", args=[title.pk]), {"numbers": " A-1 \n\nA-2"})
    assert list(title.copies.values_list("inventory_number", flat=True)) == ["A-1", "A-2"]


def test_approval_required_needs_team(manager_client):
    data = title_data(CategoryFactory(), lendable="on", approval_required="on")
    response = manager_client.post(reverse("title_create"), data)
    assert "brauchen ein zuständiges Team" in response.content.decode()


def test_cover_is_shrunk_and_served_only_after_login(manager_client, client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    buffer = io.BytesIO()
    Image.new("RGBA", (2000, 1000), "red").save(buffer, format="PNG")
    upload = SimpleUploadedFile("cover.png", buffer.getvalue(), content_type="image/png")
    manager_client.post(reverse("title_create"), title_data(CategoryFactory(), cover=upload))
    title = Title.objects.get(title="ELFE II")
    with Image.open(title.cover.path) as stored:
        assert stored.size == (600, 300)
        assert stored.format == "JPEG"
    assert manager_client.get(title.cover.url).status_code == 200
    manager_client.logout()
    assert manager_client.get(title.cover.url).status_code == 302


def test_title_with_copies_cannot_be_deleted(manager_client):
    copy = CopyFactory()
    response = manager_client.post(reverse("title_delete", args=[copy.title_id]))
    assert response["Location"] == reverse("title_detail", args=[copy.title_id])
    assert Title.objects.filter(pk=copy.title_id).exists()


def test_title_without_copies_can_be_deleted(manager_client):
    title = TitleFactory()
    manager_client.post(reverse("title_delete", args=[title.pk]))
    assert not Title.objects.filter(pk=title.pk).exists()


def test_copy_with_loans_cannot_be_deleted(manager_client):
    loan = LoanFactory()
    manager_client.post(reverse("copy_delete", args=[loan.copy_id]))
    assert Copy.objects.filter(pk=loan.copy_id).exists()


def test_edit_copy_rejects_taken_number(manager_client):
    CopyFactory(inventory_number="X-1")
    copy = CopyFactory(inventory_number="X-2")
    response = manager_client.post(
        reverse("copy_edit", args=[copy.pk]), {"inventory_number": "x-1", "condition": "good"}
    )
    assert "schon vergeben" in response.content.decode()


def test_masterdata_create_and_duplicate(manager_client):
    url = reverse("masterdata_create", args=["kategorien"])
    manager_client.post(url, {"name": "Spiele", "default_loan_days": 7})
    assert Category.objects.get(name="Spiele").default_loan_days == 7
    response = manager_client.post(url, {"name": "spiele", "default_loan_days": 7})
    assert "gibt es schon" in response.content.decode()


def test_masterdata_in_use_cannot_be_deleted(manager_client):
    copy = CopyFactory()
    url = reverse("masterdata_edit", args=["standorte", copy.location_id])
    manager_client.post(url, {"delete": "1"})
    assert Location.objects.filter(pk=copy.location_id).exists()

    unused = LocationFactory()
    manager_client.post(reverse("masterdata_edit", args=["standorte", unused.pk]), {"delete": "1"})
    assert not Location.objects.filter(pk=unused.pk).exists()


def test_history_shows_changes_and_restores(manager_client):
    category = CategoryFactory()
    manager_client.post(reverse("title_create"), title_data(category))
    title = Title.objects.get(title="ELFE II")
    manager_client.post(
        reverse("title_edit", args=[title.pk]), title_data(category, title="ELFE III")
    )

    content = manager_client.get(reverse("history", args=["titel", title.pk])).content.decode()
    assert "ELFE II" in content and "ELFE III" in content
    assert "geändert" in content

    oldest = title.history.earliest()
    manager_client.post(reverse("history_restore", args=["titel", oldest.history_id]))
    title.refresh_from_db()
    assert title.title == "ELFE II"
    assert title.history.first().history_change_reason.startswith("Wiederhergestellt")


def test_deleted_location_can_be_restored(manager_client):
    location = LocationFactory(room="Raum 9")
    pk = location.pk
    manager_client.post(reverse("masterdata_edit", args=["standorte", pk]), {"delete": "1"})
    record = Location.history.filter(id=pk, history_type="+").first()
    manager_client.post(reverse("history_restore", args=["standort", record.history_id]))
    assert Location.objects.get(pk=pk).room == "Raum 9"
