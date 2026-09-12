"""A tuition payment, and what it says a course cost.

The thing being pinned here is that these are two different questions with two
different answers, and that neither drifts into the other. The ledger records
what left the account -- net of deductions, fees folded in. Grades reports what a
course is worth -- gross, per credit. A test that made them agree would be
testing the bug.
"""
import uuid

import pytest

from app._database.models import (
    SpendCategoryModel, TransactionModel, TuitionPaymentModel, UserModel,
)
from app.Finances.schemas.transaction import TransactionCreate, TransactionKind
from app.Finances.schemas.tuition import TuitionCreate, TuitionDeduction
from app.Finances.services.transaction_service import create_transaction
from app.Finances.services.tuition_service import (
    billable_courses, course_cost, preview_tuition, record_tuition,
)
from conftest import make_account, make_category, make_course


def in_term(db, user, code, credits=3.0, **overrides):
    """A course in the user's current term, which is where tuition applies."""
    overrides.setdefault("year", 3)
    overrides.setdefault("semester", "Fall")
    return make_course(db, user.id, code, credits=credits, **overrides)


def set_term(db, user, year=3, semester="Fall"):
    user.current_school_year = year
    user.current_semester = semester
    db.commit()


def pay(db, user, account, rate=250.0, fees=0.0, deductions=(), **overrides):
    return record_tuition(db, user.id, TuitionCreate(
        account_id=account.id,
        occurred_on=overrides.pop("occurred_on", __import__("datetime").date(2026, 9, 15)),
        cost_per_credit=rate,
        fees=fees,
        deductions=[TuitionDeduction(description=d, amount=a) for d, a in deductions],
        **overrides,
    ))


# ------------------------------------------------------------ the ledger --

def test_a_tuition_payment_writes_exactly_one_transaction(db, user):
    set_term(db, user)
    account = make_account(db, user.id, "Chequing")
    for code in ("CPSC 210", "MATH 200", "ENGL 112"):
        in_term(db, user, code)

    pay(db, user, account, rate=250.0)

    rows = db.query(TransactionModel).filter(TransactionModel.user_id == user.id).all()
    assert len(rows) == 1
    # Never tagged to a course: it covers the whole term.
    assert rows[0].course_id is None


def test_the_ledger_row_is_net_of_deductions_with_fees_folded_in(db, user):
    set_term(db, user)
    account = make_account(db, user.id, "Chequing")
    in_term(db, user, "CPSC 210", credits=4.0)
    in_term(db, user, "MATH 200", credits=3.0)
    in_term(db, user, "ENGL 112", credits=3.0)
    in_term(db, user, "PHYS 118", credits=3.0)

    pay(db, user, account, rate=250.0, fees=310.0, deductions=[
        ("Entrance scholarship", 1000.0), ("Deposit paid in July", 500.0),
    ])

    row = db.query(TransactionModel).filter(TransactionModel.user_id == user.id).first()
    # 13 credits x 250 = 3250, + 310 fees, - 1500 deductions = 2060.
    assert abs(row.amount) == 2060.0


def test_a_deduction_never_becomes_income(db, user):
    set_term(db, user)
    account = make_account(db, user.id, "Chequing")
    in_term(db, user, "CPSC 210")

    pay(db, user, account, rate=100.0, deductions=[("Bursary", 100.0)])

    kinds = {
        row.kind for row in
        db.query(TransactionModel).filter(TransactionModel.user_id == user.id).all()
    }
    assert kinds == {"expense"}


def test_deductions_beyond_the_bill_are_refused(db, user):
    set_term(db, user)
    account = make_account(db, user.id, "Chequing")
    in_term(db, user, "CPSC 210", credits=3.0)

    with pytest.raises(ValueError, match="more than"):
        pay(db, user, account, rate=100.0, deductions=[("Huge scholarship", 5000.0)])


