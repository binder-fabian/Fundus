import datetime

import pytest
from django.utils import timezone

from fundus.accounts.models import Role
from fundus.loans import services
from fundus.loans.models import Loan
from fundus.loans.services import LoanError
from tests.factories import CategoryFactory, CopyFactory, LoanFactory, TitleFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def teacher():
    return UserFactory(role=Role.TEACHER)


@pytest.fixture
def manager():
    return UserFactory(role=Role.MANAGER)


def lendable_copy(days=14, **title):
    return CopyFactory(
        title=TitleFactory(category=CategoryFactory(default_loan_days=days), **title)
    )


def test_lend_to_self_with_default_due_date(teacher):
    copy = lendable_copy(days=14)
    loan = services.lend(copy, by=teacher)
    assert loan.borrower == teacher and loan.status == Loan.Status.LENT
    assert loan.due_date == timezone.localdate() + datetime.timedelta(days=14)
    assert loan.handed_over_by is None


def test_cannot_lend_twice(teacher):
    copy = lendable_copy()
    services.lend(copy, by=teacher)
    with pytest.raises(LoanError, match="bereits ausgeliehen"):
        services.lend(copy, by=UserFactory())


def test_not_lendable_title(teacher):
    with pytest.raises(LoanError, match="nicht zum Ausleihen"):
        services.lend(lendable_copy(lendable=False), by=teacher)


def test_teacher_cannot_lend_for_others(teacher):
    with pytest.raises(LoanError, match="nur für sich selbst"):
        services.lend(lendable_copy(), by=teacher, borrower=UserFactory())


def test_manager_lends_for_teacher(manager, teacher):
    loan = services.lend(lendable_copy(), by=manager, borrower=teacher)
    assert loan.borrower == teacher and loan.handed_over_by == manager


def test_approval_required_blocks_teacher_but_not_responsible(teacher):
    responsible = UserFactory(first_name="Petra", last_name="Test")
    copy = lendable_copy(approval_required=True, responsible=responsible)
    with pytest.raises(LoanError, match="Petra Test"):
        services.lend(copy, by=teacher)
    loan = services.lend(copy, by=responsible, borrower=teacher)
    assert loan.handed_over_by == responsible


def test_due_date_in_past_rejected(teacher):
    with pytest.raises(LoanError, match="Vergangenheit"):
        services.lend(
            lendable_copy(), by=teacher, due_date=timezone.localdate() - datetime.timedelta(days=1)
        )


def test_return_by_borrower_or_manager_only(teacher, manager):
    copy = lendable_copy()
    services.lend(copy, by=teacher)
    with pytest.raises(LoanError, match="Nur die ausleihende Person"):
        services.return_copy(copy, by=UserFactory())
    loan = services.return_copy(copy, by=manager)
    assert loan.status == Loan.Status.RETURNED and loan.returned_at
    with pytest.raises(LoanError, match="nicht ausgeliehen"):
        services.return_copy(copy, by=manager)


def test_return_incomplete_marks_copy_and_notes_missing_parts(teacher):
    copy = lendable_copy(contents="Manual\nTestheft A\nSchablone")
    services.lend(copy, by=teacher)
    services.return_copy(copy, by=teacher, complete=False, missing=["Testheft A"])
    copy.refresh_from_db()
    assert copy.incomplete
    assert "Testheft A" in copy.note

    services.lend(copy, by=teacher)
    services.return_copy(copy, by=teacher, complete=True)
    copy.refresh_from_db()
    assert not copy.incomplete


def test_extend(teacher):
    copy = lendable_copy(days=14)
    loan = services.lend(copy, by=teacher)
    first_due = loan.due_date
    later = timezone.localdate() + datetime.timedelta(days=10)
    loan = services.extend(loan, by=teacher, today=later)
    assert loan.due_date == later + datetime.timedelta(days=14)
    # Sofort erneut verlängern verschiebt um eine weitere Frist.
    loan = services.extend(loan, by=teacher, today=later)
    assert loan.due_date == first_due + datetime.timedelta(days=24)


def test_extend_blocked_by_pending_request_or_other_person(teacher):
    copy = lendable_copy()
    loan = services.lend(copy, by=teacher)
    with pytest.raises(LoanError, match="ausleihende Person"):
        services.extend(loan, by=UserFactory())
    LoanFactory(copy=copy, status=Loan.Status.REQUESTED, lent_at=None, borrower=UserFactory())
    with pytest.raises(LoanError, match="Anfrage"):
        services.extend(loan, by=teacher)


def test_borrower_visibility(teacher, manager):
    responsible = UserFactory()
    title = TitleFactory(responsible=responsible)
    assert services.can_see_borrower(manager, title)
    assert services.can_see_borrower(responsible, title)
    assert not services.can_see_borrower(teacher, title)


def test_is_overdue():
    loan = LoanFactory(due_date=timezone.localdate() - datetime.timedelta(days=1))
    assert loan.is_overdue
    loan.due_date = timezone.localdate()
    assert not loan.is_overdue
