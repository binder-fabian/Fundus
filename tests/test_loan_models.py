import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from fundus.catalog.models import Copy
from fundus.loans.models import Loan
from tests.factories import CopyFactory, LoanFactory, UserFactory

pytestmark = pytest.mark.django_db


def test_copy_without_loans_is_available():
    copy = CopyFactory()
    annotated = Copy.objects.with_availability().get(pk=copy.pk)
    assert annotated.is_lent is False
    assert annotated.due_date is None
    assert copy.active_loan is None


def test_lent_copy_shows_due_date_and_borrower():
    loan = LoanFactory()
    annotated = Copy.objects.with_availability().get(pk=loan.copy_id)
    assert annotated.is_lent is True
    assert annotated.due_date == loan.due_date
    assert annotated.borrower_id == loan.borrower_id
    assert loan.copy.active_loan == loan


def test_returned_and_requested_loans_do_not_count_as_lent():
    copy = CopyFactory()
    LoanFactory(copy=copy, status=Loan.Status.RETURNED, returned_at=timezone.now())
    LoanFactory(copy=copy, status=Loan.Status.REQUESTED, lent_at=None)
    assert Copy.objects.with_availability().get(pk=copy.pk).is_lent is False


def test_availability_annotation_does_not_duplicate_rows():
    copy = CopyFactory()
    LoanFactory(copy=copy, status=Loan.Status.RETURNED, returned_at=timezone.now())
    LoanFactory(copy=copy)
    assert Copy.objects.with_availability().filter(pk=copy.pk).count() == 1


def test_only_one_active_loan_per_copy():
    loan = LoanFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        LoanFactory(copy=loan.copy)


def test_copy_can_be_lent_again_after_return():
    loan = LoanFactory()
    loan.status = Loan.Status.RETURNED
    loan.returned_at = timezone.now()
    loan.save()
    LoanFactory(copy=loan.copy)


def test_loan_needs_borrower_or_label():
    with pytest.raises(IntegrityError), transaction.atomic():
        LoanFactory(borrower=None, borrower_label="")


def test_loan_without_person_uses_class_or_room():
    loan = LoanFactory(borrower=None, borrower_label="Klasse 3b")
    assert loan.borrower_display == "Klasse 3b"


def test_anonymized_loan_keeps_statistics_without_person():
    loan = LoanFactory(status=Loan.Status.RETURNED, returned_at=timezone.now())
    loan.borrower = None
    loan.anonymized_at = timezone.now()
    loan.save()
    assert loan.borrower_display == "anonymisiert"
    assert Loan.objects.filter(copy__title=loan.copy.title).count() == 1


def test_lent_status_requires_lent_at():
    with pytest.raises(IntegrityError), transaction.atomic():
        LoanFactory(lent_at=None)


def test_returned_status_requires_returned_at():
    with pytest.raises(IntegrityError), transaction.atomic():
        LoanFactory(status=Loan.Status.RETURNED, returned_at=None)


def test_teacher_with_loans_cannot_be_deleted():
    teacher = UserFactory()
    LoanFactory(borrower=teacher)
    with pytest.raises(Exception, match="protected"), transaction.atomic():
        teacher.delete()
