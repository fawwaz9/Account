"""What a term cost, measured over the term rather than a calendar month.

A month is the wrong unit for a student: tuition lands once and textbooks land
in the first fortnight, neither of which is a monthly rhythm.

The span used to be assembled from the courses -- earliest start, latest end --
which meant a term could only be measured if the courses in it happened to
carry dates. Most did not. Now the term has its own fixed dates, resolved to a
calendar year through one anchor: the year first year began.
"""
import datetime
import uuid

from app._database.models import TransactionModel
from app.Finances.schemas.transaction import TransactionCreate, TransactionKind
from app.Finances.services.transaction_service import create_transaction
from app.Finances.services.tuition_service import term_budget, term_span
from conftest import make_account, make_category, make_course

#: When the teaching actually runs, which is no longer what is measured.
SEP = datetime.date(2026, 9, 9)
DEC = datetime.date(2026, 12, 7)

#: What Fall of school year 3 resolves to, given the anchor below.
TERM_START = datetime.date(2026, 9, 1)
TERM_END = datetime.date(2026, 12, 31)

#: First year began in 2024, so year 3's Fall is 2026.
ANCHOR = 2024


def set_term(db, user, year=3, semester="Fall", anchor=ANCHOR):
    user.current_school_year = year
    user.current_semester = semester
    user.first_year_calendar_year = anchor
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

def test_the_span_is_the_term_not_the_teaching_weeks(db, user):
    """The deliberate trade. A Fall that really runs Sep 9 to Dec 7 is measured
    Sep 1 to Dec 31, so a few weeks either side are counted -- which beats the
    old behaviour of not being able to measure the term at all."""
    set_term(db, user)
    dated(db, user, "STAT 201", SEP, DEC)

    budget = term_budget(db, user.id, today=datetime.date(2026, 10, 1))
    assert (budget.starts_on, budget.ends_on) == (TERM_START, TERM_END)


def test_a_course_with_no_dates_of_its_own_is_measured_all_the_same(db, user):
    """The whole point. 21 of 27 real courses carry no dates, and under the old
    rule none of their terms could be measured."""
    set_term(db, user)
    make_course(db, user.id, "NODATE 100", year=3, semester="Fall")

    budget = term_budget(db, user.id, today=datetime.date(2026, 10, 1))
    assert budget.can_measure is True
    assert (budget.starts_on, budget.ends_on) == (TERM_START, TERM_END)


def test_a_course_cannot_stretch_the_term_past_its_own_end(db, user):
    """The old span took the latest end across the courses, so one year-long
    course dragged the whole term with it. A term is now a term."""
    set_term(db, user)
    dated(db, user, "CPSC 322", datetime.date(2026, 9, 10), datetime.date(2027, 4, 8))

    budget = term_budget(db, user.id, today=datetime.date(2026, 10, 1))
    assert budget.ends_on == TERM_END


def test_with_no_anchor_there_are_no_dates_and_it_says_why(db, user):
    """A school year is 1..10, not a calendar year, so without the anchor there
    is genuinely nothing to resolve. Guessing would date a current course three
    years into the past with nothing on screen to explain it."""
    set_term(db, user, anchor=None)
    dated(db, user, "STAT 201", SEP, DEC)

    assert term_span([], None) == (None, None)

    budget = term_budget(db, user.id)
    assert budget.can_measure is False
    assert "first year began" in budget.reason


def test_winter_lands_in_the_calendar_year_after_its_fall(db, user):
    """The offset that makes a school year read "2026-2027". Getting it wrong
    puts Winter eight months before the Fall it follows."""
    set_term(db, user, semester="Winter")
    make_course(db, user.id, "CPSC 310", year=3, semester="Winter")

    budget = term_budget(db, user.id, today=datetime.date(2027, 2, 1))
    assert budget.starts_on == datetime.date(2027, 1, 1)
    assert budget.ends_on == datetime.date(2027, 4, 30)


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

    spend(db, user, account, 10.0, TERM_START)
    spend(db, user, account, 20.0, TERM_END)

    assert term_budget(db, user.id, today=TERM_END).spent == 30.0


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
    during = term_budget(db, user.id, today=TERM_START)
    after = term_budget(db, user.id, today=datetime.date(2030, 1, 1))

    assert before.days_elapsed == 0
    assert during.days_elapsed == 1
    assert after.days_elapsed == after.days_total
    assert during.days_total == (TERM_END - TERM_START).days + 1
