import pytest
from django.core import mail
from django.urls import reverse

from fundus.accounts.models import Role
from fundus.core.models import SchoolSettings
from fundus.supplies import services
from fundus.supplies.models import Consumable, ReorderNotice
from tests.factories import TitleFactory, UserFactory
from tests.test_labels import pdf_text

pytestmark = pytest.mark.django_db


def item(**kwargs):
    defaults = {"name": "Protokollbögen ELFE", "code": services.next_code()}
    defaults.update(kwargs)
    return Consumable.objects.create(**defaults)


@pytest.fixture
def secretary():
    return UserFactory(role=Role.SECRETARY, email="sekretariat-person@schule.de")


def test_codes_are_numbered():
    assert services.next_code() == "NB-0001"
    item(code="NB-0007")
    item(code="anderes")
    assert services.next_code() == "NB-0008"


def test_reorder_notifies_secretary_and_extra_address_once(secretary):
    config = SchoolSettings.current()
    config.reorder_email = "sekretariat@schule.de"
    config.save()
    sheets = item(order_info="Hogrefe, Art.-Nr. 123")
    notice, created = services.request_reorder(sheets, by=UserFactory())
    assert created and notice.status == ReorderNotice.Status.OPEN
    assert sorted(mail.outbox[0].to) == ["sekretariat-person@schule.de", "sekretariat@schule.de"]
    assert "Hogrefe" in mail.outbox[0].body
    again, created = services.request_reorder(sheets)
    assert not created and again == notice and len(mail.outbox) == 1


def test_take_below_minimum_triggers_notice(secretary):
    sheets = item(track_stock=True, stock=12, min_stock=10)
    sheets, notice = services.take(sheets, UserFactory(), 1)
    assert sheets.stock == 11 and notice is None
    sheets, notice = services.take(sheets, UserFactory(), 5)
    assert sheets.stock == 6 and notice.reason == ReorderNotice.Reason.MINIMUM
    sheets, _ = services.take(sheets, UserFactory(), 100)
    assert sheets.stock == 0
    assert ReorderNotice.objects.count() == 1


def test_take_needs_tracking():
    with pytest.raises(services.SupplyError):
        services.take(item(), UserFactory(), 1)


def test_order_flow_restocks(secretary):
    sheets = item(track_stock=True, stock=2, min_stock=5)
    notice, _ = services.request_reorder(sheets)
    with pytest.raises(services.SupplyError, match="Sekretariat"):
        services.mark_ordered(notice, UserFactory(role=Role.TEACHER))
    services.mark_ordered(notice, secretary)
    services.mark_delivered(notice, secretary, 50)
    sheets.refresh_from_db()
    assert sheets.stock == 52
    notice.refresh_from_db()
    assert notice.status == ReorderNotice.Status.DELIVERED and notice.handled_by == secretary
    assert services.request_reorder(sheets)[1]  # danach wieder meldbar


def test_scanning_card_opens_item_and_teacher_reorders(client):
    client.force_login(UserFactory(role=Role.TEACHER))
    sheets = item(code="NB-0042")
    assert client.get("/s/nb-0042")["Location"] == reverse("consumable_detail", args=[sheets.pk])
    page = client.get(reverse("consumable_detail", args=[sheets.pk])).content.decode()
    assert "Nachbestellen</button>" in page
    client.post(reverse("consumable_reorder", args=[sheets.pk]))
    assert sheets.notices.count() == 1
    page = client.get(reverse("consumable_detail", args=[sheets.pk])).content.decode()
    assert "Nachbestellung offen" in page


def test_secretary_handles_list_and_sees_home_hint(client, secretary):
    sheets = item()
    services.request_reorder(sheets)
    client.force_login(secretary)
    assert "offene Nachbestellung" in client.get(reverse("home")).content.decode()
    page = client.get(reverse("reorder_list")).content.decode()
    assert "Protokollbögen ELFE" in page
    notice = sheets.notices.get()
    client.post(reverse("notice_action", args=[notice.pk, "bestellt"]))
    client.post(reverse("notice_action", args=[notice.pk, "geliefert"]))
    notice.refresh_from_db()
    assert notice.status == ReorderNotice.Status.DELIVERED


def test_teacher_cannot_see_reorder_list(client):
    client.force_login(UserFactory(role=Role.TEACHER))
    assert client.get(reverse("reorder_list")).status_code == 403


def test_manager_creates_item_for_title_and_prints_cards(client):
    client.force_login(UserFactory(role=Role.MANAGER))
    title = TitleFactory(title="ELFE II")
    form = client.get(reverse("consumable_create"), {"titel": title.pk}).content.decode()
    assert 'value="NB-0001"' in form
    client.post(
        reverse("consumable_create"),
        {
            "name": "Protokollbögen",
            "code": "NB-0001",
            "title": title.pk,
            "unit": "Block",
            "stock": 0,
            "min_stock": 0,
        },
    )
    sheets = Consumable.objects.get()
    assert sheets.title == title
    assert "Protokollbögen" in client.get(reverse("title_detail", args=[title.pk])).content.decode()
    pdf = client.post(reverse("reorder_cards"), {"items": [sheets.pk]})
    assert pdf["Content-Type"] == "application/pdf"
    text = pdf_text(pdf.content)
    assert b"(NB-0001)" in text and b"Nachbestellkarte" in text


def test_duplicate_code_rejected(client):
    client.force_login(UserFactory(role=Role.MANAGER))
    item(code="NB-0001")
    response = client.post(
        reverse("consumable_create"),
        {"name": "X", "code": "nb-0001", "unit": "Stück", "stock": 0, "min_stock": 0},
    )
    assert "schon vergeben" in response.content.decode()


def test_without_secretary_notices_go_to_management_and_settings_warn(client):
    admin = UserFactory(role=Role.ADMIN, email="leitung@schule.de")
    UserFactory(role=Role.MANAGER, email="verwaltung@schule.de")
    assert not services.order_handlers_configured()
    services.request_reorder(item())
    assert sorted(mail.outbox[0].to) == ["leitung@schule.de", "verwaltung@schule.de"]
    client.force_login(admin)
    assert (
        "Hinweise gehen deshalb an die Verwaltung"
        in client.get(reverse("school_settings")).content.decode()
    )


def test_settings_do_not_warn_with_secretary(client, secretary):
    assert services.order_handlers_configured()
    client.force_login(UserFactory(role=Role.ADMIN))
    page = client.get(reverse("school_settings")).content.decode()
    assert "Hinweise gehen deshalb an die Verwaltung" not in page
