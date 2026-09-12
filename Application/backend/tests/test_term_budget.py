"""What a term cost, measured over the term rather than a calendar month.

A month is the wrong unit for a student: tuition lands once and textbooks land
in the first fortnight, neither of which is a monthly rhythm. Grades is the only
part of the app that knows when a term runs, and it knows it per course, so the
span is assembled from the courses themselves.
"""
import datetime
import uuid

from app._database.models import TransactionModel
from app.Finances.schemas.transaction import TransactionCreate, TransactionKind
from app.Finances.services.transaction_service import create_transaction
from app.Finances.services.tuition_service import term_budget, term_span
from conftest import make_account, make_category, make_course

SEP = datetime.date(2026, 9, 9)
DEC = datetime.date(2026, 12, 7)


def set_term(db, user, year=3, semester="Fall"):
    user.current_school_year = year
    user.current_semester = semester
    db.commit()


def dated(db, user, code, start=SEP, end=DEC, **overrides):
    overrides.setdefault("year", 3)
    overrides.setdefault("semester", "Fall")
    return make_course(db, user.id, code, start_date=start, end_date=end, **overrides)


def spend(db, user, account, amount, when, category=None, course=None):
    return create_transaction(db, user.id, TransactionCreate(
        kind=TransactionKind.EXPENSE, account_id=account.id, amount=amount,
        description="x", occurred_on=when,
        category_id=category.id if category else None,
        course_id=course.id if course else None,
    ))


# ------------------------------------------------------------- the span --

def test_the_span_is_the_widest_the_courses_reach(db, user):
    """A year-long course stretches it, which is how long you really pay for."""
    set_term(db, user)
    dated(db, user, "STAT 201", SEP, DEC)
    dated(db, user, "CPSC 322", datetime.date(2026, 9, 10), datetime.date(2027, 4, 8))

    assert term_span([]) == (None, None)

    budget = term_budget(db, user.id, today=datetime.date(2026, 10, 1))
    assert budget.starts_on == SEP
    assert budget.ends_on == datetime.date(2027, 4, 8)


def test_undated_courses_do_not_shrink_the_span(db, user):
    """They contribute nothing rather than defaulting to today."""
    set_term(db, user)
    dated(db, user, "STAT 201", SEP, DEC)
    make_course(db, user.id, "NODATE 100", year=3, semester="Fall")

    budget = term_budget(db, user.id, today=datetime.date(2026, 10, 1))
    assert (budget.starts_on, budget.ends_on) == (SEP, DEC)
    assert budget.dated_courses == 1
    assert budget.undated_courses == 1


def test_a_term_with_no_dated_course_says_so(db, user):
    set_term(db, user)
    make_course(db, user.id, "NODATE 100", year=3, semester="Fall")

    budget = term_budget(db, user.id)
    assert budget.can_measure is False
    assert "start and end dates" in budget.reason


def test_no_courses_at_all_says_something_different(db, user):
    set_term(db, user)
    budget = term_budget(db, user.id)
    assert budget.can_measure is False
    assert "No courses" in budget.reason


# ------------------------------------------------------------ the money --

def test_only_spend_inside_the_term_counts(db, user):
    set_term(db, user)
    dated(db, user, "STAT 201", SEP, DEC)
    account = make_account(db, user.id, "Chequing")

    spend(db, user, account, 100.0, datetime.date(2026, 9, 15))   # inside
    spend(db, user, account, 999.0, datetime.date(2026, 8, 1))    # before
    spend(db, user, account, 888.0, datetime.date(2027, 1, 5))    # after

    budget = term_budget(db, user.id, today=datetime.date(2026, 10, 1))
    assert budget.spent == 100.0


def test_the_boundary_days_are_inside_the_term(db, user):
    set_term(db, user)
    dated(db, user, "STAT 201", SEP, DEC)
    account = make_account(db, user.id, "Chequing")

    spend(db, user, account, 10.0, SEP)
    spend(db, user, account, 20.0, DEC)

    assert term_budget(db, user.id, today=DEC).spent == 30.0


def test_transfers_are_not_spending(db, user):
    """Moving money between pots would otherwise double the total."""
    from app.Finances.schemas.transaction import TransferCreate
    from app.Finances.services.transaction_service import create_transfer

    set_term(db, user)
    dated(db, user, "STAT 201", SEP, DEC)
    a = make_account(db, user.id, "Chequing")
    b = make_account(db, user.id, "Savings")
    create_transfer(db, user.id, TransferCreate(
        from_account_id=a.id, to_account_id=b.id, amount=500.0,
        occurred_on=datetime.date(2026, 9, 20), description="move",
    ))

    budget = term_budget(db, user.id, today=datetime.date(2026, 10, 1))
    assert budget.spent == 0.0
    assert budget.received == 0.0


def test_spend_tagged_to_a_course_is_reported_separately(db, user):
    set_term(db, user)
    course = dated(db, user, "STAT 201", SEP, DEC)
    account = make_account(db, user.id, "Chequing")

    spend(db, user, account, 89.0, datetime.date(2026, 9, 15), course=course)
    spend(db, user, account, 40.0, datetime.date(2026, 9, 16))

    budget = term_budget(db, user.id, today=datetime.date(2026, 10, 1))
    assert budget.spent == 129.0
    assert budget.on_courses == 89.0


def test_income_is_counted_and_nets_off(db, user):
    set_term(db, user)
    dated(db, user, "STAT 201", SEP, DEC)
    account = make_account(db, user.id, "Chequing")

    spend(db, user, account, 100.0, datetime.date(2026, 9, 15))
    create_transaction(db, user.id, TransactionCreate(
        kind=TransactionKind.INCOME, account_id=account.id, amount=250.0,
        description="pay", occurred_on=datetime.date(2026, 9, 20),
    ))

    budget = term_budget(db, user.id, today=datetime.date(2026, 10, 1))
    assert (budget.spent, budget.received, budget.net) == (100.0, 250.0, 150.0)


# ------------------------------------------------------------ the clock --

def test_progress_through_the_term_is_clamped(db, user):
    set_term(db, user)
    dated(db, user, "STAT 201", SEP, DEC)

    before = term_budget(db, user.id, today=datetime.date(2026, 1, 1))
    during = term_budget(db, user.id, today=SEP)
    after = term_budget(db, user.id, today=datetime.date(2030, 1, 1))

    assert before.days_elapsed == 0
    assert during.days_elapsed == 1
    assert after.days_elapsed == after.days_total
    assert during.days_total == (DEC - SEP).days + 1
