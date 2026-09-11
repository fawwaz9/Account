import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Float, Boolean, Integer, ForeignKey, Date, DateTime, Time, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import Uuid
from app._database.db import Base

cascade = "all, delete-orphan"


def utc_now() -> datetime:
    """Now, in UTC, stored naive to match every DateTime column here.

    `datetime.utcnow()` does the same thing but is deprecated, and the
    timezone-aware value on its own would land an offset in a naive column and
    make two rows written the same way compare unequal.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)

class UserModel(Base):
    __tablename__ = "users"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    google_id = Column(String, nullable=True, unique=True)
    # bcrypt hash for the local provider; NULL for Google-authenticated
    # users, who have no password of ours to check.
    password_hash = Column(String, nullable=True)
    # How the account was first created. Once providers are linked, use the
    # has_* properties below to ask what the account can actually sign in with.
    auth_provider = Column(String, nullable=False, default="google")
    # True once an identity provider has vouched for the address. Google sets
    # it; local signup cannot, since there is no verification email yet.
    email_verified = Column(Boolean, nullable=False, default=False)
    # UserPreferences as JSON. Previously the schema declared preferences with
    # no column behind it, so update_user's setattr loop wrote to a non-mapped
    # attribute and every change was silently dropped on commit.
    preferences = Column(JSON, nullable=False, default=dict)
    # Bumped to invalidate every session outstanding at that moment. Each token
    # carries the epoch it was minted under, and a mismatch is refused.
    #
    # A counter rather than a timestamp, and rather than a jti denylist: comparing
    # a token's `iat` against a revocation *time* cannot tell a token minted just
    # before the revocation from one minted just after it, because `iat` has
    # whole-second granularity -- so signing straight back in could be refused.
    # Integer equality has no such ambiguity, no timezone handling and nothing to
    # prune. There is no per-device session list to revoke from selectively, and
    # what is actually needed is "invalidate everything outstanding".
    session_epoch = Column(Integer, nullable=False, default=0, server_default="0")

    # Which term the student is in right now. Everything past/current/future on
    # the grades page is decided by comparing a course against these.
    current_school_year = Column(Integer, nullable=True)
    current_semester = Column(String, nullable=True)
    term_label = Column(String, nullable=True)

    courses = relationship("CourseModel", back_populates="user", cascade=cascade)
    accounts = relationship("AccountModel", back_populates="user", cascade=cascade)

    @property
    def has_password(self) -> bool:
        return self.password_hash is not None

    @property
    def has_google(self) -> bool:
        return self.google_id is not None


class CourseModel(Base):
    __tablename__ = "courses"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    code = Column(String, nullable=False)
    name = Column(String, nullable=False)
    semester = Column(String, nullable=False)
    year = Column(Integer, nullable=False)
    credits = Column(Float, default=3.0)
    required = Column(Boolean, default=True)
    professor = Column(String)
    final_grade = Column(Float, default=0.0)
    # What you are aiming for in this course. Null falls back to the account
    # default, so a new course is measured against something without you
    # having to fill it in.
    target_grade = Column(Float, nullable=True)
    average = Column(Float, default=0.0)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    # Three flags that each remove the course from a rule it would otherwise
    # fall under. Kept as flags rather than a status enum because they are
    # independent: a transfer credit can also be archived.
    #
    #: No final exam, so "finished but no final grade recorded" is not a problem
    #: to act on and the course stops appearing in Attention.
    no_final = Column(Boolean, nullable=False, default=False)
    #: Credit granted without taking the course. It contributes credits and
    #: nothing else -- no score is recorded, so it stays out of every average.
    transfer_credit = Column(Boolean, nullable=False, default=False)
    #: Still searchable and still counted in the credit-weighted average, but no
    #: longer counted toward credits completed.
    archived = Column(Boolean, nullable=False, default=False)

    user = relationship("UserModel", back_populates="courses")
    grades = relationship("GradeModel", back_populates="course", cascade=cascade)
    category_weight_rows = relationship(
        "CourseCategoryWeightModel", back_populates="course", cascade=cascade
    )
    events = relationship("EventModel", back_populates="course", cascade=cascade)
    tasks = relationship("TaskModel", back_populates="course", cascade=cascade)

    @property
    def category_weights(self) -> dict[str, float]:
        return {cw.category: cw.weight for cw in self.category_weight_rows}


class CourseCategoryWeightModel(Base):
    __tablename__ = "course_category_weights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(Uuid, ForeignKey("courses.id"), nullable=False)
    category = Column(String, nullable=False)
    weight = Column(Float, nullable=False, default=0.0)

    course = relationship("CourseModel", back_populates="category_weight_rows")

class GradeModel(Base):
    __tablename__ = "grades"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    course_id = Column(Uuid, ForeignKey("courses.id"), nullable=False)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)
    score = Column(Float, nullable=True)
    max_score = Column(Float, nullable=False)
    weight = Column(Float, default=0.0)
    #: When the work is due, as opposed to when it was marked. A grade that has
    #: one raises a task automatically, and that task closes when the score
    #: lands.
    due_date = Column(Date, nullable=True)

    course = relationship("CourseModel", back_populates="grades")
    tasks = relationship("TaskModel", back_populates="grade", cascade=cascade)

class AccountModel(Base):
    """One pot money sits in.

    Seeded with the four from the project notes -- Spending, Savings,
    Investments, Emergency -- but a row rather than an enum, so a fifth pot
    later is data instead of a migration.
    """

    __tablename__ = "accounts"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    #: spending | savings | investment | emergency | other -- drives styling and
    #: sensible defaults, not behaviour.
    kind = Column(String, nullable=False, default="spending")
    #: Share of incoming money this account takes by default, as a percentage.
    income_share = Column(Float, nullable=False, default=0.0)
    #: Archived accounts keep their history but stop being offered.
    archived = Column(Boolean, nullable=False, default=False)
    position = Column(Integer, nullable=False, default=0)

    user = relationship("UserModel", back_populates="accounts")
    transactions = relationship(
        "TransactionModel", back_populates="account", cascade=cascade
    )


class TransactionModel(Base):
    """A single movement of money.

    `amount` is signed: positive is money into the account, negative is out. A
    balance is then just the sum of its rows, and a transfer is two rows that
    cancel each other -- no special case in the arithmetic.
    """

    __tablename__ = "transactions"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    account_id = Column(Uuid, ForeignKey("accounts.id"), nullable=False)
    #: income | expense | transfer
    kind = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    description = Column(String)
    occurred_on = Column(Date, nullable=False)
    #: Ties the two halves of a transfer together so they can be shown, edited
    #: and deleted as one event.
    group_id = Column(Uuid, nullable=True)
    #: What the money went on, as opposed to which pot it came from. Only
    #: meaningful for expenses, so nullable.
    category_id = Column(Uuid, ForeignKey("spend_categories.id"), nullable=True)
    #: Set when a standing instruction generated this row. Together with
    #: `occurred_on` it is what stops the same payment being written twice, and
    #: it is a separate column from `group_id` on purpose: that one already
    #: carries two meanings and must not take a third.
    recurring_id = Column(Uuid, ForeignKey("recurring_transactions.id"), nullable=True)

    account = relationship("AccountModel", back_populates="transactions")
    category = relationship("SpendCategoryModel", back_populates="transactions")
    recurring = relationship("RecurringTransactionModel", back_populates="transactions")


class SpendCategoryModel(Base):
    """What money was spent on -- groceries, rent -- as opposed to which pot paid.

    User-defined rather than an enum, for the same reason accounts are.
    """

    __tablename__ = "spend_categories"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    archived = Column(Boolean, nullable=False, default=False)
    position = Column(Integer, nullable=False, default=0)

    transactions = relationship("TransactionModel", back_populates="category")


class BudgetTargetModel(Base):
    """What one account is allowed to spend in one month."""

    __tablename__ = "budget_targets"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    account_id = Column(Uuid, ForeignKey("accounts.id"), nullable=False)
    #: Always the first of the month, normalized on the way in so a month is
    #: one value rather than any of twenty-eight.
    month = Column(Date, nullable=False)
    planned_amount = Column(Float, nullable=False, default=0.0)


class EventModel(Base):
    """Something that happens on a date, optionally repeating.

    One table serves class times, midterms, finals and anything you put on the
    calendar yourself, because they differ only by `kind` and by which course
    they hang off. Recurring payments and repeating tasks are meant to land here
    too rather than growing their own schedulers.

    A repeat is stored as the rule that generates it -- never as rows. Writing
    out a term of lectures would mean thirty-six rows to keep in step every time
    a room changes, and no way to answer "does this repeat?" without counting
    them. Occurrences are materialised on read, for the window asked for.
    """

    __tablename__ = "events"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    #: Set when the event belongs to a course -- a lecture, a lab, a midterm.
    #: Null for anything personal.
    course_id = Column(Uuid, ForeignKey("courses.id"), nullable=True)
    title = Column(String, nullable=False)
    #: lecture | lab | discussion | midterm | final | deadline | personal.
    #: Drives how the card is themed, not what it does.
    kind = Column(String, nullable=False, default="personal")
    location = Column(String, nullable=True)
    notes = Column(String, nullable=True)

    #: A date and two clock times rather than two timestamps. Every date in this
    #: app is a plain local date, and a 10:00 lecture is at 10:00 in the week the
    #: clocks change too. Recurrence then moves the date and leaves the times
    #: alone, which is exactly what a timetable means.
    starts_on = Column(Date, nullable=False)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)

    #: daily | weekly | monthly, or NULL for a one-off.
    recur_freq = Column(String, nullable=True)
    recur_interval = Column(Integer, nullable=False, default=1)
    #: Weekly only: "MO,WE,FR". Empty means "the weekday starts_on falls on".
    recur_byday = Column(String, nullable=True)
    #: Inclusive last date, or a number of occurrences. Never both.
    recur_until = Column(Date, nullable=True)
    recur_count = Column(Integer, nullable=True)
    #: ISO dates the rule would generate but that were cancelled -- reading week,
    #: a lecture that did not happen. Without these, removing one occurrence of a
    #: series could only mean ending the series.
    skipped_dates = Column(JSON, nullable=False, default=list)

    user = relationship("UserModel")
    course = relationship("CourseModel", back_populates="events")


class TaskModel(Base):
    """Something to do, with or without a date.

    Anything carrying a due date also renders on the calendar, so a task and an
    event are two shapes of the same week rather than two separate apps.
    """

    __tablename__ = "tasks"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    #: School work hangs off its course; the course code is then the task's
    #: category, which is why coursework needs no tag of its own.
    course_id = Column(Uuid, ForeignKey("courses.id"), nullable=True)
    #: Set when this task was raised automatically from a dated grade. It closes
    #: itself when that grade's score lands.
    grade_id = Column(Uuid, ForeignKey("grades.id"), nullable=True)
    title = Column(String, nullable=False)
    notes = Column(String, nullable=True)
    due_date = Column(Date, nullable=True)
    due_time = Column(Time, nullable=True)
    #: What you think it will take. Summing these is what turns "7 tasks" into
    #: "23 hours", so a week can be seen to be over-committed in advance.
    estimated_minutes = Column(Integer, nullable=True)
    #: Free-text labels, as a JSON list. Coursework is categorised by its
    #: course code instead.
    tags = Column(JSON, nullable=False, default=list)
    done = Column(Boolean, nullable=False, default=False)
    completed_at = Column(DateTime, nullable=True)
    #: Checked-off tasks archive rather than vanish, so the term's record of what
    #: was actually done survives.
    archived = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    course = relationship("CourseModel", back_populates="tasks")
    grade = relationship("GradeModel", back_populates="tasks")


class RecurringTransactionModel(Base):
    """A standing instruction: rent on the 1st, Spotify on the 14th.

    Stores the rule and a template, never the payments themselves. The same
    recurrence engine that drives class times expands it -- written once, as the
    project notes asked.

    Where this parts company with a calendar event is that its occurrences
    cannot stay virtual. A balance is the sum of its rows, so a payment that has
    actually happened has to *be* a row; and a payment that has not happened yet
    must not be one, or the balance reports money that is still in the account
    as gone. So an occurrence on or before today is materialised into a real
    transaction, exactly once, and an occurrence after today stays a projection
    that only the upcoming-commitments view reads.

    Deliberately not hung off `group_id`. That column already means "transfer
    pair" or "deposit split" depending on `kind`, and a third meaning is what
    the two deposit bugs were made of. Generated rows point back here through
    `transactions.recurring_id` instead, which means one thing only.
    """

    __tablename__ = "recurring_transactions"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    #: income | expense | transfer | deposit -- the same four the money dialog
    #: offers, so a standing instruction can be any of them.
    kind = Column(String, nullable=False)
    #: Which pot. The source for a transfer; null for a deposit, which splits
    #: across every account by income share rather than landing in one.
    account_id = Column(Uuid, ForeignKey("accounts.id"), nullable=True)
    #: Transfers only: where the money goes.
    to_account_id = Column(Uuid, ForeignKey("accounts.id"), nullable=True)
    #: Always positive. The sign is applied when the payment is written, by the
    #: same code that signs a manual one.
    amount = Column(Float, nullable=False)
    description = Column(String, nullable=True)
    #: Expenses only, matching the rule on a one-off expense.
    category_id = Column(Uuid, ForeignKey("spend_categories.id"), nullable=True)

    #: The rule, in the same shape events use, so one engine reads both.
    starts_on = Column(Date, nullable=False)
    recur_freq = Column(String, nullable=False, default="monthly")
    recur_interval = Column(Integer, nullable=False, default=1)
    recur_byday = Column(String, nullable=True)
    recur_until = Column(Date, nullable=True)
    recur_count = Column(Integer, nullable=True)
    #: Dates the rule generates that were cancelled -- a month the subscription
    #: was paused. Without these, skipping one payment could only mean ending
    #: the whole standing instruction.
    skipped_dates = Column(JSON, nullable=False, default=list)

    #: Paused rather than deleted: a cancelled subscription is worth keeping, so
    #: last term's spending still explains itself.
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    account = relationship("AccountModel", foreign_keys=[account_id])
    to_account = relationship("AccountModel", foreign_keys=[to_account_id])
    category = relationship("SpendCategoryModel")
    transactions = relationship("TransactionModel", back_populates="recurring")
