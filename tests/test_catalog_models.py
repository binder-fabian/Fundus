import datetime

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from fundus.catalog.isbn import normalize_isbn, validate_isbn
from fundus.catalog.models import Category, Copy, SupportFocus, Title
from tests.factories import (
    CategoryFactory,
    CopyFactory,
    SchoolFactory,
    TitleFactory,
    default_school,
)

pytestmark = pytest.mark.django_db


def test_default_school_and_seed_data_exist():
    school = default_school()
    days = dict(Category.objects.filter(school=school).values_list("name", "default_loan_days"))
    assert days == {"Bücher": 28, "Diagnostik/Tests": 14, "Fördermaterial": 28, "Technik": 14}
    assert SupportFocus.objects.filter(school=school).count() == 7


def test_inventory_number_unique_per_school_ignoring_case():
    CopyFactory(inventory_number="FS-0001")
    with pytest.raises(IntegrityError), transaction.atomic():
        CopyFactory(inventory_number="fs-0001")


def test_same_inventory_number_allowed_in_other_school():
    CopyFactory(inventory_number="FS-0001")
    other_title = TitleFactory(school=SchoolFactory())
    copy = CopyFactory(title=other_title, inventory_number="FS-0001")
    assert copy.school == other_title.school


def test_full_clean_reports_duplicate_inventory_number():
    existing = CopyFactory(inventory_number="FS-0001")
    duplicate = Copy(title=existing.title, inventory_number=" fs-0001 ")
    duplicate.school_id = existing.school_id
    with pytest.raises(ValidationError, match="schon vergeben"):
        duplicate.full_clean()


def test_copy_takes_school_from_title_and_strips_number():
    other = TitleFactory(school=SchoolFactory())
    copy = CopyFactory(title=other, inventory_number="  A-7 ")
    assert copy.school_id == other.school_id
    assert copy.inventory_number == "A-7"


def test_approval_required_needs_lendable():
    with pytest.raises(IntegrityError), transaction.atomic():
        TitleFactory(lendable=False, approval_required=True)


def test_isbn_is_normalized_on_save():
    title = TitleFactory(isbn="978-3-16-148410-0")
    assert title.isbn == "9783161484100"


@pytest.mark.parametrize("value", ["978-3-16-148410-0", "3-499-13599-X", "349913599x"])
def test_valid_isbns(value):
    validate_isbn(value)


@pytest.mark.parametrize("value", ["978-3-16-148410-1", "12345", "abcdefghij"])
def test_invalid_isbns(value):
    with pytest.raises(ValidationError):
        validate_isbn(value)


def test_normalize_isbn():
    assert normalize_isbn(" 3-499-13599-x ") == "349913599X"
    assert normalize_isbn(None) == ""


def test_full_clean_accepts_isbn_with_hyphens():
    title = TitleFactory.build(isbn="978-3-16-148410-0", category=CategoryFactory())
    title.full_clean()
    assert title.isbn == "9783161484100"


def test_contents_items_skips_blank_lines():
    title = TitleFactory.build(contents="Manual\n\n  Protokollbogen A \nBildkarten\n")
    assert title.contents_items == ["Manual", "Protokollbogen A", "Bildkarten"]


def test_norm_is_outdated():
    today = datetime.date(2026, 11, 1)
    assert TitleFactory.build(norm_year=2010).norm_is_outdated(10, today=today)
    assert not TitleFactory.build(norm_year=2018).norm_is_outdated(10, today=today)
    assert not TitleFactory.build(norm_year=None).norm_is_outdated(10, today=today)


def test_default_due_date_uses_category_period():
    title = TitleFactory(category__default_loan_days=14)
    assert title.default_due_date(datetime.date(2026, 11, 2)) == datetime.date(2026, 11, 16)


def test_history_records_changes():
    title = TitleFactory(title="Alt")
    title.title = "Neu"
    title.save()
    assert [h.title for h in title.history.all()] == ["Neu", "Alt"]

    old = title.history.earliest()
    old.instance.save()
    title.refresh_from_db()
    assert title.title == "Alt"


def test_title_with_copies_cannot_be_deleted():
    copy = CopyFactory()
    with pytest.raises(Exception, match="protected"), transaction.atomic():
        Title.objects.filter(pk=copy.title_id).delete()
