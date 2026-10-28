"""Service functions for tuition payments, what each course cost, and the term budget.

Two questions that look like one: what left the account (one expense: credits
times the rate, plus fees, less deductions) and what a course cost (its credits
times the rate, gross, since a scholarship lowers what was paid, not what the
course is worth). They are not meant to reconcile. A payment and its ledger row
are deleted together from either side.
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
from app.Grades.utils.terms import CURRENT, calendar_year_of, term_bucket, term_dates
from app.shared.dates import user_today
from app.Finances.services.counted import on_counted_accounts


def current_term(db: Session, user_id: uuid.UUID) -> tuple[int | None, str | None]:
    """Return the user's current school year and semester, or (None, None).

    Args:
        db: Open database session.
        user_id: Owner of the rows.

    Returns:
        (school year, semester) from the user's academic status; either may be None.
    """
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None:
        return None, None
    return user.current_school_year, user.current_semester


def term_name(db: Session, user_id: uuid.UUID) -> str:
    """Return the current term as a person would write it, such as "Fall 2026-2027".

    Derived from the first-year anchor rather than the free-text `term_label`, which
    nothing keeps current; the label is the fallback when no anchor is set.

    Args:
        db: Open database session.
        user_id: Whose term.

    Returns:
        The name; "your current term" when the user or their semester is unset.
    """
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    if user is None or not user.current_semester:
        return "your current term"

    began = calendar_year_of(user.current_school_year, user.first_year_calendar_year)
    if began is not None:
        return f"{user.current_semester} {began}-{began + 1}"

    if user.term_label:
        return f"{user.current_semester} {user.term_label}"
    return user.current_semester


def billable_courses(db: Session, user_id: uuid.UUID) -> list[CourseModel]:
    """Return the current term's courses tuition is charged for, by code.

    Transfer credits are left out: they carry no tuition.

    Args:
        db: Open database session.
        user_id: Whose courses.

    Returns:
        The course rows; empty when the current term has none.
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
    """Return the per-credit rate already recorded for a term, summed across payments.

    Instalments are additive: half the rate entered twice is the whole rate.

    Args:
        db: Open database session.
        user_id: Whose payments.
        school_year: The term's school year.
        semester: The term's semester.

    Returns:
        The summed rate, rounded to cents; 0 when nothing is recorded.
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
    """Return the arithmetic of a tuition payment for the current term, writing nothing.

    Args:
        db: Open database session.
        user_id: Whose courses.
        cost_per_credit: The rate, in dollars.
        fees: Fees belonging to no course.
        deductions_total: The deductions, summed.

    Returns:
        The preview; `can_record` is False when a rate is given with no billable
        courses, or the deductions exceed the bill.
    """
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
    """Record a tuition payment: one expense row plus the record of what it was made of.

    The row is written through `create_transaction`, which commits it, and the
    payment and its deductions are committed after it.

    Args:
        db: Open database session.
        user_id: Whose payment.
        data: The account, date, rate, fees, description and deductions.

    Returns:
        The payment row.

    Raises:
        ValueError: If the account is not the user's, the preview cannot be
            recorded, or the payment comes to nothing after deductions.
    """
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
    """Return what a course cost: its gross tuition share plus what was bought for it.

    Args:
        db: Open database session.
        user_id: Whose course.
        course_id: The course.

    Returns:
        The cost, with expenses tagged to the course on counted accounts by
        category; None when the course is not the user's.
    """
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
            on_counted_accounts(user_id),  # D39
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
    """Return the user's tuition payment row with this id, or None.

    Args:
        db: Open database session.
        user_id: Owner of the rows.
        payment_id: The payment to fetch.

    Returns:
        The payment row, or None when it is missing or another user's.
    """
    return (
        db.query(TuitionPaymentModel)
        .filter(
            TuitionPaymentModel.id == payment_id,
            TuitionPaymentModel.user_id == user_id,
        )
        .first()
    )


def update_tuition(db: Session, user_id: uuid.UUID, payment_id: uuid.UUID, data: TuitionUpdate):
    """Correct a tuition payment and move its ledger row to match.

    The credits billed stay as recorded unless `recount_credits` is set; the
    deductions are replaced. One commit.

    Args:
        db: Open database session.
        user_id: Whose payment.
        payment_id: The payment.
        data: The full corrected payment.

    Returns:
        The updated payment row; None when it is not the user's.

    Raises:
        ValueError: If the account is not the user's, the deductions exceed the
            bill, the payment comes to nothing, or its ledger row is missing.
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
    """Delete a tuition payment and the ledger row it owns.

    Two commits: the payment and its deductions first, then the row through
    `delete_transaction`.

    Args:
        db: Open database session.
        user_id: Whose payment.
        payment_id: The payment.

    Returns:
        True when deleted; None when it is not the user's.
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


def term_span(courses, first_year: int | None) -> tuple[date | None, date | None]:
    """Return the dates the term runs, from the term itself rather than its courses.

    The span is the term's fixed months (Fall is September to December), widest
    across the courses given, which is slightly wider than the teaching weeks.

    Args:
        courses: The term's courses.
        first_year: The calendar year school year 1 began; None means no dates.

    Returns:
        (start, end), or (None, None) when no course's term can be dated.
    """
    terms = {
        dates
        for course in courses
        if (dates := term_dates(course.semester, course.year, first_year)) is not None
    }
    if not terms:
        return None, None

    # A term's courses should all resolve to the same span, but a student with
    # courses from two terms in "current" would give several. Widest wins, which
    # is the same answer the old per-course min/max gave.
    return min(start for start, _ in terms), max(end for _, end in terms)


def term_budget(db: Session, user_id: uuid.UUID, today: date | None = None) -> TermBudget:
    """Return what the current term has cost, over the term's own dates.

    Income and expenses on counted accounts dated in the term count; transfers do
    not.

    Args:
        db: Open database session.
        user_id: Whose money.
        today: The day that decides how far through the term it is; defaults to
            the user's today.

    Returns:
        The term budget; when the term has no dates, `can_measure` is False and
        `reason` says what to set.
    """
    today = today or user_today(db, user_id)
    courses = billable_courses(db, user_id)
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    first_year = user.first_year_calendar_year if user else None
    dated = [c for c in courses if c.start_date and c.end_date]
    starts_on, ends_on = term_span(courses, first_year)

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
            "to measure. Set the year your first year began, in Settings."
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
            on_counted_accounts(user_id),  # D39
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
