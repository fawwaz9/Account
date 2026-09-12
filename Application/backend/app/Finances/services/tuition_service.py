"""Recording a tuition payment, and answering what a course cost.

Two questions that look like one and are not:

- *What left my account?* One expense: credits times the rate, plus fees, less
  every deduction. That is the ledger, and it is a single line.
- *What did this course cost?* Its credits times the rate, gross. A scholarship
  reduces what you pay, not what the course is worth.

The two do not reconcile and must not be made to. A term at $250/credit over 13
credits with $310 of fees and $1,500 of deductions is one $2,060 ledger line and
$3,250 spread across four course pages. Both are right.
"""

import uuid
from datetime import date

from sqlalchemy.orm import Session

from app._database.models import (
    CourseModel,
    SpendCategoryModel,
    TransactionModel,
    TuitionDeductionModel,
    TuitionPaymentModel,
    UserModel,
)
from app.Finances.schemas.transaction import TransactionCreate, TransactionKind
from app.Finances.schemas.budget import CategorySpend, TermBudget
from app.Finances.schemas.tuition import (
    CourseCost,
    CourseCostLine,
    TuitionCourse,
    TuitionCreate,
    TuitionPreview,
    TuitionUpdate,
)
from app.Finances.services.transaction_service import (
    create_transaction,
    delete_transaction,
    owned_account,
)
from app.Grades.utils.terms import CURRENT, term_bucket


def current_term(db: Session, user_id: uuid.UUID) -> tuple[int | None, str | None]:
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None, None
    return user.current_school_year, user.current_semester


def term_name(db: Session, user_id: uuid.UUID) -> str:
    """A term as a person would write it.

    school_year is a year of standing, not a calendar year, so pasting it in
    front of the semester produced "3 Fall". The user's own term_label ("2025-
    2026") is the right thing when they have set one; failing that the semester
    alone reads better than a bare ordinal.
    """
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None or not user.current_semester:
        return "your current term"
    if user.term_label:
        return f"{user.current_semester} {user.term_label}"
    return user.current_semester


def billable_courses(db: Session, user_id: uuid.UUID) -> list[CourseModel]:
    """The current term's courses that tuition is actually charged for.

    Transfer credits are excluded: credit granted without taking the course
    carries no tuition, so counting it would inflate the bill by a course that
    was never paid for.
    """
    school_year, semester = current_term(db, user_id)
    courses = (
        db.query(CourseModel)
        .filter(CourseModel.user_id == user_id)
        .order_by(CourseModel.code)
        .all()
    )
    return [
        course for course in courses
        if not course.transfer_credit
        and term_bucket(course, school_year, semester) == CURRENT
    ]


def recorded_rate(db: Session, user_id: uuid.UUID, school_year, semester) -> float:
    """Per-credit rate already recorded for a term.

    Instalments are additive: half the rate entered twice is the whole rate. This
    is what lets the form say so, rather than leaving it as a trap that silently
    doubles every course's cost.
    """
    rows = (
        db.query(TuitionPaymentModel)
        .filter(
            TuitionPaymentModel.user_id == user_id,
            TuitionPaymentModel.school_year == school_year,
            TuitionPaymentModel.semester == semester,
        )
        .all()
    )
    return round(sum(row.cost_per_credit for row in rows), 2)


