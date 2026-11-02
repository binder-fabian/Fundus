import pytest
from django.urls import reverse

from fundus.accounts.models import Role
from fundus.loans.models import Loan
from tests.factories import CopyFactory, LoanFactory, TitleFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def manager(client):
    user = UserFactory(role=Role.MANAGER)
    client.force_login(user)
    return user


def test_scanner_returns_plain_copies_immediately(client, manager):
    loans = [LoanFactory(copy=CopyFactory(inventory_number=f"B-{i}")) for i in range(3)]
    for i in range(3):
        response = client.post(reverse("return_box"), {"nummer": f"b-{i}"})
        assert response["Location"] == reverse("return_box")
    assert not Loan.objects.filter(status=Loan.Status.LENT).exists()
    page = client.get(reverse("return_box")).content.decode()
    assert "Gerade zurückgebucht" in page and "B-0" in page
    assert all(Loan.objects.get(pk=loan.pk).returned_at for loan in loans)


def test_test_kit_asks_for_contents_first(client, manager):
    copy = CopyFactory(inventory_number="T-1", title=TitleFactory(contents="Manual\nTestheft"))
    LoanFactory(copy=copy)
    page = client.post(reverse("return_box"), {"nummer": "T-1"}).content.decode()
    assert "Inhalt prüfen" in page and "Testheft" in page
    assert Loan.objects.filter(copy=copy, status=Loan.Status.LENT).exists()

    client.post(reverse("return_box"), {"nummer": "T-1", "pruefung": "1", "part_0": "1"})
    copy.refresh_from_db()
    assert copy.incomplete and "Testheft" in copy.note
    assert not Loan.objects.filter(copy=copy, status=Loan.Status.LENT).exists()
    assert "fehlt: Testheft" in client.get(reverse("return_box")).content.decode()


def test_camera_scan_needs_one_tap(client, manager):
    loan = LoanFactory(copy=CopyFactory(inventory_number="K-1"))
    page = client.get(reverse("return_box"), {"nummer": "K-1"}).content.decode()
    assert "Zurückbuchen" in page
    assert Loan.objects.get(pk=loan.pk).status == Loan.Status.LENT  # GET bucht nichts
    client.post(reverse("return_box"), {"nummer": "K-1"})
    assert Loan.objects.get(pk=loan.pk).status == Loan.Status.RETURNED


def test_unknown_and_not_lent(client, manager):
    CopyFactory(inventory_number="X-1")
    assert (
        "Keine Inventarnummer"
        in client.post(reverse("return_box"), {"nummer": "NIX"}, follow=True).content.decode()
    )
    assert (
        "nicht ausgeliehen"
        in client.post(reverse("return_box"), {"nummer": "X-1"}, follow=True).content.decode()
    )


def test_return_box_for_managers_only(client):
    client.force_login(UserFactory(role=Role.TEACHER))
    assert client.get(reverse("return_box")).status_code == 403


def test_camera_mode_targets_return_box(client, manager):
    page = client.get(reverse("scanner"), {"ziel": "kiste"}).content.decode()
    assert 'data-target="/ausleihen/rueckgabekiste/?nummer=__CODE__"' in page