def test_a_payment_that_nets_to_nothing_is_refused(db, user):
    set_term(db, user)
    account = make_account(db, user.id, "Chequing")
    in_term(db, user, "CPSC 210", credits=3.0)

    with pytest.raises(ValueError, match="nothing"):
        pay(db, user, account, rate=100.0, deductions=[("Full ride", 300.0)])


# ----------------------------------------------------------- the credits --

def test_transfer_credits_are_not_billed(db, user):
    """Credit granted without taking the course carries no tuition."""
    set_term(db, user)
    in_term(db, user, "CPSC 210", credits=4.0)
    in_term(db, user, "HIST 102", credits=3.0, transfer_credit=True)

    assert [c.code for c in billable_courses(db, user.id)] == ["CPSC 210"]

    preview = preview_tuition(db, user.id, cost_per_credit=250.0, fees=0.0, deductions_total=0.0)
    assert preview.credits_counted == 4.0
    assert preview.gross == 1000.0


def test_only_the_current_term_is_billed(db, user):
    set_term(db, user, year=3, semester="Fall")
    in_term(db, user, "CPSC 210", credits=4.0)
    make_course(db, user.id, "OLD 100", credits=3.0, year=2, semester="Fall")
    make_course(db, user.id, "NEXT 100", credits=3.0, year=4, semester="Fall")

    assert [c.code for c in billable_courses(db, user.id)] == ["CPSC 210"]


# ------------------------------------------------------------ instalments --

def test_two_instalments_sum_their_rates(db, user):
    """Half the rate entered twice is the whole rate, not two separate bills."""
    set_term(db, user)
    account = make_account(db, user.id, "Chequing")
    course = in_term(db, user, "CPSC 210", credits=4.0)

    pay(db, user, account, rate=125.0)
    pay(db, user, account, rate=125.0)

    cost = course_cost(db, user.id, course.id)
    assert cost.cost_per_credit == 250.0
    assert cost.tuition_share == 1000.0


def test_the_form_says_what_is_already_recorded(db, user):
    set_term(db, user)
    account = make_account(db, user.id, "Chequing")
    in_term(db, user, "CPSC 210", credits=4.0)
    pay(db, user, account, rate=125.0)

    preview = preview_tuition(db, user.id, cost_per_credit=125.0, fees=0.0, deductions_total=0.0)
    assert preview.already_recorded_per_credit == 125.0


def test_credits_counted_is_history_not_a_recomputation(db, user):
    """What the bill was for does not change when a course is added later."""
    set_term(db, user)
    account = make_account(db, user.id, "Chequing")
    in_term(db, user, "CPSC 210", credits=4.0)

    payment = pay(db, user, account, rate=250.0)
    assert payment.credits_counted == 4.0

    in_term(db, user, "LATE 200", credits=3.0)
    db.refresh(payment)
    assert payment.credits_counted == 4.0


# ---------------------------------------------------------- course cost --

def test_course_cost_is_gross_and_ignores_deductions(db, user):
    """A scholarship reduces what you pay, not what the course is worth."""
    set_term(db, user)
    account = make_account(db, user.id, "Chequing")
    course = in_term(db, user, "CPSC 210", credits=4.0)
    in_term(db, user, "MATH 200", credits=3.0)

    pay(db, user, account, rate=250.0, fees=310.0, deductions=[("Scholarship", 1500.0)])

    cost = course_cost(db, user.id, course.id)
    # 4 credits x 250, untouched by the scholarship and carrying none of the fees.
    assert cost.tuition_share == 1000.0
    assert cost.total == 1000.0


def test_course_cost_is_proportional_to_credits(db, user):
    set_term(db, user)
    account = make_account(db, user.id, "Chequing")
    big = in_term(db, user, "CPSC 210", credits=4.0)
    small = in_term(db, user, "SEMI 100", credits=1.0)

    pay(db, user, account, rate=250.0)

    assert course_cost(db, user.id, big.id).tuition_share == 1000.0
    assert course_cost(db, user.id, small.id).tuition_share == 250.0