def preview_tuition(
    db: Session,
    user_id: uuid.UUID,
    cost_per_credit: float,
    fees: float,
    deductions_total: float,
) -> TuitionPreview:
    school_year, semester = current_term(db, user_id)
    courses = billable_courses(db, user_id)

    credits_counted = round(sum(course.credits for course in courses), 2)
    gross = round(credits_counted * cost_per_credit, 2)
    payable = round(gross + fees - deductions_total, 2)

    preview = TuitionPreview(
        school_year=school_year,
        semester=semester,
        courses=[
            TuitionCourse(
                course_id=course.id,
                code=course.code,
                name=course.name,
                credits=course.credits,
                share=round(course.credits * cost_per_credit, 2),
            )
            for course in courses
        ],
        credits_counted=credits_counted,
        cost_per_credit=cost_per_credit,
        gross=gross,
        fees=round(fees, 2),
        deductions_total=round(deductions_total, 2),
        payable=payable,
        already_recorded_per_credit=recorded_rate(db, user_id, school_year, semester),
        term_name=term_name(db, user_id),
    )

    if not courses and cost_per_credit > 0:
        preview.can_record = False
        preview.reason = (
            "No courses in your current term to charge per-credit tuition against. "
            "Add them, or set your term in Settings."
        )
    elif payable < 0:
        preview.can_record = False
        preview.reason = (
            f"Deductions come to {deductions_total:.2f}, more than the "
            f"{gross + fees:.2f} being billed."
        )

    return preview


def record_tuition(db: Session, user_id: uuid.UUID, data: TuitionCreate):
    """One ledger row, plus the record of what it was made of."""
    if owned_account(db, user_id, data.account_id) is None:
        raise ValueError("That account does not exist")

    deductions_total = round(sum(entry.amount for entry in data.deductions), 2)
    preview = preview_tuition(
        db, user_id, data.cost_per_credit, data.fees, deductions_total
    )
    if not preview.can_record:
        raise ValueError(preview.reason or "That tuition payment cannot be recorded")

    if preview.payable == 0:
        raise ValueError("That payment comes to nothing once deductions are applied")

    school_year, semester = preview.school_year, preview.semester
    label = data.description or f"Tuition {term_name(db, user_id)}"

    # One line, fees folded in, deductions already off. The deductions are not
    # income -- that money never entered the account -- so they never become
    # rows of their own; they live on the payment record instead.
    transaction = create_transaction(db, user_id, TransactionCreate(
        kind=TransactionKind.EXPENSE,
        account_id=data.account_id,
        amount=preview.payable,
        description=label,
        occurred_on=data.occurred_on,
        category_id=None,
        # Deliberately unset: this covers a whole term, and what it cost each
        # course is answered from the rate, not from the ledger.
        course_id=None,
    ))
    if transaction is None:
        raise ValueError("That account does not exist")

    payment = TuitionPaymentModel(
        id=uuid.uuid4(),
        user_id=user_id,
        transaction_id=transaction.id,
        school_year=school_year,
        semester=semester,
        cost_per_credit=data.cost_per_credit,
        fees=data.fees,
        credits_counted=preview.credits_counted,
        occurred_on=data.occurred_on,
    )
    db.add(payment)
    db.flush()

    for entry in data.deductions:
        db.add(TuitionDeductionModel(
            id=uuid.uuid4(),
            tuition_payment_id=payment.id,
            description=entry.description,
            amount=entry.amount,
        ))

    db.commit()
    db.refresh(payment)
    return payment


def course_cost(db: Session, user_id: uuid.UUID, course_id: uuid.UUID) -> CourseCost | None:
    """What one course cost: its share of tuition, plus anything bought for it."""
    course = (
        db.query(CourseModel)
        .filter(CourseModel.id == course_id, CourseModel.user_id == user_id)
        .first()
    )
    if course is None:
        return None

    # Gross, and the rate is summed across the term's instalments.
    rate = 0.0
    if not course.transfer_credit:
        rate = recorded_rate(db, user_id, course.year, course.semester)
    tuition_share = round(rate * course.credits, 2)

    rows = (
        db.query(TransactionModel)
        .filter(
            TransactionModel.user_id == user_id,
            TransactionModel.course_id == course_id,
            TransactionModel.kind == TransactionKind.EXPENSE.value,
        )
        .all()
    )
    names = {
        category.id: category.name
        for category in db.query(SpendCategoryModel)
        .filter(SpendCategoryModel.user_id == user_id)
        .all()
    }
    by_label: dict[str, float] = {}
    for row in rows:
        label = names.get(row.category_id, "Uncategorised")
        by_label[label] = round(by_label.get(label, 0.0) + abs(row.amount), 2)

    materials = [
        CourseCostLine(label=label, amount=amount)
        for label, amount in sorted(by_label.items(), key=lambda pair: -pair[1])
    ]
    materials_total = round(sum(line.amount for line in materials), 2)

    return CourseCost(
        course_id=course.id,
        credits=course.credits,
        cost_per_credit=rate,
        tuition_share=tuition_share,
        materials=materials,
        materials_total=materials_total,
        total=round(tuition_share + materials_total, 2),
    )


