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
from app.Finances.schemas.tuition import (
    CourseCost,
    CourseCostLine,
    TuitionCourse,
    TuitionCreate,
    TuitionPreview,
)
from app.Finances.services.transaction_service import create_transaction, owned_account
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
