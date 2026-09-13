"""Query counts, and the cent that never existed.

A performance fix is only worth having if the answer does not change, so the
first test here pins the figures and the rest pin the cost. The query-count
assertions are deliberately generous bounds rather than exact numbers: the point
is "does not grow with the number of courses", and an exact count would fail on
any unrelated refactor without telling anyone anything.
"""
import uuid
from datetime import date

import pytest
from sqlalchemy import event

from app._database.models import TransactionModel
from app.Finances.schemas.deposit import DepositCreate, DepositAllocation
from app.Finances.services.account_service import balance_of, get_account
from app.Grades.schemas.grade import GradeCreate
from app.Grades.services.dash_services import get_dashboard
from app.Grades.services.grade_service import add_grade
from conftest import make_account, make_course


class QueryCounter:
    """Counts statements issued on a session's engine."""

    def __init__(self, db):
        self.engine = db.get_bind()
        self.count = 0

    def _bump(self, *_args, **_kwargs):
        self.count += 1

    def __enter__(self):
        event.listen(self.engine, "before_cursor_execute", self._bump)
        return self

    def __exit__(self, *_exc):
        event.remove(self.engine, "before_cursor_execute", self._bump)


def course_with_grades(db, user, code: str):
    course = make_course(db, user.id, code, category_weights={"Assignment": 50.0, "Final": 50.0})
    add_grade(db, user.id, course.id, GradeCreate(
        name="A1", score=80.0, max_score=100.0, category="Assignment",
    ))
    return course


# --------------------------------------------------------------- #22 the N+1 --

def test_the_dashboard_does_not_query_per_course(db, user):
    """It was ~3 queries a course: lazy grades, lazy weights, and a re-fetch."""
    for index in range(10):
        course_with_grades(db, user, f"COSC {100 + index}")

    with QueryCounter(db) as counter:
        get_dashboard(db, user.id)

    assert counter.count < 15, f"{counter.count} queries for 10 courses"


def test_the_dashboard_cost_is_flat_in_the_number_of_courses(db, user):
    """The property that matters: adding courses must not add queries."""
    for index in range(3):
        course_with_grades(db, user, f"AAAA {100 + index}")
    with QueryCounter(db) as small:
        get_dashboard(db, user.id)

    for index in range(12):
        course_with_grades(db, user, f"BBBB {100 + index}")
    with QueryCounter(db) as large:
        get_dashboard(db, user.id)

    assert large.count == small.count


def test_the_dashboard_still_reports_the_same_figures(db, user):
    """Loading differently must not answer differently."""
    course = course_with_grades(db, user, "COSC 111")

    dashboard = get_dashboard(db, user.id)

    assert dashboard.total_courses == 1
    assert dashboard.best_course is not None
    assert dashboard.best_course.course_code == "COSC 111"
    assert dashboard.best_course.average == course.average


# ------------------------------------------------- #23 one account's balance --

def test_one_accounts_balance_does_not_read_the_whole_ledger(db, user):
    wanted = make_account(db, user.id, "Chequing")
    other = make_account(db, user.id, "Savings")
    for account, amount in ((wanted, 100.0), (other, 5000.0)):
        db.add(TransactionModel(
            id=uuid.uuid4(), user_id=user.id, account_id=account.id, kind="income",
            amount=amount, description="Opening", occurred_on=date(2026, 9, 1),
        ))
    db.commit()

    assert balance_of(db, user.id, wanted.id) == 100.0
    assert get_account(db, user.id, wanted.id).balance == 100.0


def test_an_account_with_no_transactions_reads_zero(db, user):
    account = make_account(db, user.id, "Chequing")

    assert balance_of(db, user.id, account.id) == 0.0
    assert get_account(db, user.id, account.id).balance == 0.0


def test_a_balance_is_only_its_own_accounts_rows(db, user):
    """The filter is what makes the cheaper query correct, not just cheaper."""
    mine = make_account(db, user.id, "Chequing")
    theirs = make_account(db, user.id, "Savings")
    db.add(TransactionModel(
        id=uuid.uuid4(), user_id=user.id, account_id=theirs.id, kind="income",
        amount=999.0, description="Not mine", occurred_on=date(2026, 9, 1),
    ))
    db.commit()

    assert balance_of(db, user.id, mine.id) == 0.0


# ------------------------------------------- #50 a cent that never existed --

def deposit(amount: float, allocations: list[tuple[uuid.UUID, float]]):
    return DepositCreate(
        amount=amount,
        occurred_on=date(2026, 9, 1),
        description="Paycheque",
        allocations=[
            DepositAllocation(account_id=account_id, amount=value)
            for account_id, value in allocations
        ],
    )


# Amounts chosen deliberately. The old rule was `abs(difference) > 0.01`, and
# for many values -- 100.00 among them -- the float difference lands just *above*
# 0.01 and the wrong total was rejected by accident. These are values where it
# genuinely lands at or below, which is where a cent that never existed got in.
# Sweeping every amount from 0.01 to 600.00 finds tens of thousands of them.
CENT_OVER = (100.01, 100.02)
CENT_UNDER = (100.02, 100.01)


def test_allocations_a_cent_over_are_rejected(db, user):
    """`> 0.01` accepted exactly one cent of invented money."""
    account = make_account(db, user.id, "Chequing")
    amount, allocated = CENT_OVER

    with pytest.raises(ValueError, match="Allocations total"):
        deposit(amount, [(account.id, allocated)])


def test_allocations_a_cent_under_are_rejected(db, user):
    account = make_account(db, user.id, "Chequing")
    amount, allocated = CENT_UNDER

    with pytest.raises(ValueError, match="Allocations total"):
        deposit(amount, [(account.id, allocated)])


def test_allocations_that_match_exactly_are_accepted(db, user):
    first = make_account(db, user.id, "Chequing")
    second = make_account(db, user.id, "Savings")

    payload = deposit(100.00, [(first.id, 75.00), (second.id, 25.00)])

    assert len(payload.allocations) == 2


def test_a_split_that_only_adds_up_in_floating_point_is_still_accepted(db, user):
    """Thirds of a tenner: 3.33 + 3.33 + 3.34 is exact in cents, not in floats."""
    accounts = [make_account(db, user.id, name) for name in ("A", "B", "C")]

    payload = deposit(10.00, [
        (accounts[0].id, 3.33), (accounts[1].id, 3.33), (accounts[2].id, 3.34),
    ])

    assert len(payload.allocations) == 3