def get_tuition(db: Session, user_id: uuid.UUID, payment_id: uuid.UUID):
    return (
        db.query(TuitionPaymentModel)
        .filter(
            TuitionPaymentModel.id == payment_id,
            TuitionPaymentModel.user_id == user_id,
        )
        .first()
    )


def update_tuition(db: Session, user_id: uuid.UUID, payment_id: uuid.UUID, data: TuitionUpdate):
    """Correct a payment, and move its ledger row to match.

    The two are one thing: the rate is what the course pages read and the net is
    what the ledger shows, so a correction that changed one without the other
    would leave them disagreeing with no way to tell which was right.
    """
    payment = get_tuition(db, user_id, payment_id)
    if payment is None:
        return None

    if owned_account(db, user_id, data.account_id) is None:
        raise ValueError("That account does not exist")

    deductions_total = round(sum(entry.amount for entry in data.deductions), 2)

    # credits_counted is history unless the caller asks to re-count. A payment
    # recorded before a course was added should not silently start billing for
    # it just because a typo in the fees was fixed.
    credits_counted = payment.credits_counted
    if data.recount_credits:
        credits_counted = round(
            sum(course.credits for course in billable_courses(db, user_id)), 2
        )

    gross = round(credits_counted * data.cost_per_credit, 2)
    payable = round(gross + data.fees - deductions_total, 2)

    if payable < 0:
        raise ValueError(
            f"Deductions come to {deductions_total:.2f}, more than the "
            f"{gross + data.fees:.2f} being billed."
        )
    if payable == 0:
        raise ValueError("That payment comes to nothing once deductions are applied")

    transaction = (
        db.query(TransactionModel)
        .filter(
            TransactionModel.id == payment.transaction_id,
            TransactionModel.user_id == user_id,
        )
        .first()
    )
    if transaction is None:
        raise ValueError("The ledger row for this payment is missing")

    # Expenses are stored negative, so the sign is reapplied rather than assumed.
    transaction.amount = -abs(payable)
    transaction.account_id = data.account_id
    transaction.occurred_on = data.occurred_on
    transaction.description = data.description or f"Tuition {term_name(db, user_id)}"

    # The account lives on the transaction, which is the thing that moved money.
    payment.cost_per_credit = data.cost_per_credit
    payment.fees = data.fees
    payment.credits_counted = credits_counted
    payment.occurred_on = data.occurred_on

    # Replaced wholesale rather than diffed: the list is short, and matching old
    # rows to new ones by description would guess wrong the moment one is renamed.
    db.query(TuitionDeductionModel).filter(
        TuitionDeductionModel.tuition_payment_id == payment.id
    ).delete(synchronize_session=False)
    for entry in data.deductions:
        db.add(TuitionDeductionModel(
            id=uuid.uuid4(),
            tuition_payment_id=payment.id,
            description=entry.description,
            amount=entry.amount,
        ))

    db.commit()
    db.refresh(payment)
    return payment