def test_fees_reach_no_course(db, user):
    """A U-Pass is not a cost of CPSC 210."""
    set_term(db, user)
    account = make_account(db, user.id, "Chequing")
    course = in_term(db, user, "CPSC 210", credits=4.0)

    pay(db, user, account, rate=0.0, fees=310.0)

    assert course_cost(db, user.id, course.id).total == 0.0


def test_materials_tagged_to_a_course_are_counted(db, user):
    import datetime
    set_term(db, user)
    account = make_account(db, user.id, "Chequing")
    books = make_category(db, user.id, "Textbooks")
    course = in_term(db, user, "CPSC 210", credits=4.0)

    create_transaction(db, user.id, TransactionCreate(
        kind=TransactionKind.EXPENSE, account_id=account.id, amount=89.0,
        description="Textbook", occurred_on=datetime.date(2026, 9, 3),
        category_id=books.id, course_id=course.id,
    ))

    cost = course_cost(db, user.id, course.id)
    assert cost.materials_total == 89.0
    assert cost.materials[0].label == "Textbooks"
    assert cost.total == 89.0


def test_a_course_with_no_tuition_payment_shows_materials_only(db, user):
    import datetime
    set_term(db, user)
    account = make_account(db, user.id, "Chequing")
    course = in_term(db, user, "CPSC 210", credits=4.0)

    create_transaction(db, user.id, TransactionCreate(
        kind=TransactionKind.EXPENSE, account_id=account.id, amount=24.5,
        description="Lab manual", occurred_on=datetime.date(2026, 9, 3),
        course_id=course.id,
    ))

    cost = course_cost(db, user.id, course.id)
    assert cost.tuition_share == 0.0
    assert cost.total == 24.5


# ------------------------------------------------------- the course guard --

def test_a_course_belonging_to_someone_else_is_refused(db, user):
    """The id arrives from the client; another user's would otherwise be stored."""
    import datetime
    from conftest import make_user

    account = make_account(db, user.id, "Chequing")
    stranger = make_user(db, "stranger@test.local")
    theirs = make_course(db, stranger.id, "SECRET 101")

    with pytest.raises(ValueError, match="course does not exist"):
        create_transaction(db, user.id, TransactionCreate(
            kind=TransactionKind.EXPENSE, account_id=account.id, amount=10.0,
            description="Nope", occurred_on=datetime.date(2026, 9, 3),
            course_id=theirs.id,
        ))


def test_course_id_is_cleared_on_income(db, user):
    """A course says what money went on, which only makes sense going out."""
    import datetime
    account = make_account(db, user.id, "Chequing")
    course = make_course(db, user.id, "CPSC 210")

    result = create_transaction(db, user.id, TransactionCreate(
        kind=TransactionKind.INCOME, account_id=account.id, amount=500.0,
        description="Paycheque", occurred_on=datetime.date(2026, 9, 3),
        course_id=course.id,
    ))

    assert result.course_id is None


def test_course_cost_ignores_income_tagged_rows(db, user):
    """Belt and braces: even if a tagged income row existed, it is not a cost."""
    import datetime
    set_term(db, user)
    account = make_account(db, user.id, "Chequing")
    course = in_term(db, user, "CPSC 210", credits=4.0)

    create_transaction(db, user.id, TransactionCreate(
        kind=TransactionKind.EXPENSE, account_id=account.id, amount=89.0,
        description="Textbook", occurred_on=datetime.date(2026, 9, 3),
        course_id=course.id,
    ))
    # Written straight to the table, bypassing the service's clearing rule.
    db.add(TransactionModel(
        id=uuid.uuid4(), user_id=user.id, account_id=account.id, kind="income",
        amount=50.0, description="Refund", occurred_on=datetime.date(2026, 9, 4),
        course_id=course.id,
    ))
    db.commit()

    assert course_cost(db, user.id, course.id).materials_total == 89.0