def delete_tuition(db: Session, user_id: uuid.UUID, payment_id: uuid.UUID):
    """Remove a payment and the ledger row it owns.

    Deleting through the transaction works too -- that path clears the payment
    record -- but a tuition payment is the thing the student thinks they are
    deleting, so it can be addressed directly.
    """
    payment = get_tuition(db, user_id, payment_id)
    if payment is None:
        return None

    transaction_id = payment.transaction_id
    db.query(TuitionDeductionModel).filter(
        TuitionDeductionModel.tuition_payment_id == payment.id
    ).delete(synchronize_session=False)
    db.delete(payment)
    db.commit()

    # After the payment is gone, so the cascade in delete_transaction finds
    # nothing left to remove and cannot recurse.
    delete_transaction(db, user_id, transaction_id, scope="row")
    return True


def term_span(courses) -> tuple[date | None, date | None]:
    """The dates a term actually runs, taken from the courses in it.

    Grades is the only part of the app that knows when a term starts and stops,
    and it knows it per course rather than centrally -- so the span is the
    earliest start and the latest end across the term. A year-long course
    stretches it, which is correct: that is genuinely how long you are paying
    for those books.

    Courses with no dates contribute nothing rather than defaulting to today,
    which would quietly shrink the span to nothing.
    """
    starts = [c.start_date for c in courses if c.start_date]
    ends = [c.end_date for c in courses if c.end_date]
    if not starts or not ends:
        return None, None
    return min(starts), max(ends)


def term_budget(db: Session, user_id: uuid.UUID, today: date | None = None) -> TermBudget:
    """What the current term has cost, over the term's own dates.

    A calendar month is the wrong unit for a student: tuition lands once,
    textbooks land in the first fortnight, and neither is a monthly rhythm.
    """
    today = today or date.today()
    courses = billable_courses(db, user_id)
    dated = [c for c in courses if c.start_date and c.end_date]
    starts_on, ends_on = term_span(courses)

    budget = TermBudget(
        term_name=term_name(db, user_id),
        starts_on=starts_on,
        ends_on=ends_on,
        dated_courses=len(dated),
        undated_courses=len(courses) - len(dated),
    )

    if starts_on is None or ends_on is None:
        budget.reason = (
            "No course in this term has start and end dates, so there is no term "
            "to measure. Add them when editing a course."
            if courses else
            "No courses in your current term. Add them, or set your term in Settings."
        )
        return budget

    budget.can_measure = True
    budget.days_total = (ends_on - starts_on).days + 1
    # Clamped, so a term not started reads 0 and a finished one reads its whole
    # length rather than counting on past the end.
    budget.days_elapsed = max(0, min((today - starts_on).days + 1, budget.days_total))

    rows = (
        db.query(TransactionModel)
        .filter(
            TransactionModel.user_id == user_id,
            TransactionModel.occurred_on >= starts_on,
            TransactionModel.occurred_on <= ends_on,
            # Transfers move money between pots without spending it, so counting
            # them would double the total and call a savings top-up an expense.
            TransactionModel.kind != TransactionKind.TRANSFER.value,
        )
        .all()
    )

    spent = sum(abs(r.amount) for r in rows if r.kind == TransactionKind.EXPENSE.value)
    received = sum(abs(r.amount) for r in rows if r.kind == TransactionKind.INCOME.value)
    course_ids = {c.id for c in courses}
    on_courses = sum(
        abs(r.amount) for r in rows
        if r.kind == TransactionKind.EXPENSE.value and r.course_id in course_ids
    )

    names = {
        category.id: category.name
        for category in db.query(SpendCategoryModel)
        .filter(SpendCategoryModel.user_id == user_id)
        .all()
    }
    by_label: dict[str, float] = {}
    for row in rows:
        if row.kind != TransactionKind.EXPENSE.value:
            continue
        label = names.get(row.category_id, "Uncategorised")
        by_label[label] = round(by_label.get(label, 0.0) + abs(row.amount), 2)

    budget.spent = round(spent, 2)
    budget.received = round(received, 2)
    budget.net = round(received - spent, 2)
    budget.on_courses = round(on_courses, 2)
    budget.by_category = [
        CategorySpend(category_id=None, category_name=label, actual=amount)
        for label, amount in sorted(by_label.items(), key=lambda pair: -pair[1])
    ]
    return budget
