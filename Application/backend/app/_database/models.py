import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Float, Boolean, Integer, ForeignKey, Date, DateTime, Time, Index, JSON
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

    #: When deletion was *requested*, not when it happened. Null for a live
    #: account.
    #:
    #: Deletion used to take effect the instant the request landed, which for a
    #: compromised account meant a stolen token could destroy an entire academic
    #: record with no way back. The row and everything under it stay for
    #: DELETION_GRACE_DAYS, and a purge at startup removes what is past that.
    #:
    #: Signing in deliberately still works while this is set: there is no email
    #: system here, so blocking sign-in would make an account no one could ever
    #: restore. The client sees the date and offers to undo it.
    deleted_at = Column(DateTime, nullable=True)

    # Which term the student is in right now. Everything past/current/future on
    # the grades page is decided by comparing a course against these.
    current_school_year = Column(Integer, nullable=True)
    current_semester = Column(String, nullable=True)
    term_label = Column(String, nullable=True)
    #: The calendar year in which **school year 1's** Fall began. With it, every
    #: term in the app has real dates: year N's Fall runs Sep-Dec of
    #: (this + N - 1), and its Winter, Spring and Summer fall in the year after
    #: that. Null means terms have no dates and the app says so rather than
    #: guessing.
    #:
    #: Anchored on year 1 rather than on `current_school_year`, deliberately.
    #: Storing "my current year began in 2025" beside a field the student
    #: advances every September would silently re-date every course in the app
    #: the moment they bumped it. Year 1 never moves.
    first_year_calendar_year = Column(Integer, nullable=True)
    #: When the account was made. NULL for accounts that predate the column:
    #: unknown, and deliberately not guessed -- the analytics that read it
    #: (time to first value) leave those accounts out rather than treat a
    #: backfilled date as a real one.
    created_at = Column(DateTime, nullable=True, default=utc_now)

    # Every table a user directly owns, so "delete my account" removes all of
    # it. Only `courses` and `accounts` were listed here once, which left
    # categories, targets, jobs, reminders and the rest behind as rows belonging
    # to a user who no longer existed -- invisible, because nothing queries by a
    # deleted id. Declaring them lets SQLAlchemy work out the delete order
    # itself rather than this having to hand-sort twenty statements.
    #
    # The rows underneath these cascade from their own parents: grades and
    # category weights from a course, deductions from a payment or cheque,
    # contributions from a fund, snoozes from a task.
    courses = relationship("CourseModel", back_populates="user", cascade=cascade)
    accounts = relationship("AccountModel", back_populates="user", cascade=cascade)
    transactions = relationship("TransactionModel", cascade=cascade, overlaps="account,transactions")
    spend_categories = relationship("SpendCategoryModel", cascade=cascade)
    budget_targets = relationship("BudgetTargetModel", cascade=cascade)
    recurring_transactions = relationship("RecurringTransactionModel", cascade=cascade)
    sinking_funds = relationship("SinkingFundModel", cascade=cascade)
    tuition_payments = relationship("TuitionPaymentModel", cascade=cascade)
    events = relationship("EventModel", back_populates="user", cascade=cascade)
    tasks = relationship("TaskModel", cascade=cascade, overlaps="course,tasks,grade")
    recurring_tasks = relationship("RecurringTaskModel", cascade=cascade)
    reminders = relationship("ReminderModel", cascade=cascade)
    term_blackouts = relationship("TermBlackoutModel", cascade=cascade)
    jobs = relationship("JobModel", cascade=cascade)
    shift_records = relationship("ShiftRecordModel", cascade=cascade, overlaps="job,shift_records")
    paycheques = relationship("PaychequeModel", cascade=cascade, overlaps="job,paycheques")
    usage_events = relationship("UsageEventModel", cascade=cascade)
    push_subscriptions = relationship("PushSubscriptionModel", cascade=cascade)
    survey_responses = relationship("SurveyResponseModel", cascade=cascade)
    imports = relationship("ImportModel", cascade=cascade)
    syllabus_parses = relationship("SyllabusParseModel", cascade=cascade)

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
    #: The section the student is in ("101", "L2B"). Optional, but a syllabus
    #: and a schedule belong to one section, not to the course code, so a
    #: current course without one is called out in Attention.
    section = Column(String, nullable=True)
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
    #: Where this course lives: Canvas, Piazza, a syllabus PDF. A list of
    #: {"title", "url"} objects, ordered as the student arranged them.
    #:
    #: JSON rather than a table because nothing needs to query across links or
    #: reference one on its own -- and, like `tasks.tags`, it must be
    #: **reassigned whole** on every change. SQLAlchemy does not track a
    #: mutation made inside a JSON column, which is the bug that broke editing
    #: any event with a cancelled date and `users.preferences` before that.
    links = Column(JSON, nullable=False, default=list)

    user = relationship("UserModel", back_populates="courses")
    grades = relationship("GradeModel", back_populates="course", cascade=cascade)
    category_weight_rows = relationship(
        "CourseCategoryWeightModel", back_populates="course", cascade=cascade
    )
    events = relationship("EventModel", back_populates="course", cascade=cascade)
    tasks = relationship("TaskModel", back_populates="course", cascade=cascade)
    grading_schemes = relationship("GradingSchemeModel", cascade=cascade)

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
    #: Kept on the course but out of the arithmetic, for when a professor drops
    #: the two lowest quizzes or similar. Not the same as deleting it: the mark
    #: happened, you may want to see it, and which ones were dropped can change
    #: as more work is marked.
    excluded = Column(Boolean, nullable=False, default=False)
    weight = Column(Float, default=0.0)
    #: When the work is due, as opposed to when it was marked.
    due_date = Column(Date, nullable=True)
    #: The time of day that date means, where the student knows it -- a lab due
    #: at noon, an exam at 14:00. Null means no particular time: the end of the
    #: day for a task, an all-day block for an event. Meaningless without
    #: `due_date`, and the schema and the service both refuse the pair.
    due_time = Column(Time, nullable=True)
    #: How long it runs, in minutes, for a grade that draws a calendar block.
    #: A length rather than an end time, because "the midterm is two hours" is
    #: what a student actually knows -- and because an end derived from a start
    #: cannot contradict it, where a second stored column can.
    #:
    #: Meaningless without `due_time`: an all-day block has no length.
    duration_minutes = Column(Integer, nullable=True)
    #: What that date means: "task" for work to tick off, "event" for something
    #: to attend. Only consulted when there is a date. Defaults to task, which
    #: is what every dated grade did before the choice existed.
    schedule_as = Column(String, nullable=False, default="task", server_default="task")

    course = relationship("CourseModel", back_populates="grades")
    tasks = relationship("TaskModel", back_populates="grade", cascade=cascade)
    events = relationship("EventModel", back_populates="grade", cascade=cascade)

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
    #: spending | savings | investment | emergency | other.
    #:
    #: Mostly styling and sensible defaults, with one exception that is worth
    #: knowing about: safe-to-spend counts only "spending" accounts, because
    #: savings and investments are money already decided against. That is the
    #: single place this column drives behaviour. If per-account control is ever
    #: wanted, add an explicit `counts_as_spendable` rather than loading more
    #: meaning onto this -- `group_id` already shows where that ends up.
    kind = Column(String, nullable=False, default="spending")
    #: Share of incoming money this account takes by default, as a percentage.
    income_share = Column(Float, nullable=False, default=0.0)
    #: Archived accounts keep their history but stop being offered.
    archived = Column(Boolean, nullable=False, default=False)
    position = Column(Integer, nullable=False, default=0)
    #: Whether this balance reaches the net worth figure. Defaults to counting,
    #: and any account may turn it off -- the student owns the data and knows
    #: why a pot should not count. Money lent out is the obvious case, being
    #: money someone else is holding, but a joint account or one held for
    #: somebody else are just as real and no rule here could anticipate them.
    #:
    #: Independent of `kind`, deliberately. Excluding a spending account from
    #: net worth does not stop safe-to-spend counting it: "what am I worth" and
    #: "what can I spend now" are different questions.
    counts_toward_net_worth = Column(
        Boolean, nullable=False, default=True, server_default="1"
    )

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
    #: Which course this was bought for -- a textbook, a lab manual, an iClicker.
    #: Only meaningful for expenses, like category_id, and deliberately NOT used
    #: by tuition: a tuition payment is one ledger line covering a whole term,
    #: and what it cost each course is a Grades question answered from the
    #: per-credit rate rather than from rows in the ledger.
    course_id = Column(Uuid, ForeignKey("courses.id"), nullable=True)
    #: The CSV import that wrote this row, if one did -- so the import can be
    #: undone as one unit. Its own column: `group_id` already carries two
    #: meanings and must not take a third.
    import_id = Column(Uuid, ForeignKey("imports.id"), nullable=True, index=True)

    account = relationship("AccountModel", back_populates="transactions")
    category = relationship("SpendCategoryModel", back_populates="transactions")
    recurring = relationship("RecurringTransactionModel", back_populates="transactions")
    course = relationship("CourseModel")


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


class AccountCategoryLimitModel(Base):
    """What one account is meant to spend on one category in a month.

    Keyed on the **pair**, which is the whole point. An earlier attempt put the
    limit on the category alone and showed it on a single account's page, so a
    limit covering every account was judged against one account's share of the
    spending -- and a category split across two accounts always looked safely
    under budget. Here the limit and the spending it is measured against cover
    the same money.

    Standing rather than per-month: one row says what this account means to
    spend here every month, until changed. There is deliberately no month
    column; if a single month ever needs to differ, that is a month column and a
    resolution rule, not a redesign.

    **A row of 0 is a real instruction** -- "nothing is meant to go here" --
    which is why the absence of a row, and not a falsy amount, is what means
    "no limit". See `Finances/utils/limits.py`.
    """

    __tablename__ = "account_category_limits"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    account_id = Column(Uuid, ForeignKey("accounts.id"), nullable=False)
    category_id = Column(Uuid, ForeignKey("spend_categories.id"), nullable=False)
    limit_amount = Column(Float, nullable=False, default=0.0)


class AccountCategoryMonthLimitModel(Base):
    """One month's override of an account's standing limit for a category.

    Sparse on purpose: a row exists **only** for a month that differs from the
    standing figure in `account_category_limits`. A category budgeted the same
    all year has none, which is what lets changing the standing limit move every
    month nobody overrode -- the thing "standing" has to mean to be worth having.

    A second table rather than a nullable `month` on the standing one. A unique
    index cannot enforce "at most one standing row" when the distinguishing
    column is NULL: both Postgres and SQLite treat NULLs as distinct, so
    `UNIQUE (user, account, category, month)` would happily accept two standing
    limits for the same pair. Partial indexes could express it, but they are
    dialect-specific and `ensure_indexes` walks the metadata generically. Two
    tables, each with a unique index that actually holds.

    **Presence, not value, is what makes an override apply.** A row of 0 is a
    real instruction -- "nothing this month" -- see `effective_category_limit`.
    """

    __tablename__ = "account_category_month_limits"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    account_id = Column(Uuid, ForeignKey("accounts.id"), nullable=False)
    category_id = Column(Uuid, ForeignKey("spend_categories.id"), nullable=False)
    #: Always the first of the month, normalized on the way in.
    month = Column(Date, nullable=False)
    limit_amount = Column(Float, nullable=False, default=0.0)


class AccountMonthValueModel(Base):
    """One month's reading of what an investment account is actually worth.

    An account's balance is the sum of its ledger -- what you put in -- so a
    holding that has doubled and one that has halved read identically. A row here
    closes that for one month, by recording how far the holding sits above or
    below that plain value.

    **`difference_amount` is a level, not a month's gain, and the readings do not
    sum.** All-time gain is the *latest* row, never the total of them; see
    `Finances/utils/returns.py`. The column is deliberately not named
    `gain_amount` for exactly that reason -- "gain" invites a `SUM()` over the
    column, which would report a holding up $300 as up $600 and drift further with
    every month recorded.

    The level is stored rather than the market value, and that is not a
    preference. The difference is contribution-neutral: a deposit raises plain
    value and market value together, so it does not move. Store the market value
    instead and the difference has to be derived against a dated ledger -- record
    $10,543 on the 15th, deposit $1,000 on the 20th, and the month-end ledger is
    $11,000, so the derived difference reads -$457 and a gain is reported as a
    loss. This column survives that deposit; a market value does not.

    One row per (user, account, month), the shape `account_category_month_limits`
    above already uses, with `month` normalized to the first on the way in so a
    month is one value rather than any of twenty-eight.

    Rows are left alone when an account's kind changes away from `investment`.
    They stop being read, because every path that reads them gates on kind, and
    changing the kind back restores them -- where deleting recorded data on a
    dropdown change could not be undone.
    """

    __tablename__ = "account_month_values"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    account_id = Column(Uuid, ForeignKey("accounts.id"), nullable=False)
    #: Always the first of the month, normalized on the way in.
    month = Column(Date, nullable=False)
    #: Market value minus ledger balance. Positive is up on what you put in.
    difference_amount = Column(Float, nullable=False)
    #: What was actually typed, kept only so the form shows back the number
    #: entered rather than one recomputed against a ledger that has since moved.
    #: Never read for arithmetic -- `difference_amount` is the operative figure,
    #: and after a later deposit these two deliberately disagree.
    market_value = Column(Float, nullable=True)


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
    #: Set when a dated grade scheduled as an event produced this block. The
    #: gradebook entry stays the record; this follows it.
    grade_id = Column(Uuid, ForeignKey("grades.id"), nullable=True)
    #: Set when this is a shift. Sits beside course_id and behaves the same way:
    #: it says which thing outside the calendar the block belongs to.
    job_id = Column(Uuid, ForeignKey("jobs.id"), nullable=True)
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

    user = relationship("UserModel", back_populates="events")
    course = relationship("CourseModel", back_populates="events")
    grade = relationship("GradeModel", back_populates="events")


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
    #: Set when a repeating task generated this occurrence. With
    #: `occurrence_date` it is what stops the same occurrence being written
    #: twice.
    recurring_id = Column(Uuid, ForeignKey("recurring_tasks.id"), nullable=True)
    #: The date the rule produced, which is this occurrence's *identity* -- as
    #: opposed to `due_date`, which is where it currently sits and which the
    #: student may move. Null on anything that did not come from a repeat.
    #:
    #: The two used to be the same column, and that is exactly why this exists.
    #: Moving Monday's chore to Wednesday made the rule stop recognising Monday
    #: as written, so the next materialise put a second copy back on Monday and
    #: the stale sweep deleted the one that had been moved. Identity has to be
    #: something the student cannot edit.
    occurrence_date = Column(Date, nullable=True)
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
    #: 1 to 5, 5 being the most important. Coursework is seeded from its grade
    #: category and then belongs to the student, who may change it freely.
    priority = Column(Integer, nullable=False, default=3)
    #: Hidden from the list until this date. The due date never moves with it --
    #: that is what keeps "how late was this" answerable.
    snoozed_until = Column(Date, nullable=True)
    done = Column(Boolean, nullable=False, default=False)
    completed_at = Column(DateTime, nullable=True)
    #: Checked-off tasks archive rather than vanish, so the term's record of what
    #: was actually done survives.
    archived = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    course = relationship("CourseModel", back_populates="tasks")
    grade = relationship("GradeModel", back_populates="tasks")
    recurring = relationship("RecurringTaskModel", back_populates="tasks")
    snoozes = relationship(
        "TaskSnoozeModel", back_populates="task", cascade="all, delete-orphan"
    )


class SinkingFundModel(Base):
    """Money put aside a bit at a time for something that lands all at once.

    Tuition in January is not a surprise, but it behaves like one if nothing
    reserves for it. This says what the thing costs and when it is due, and the
    monthly figure falls out of the two.

    Nothing about the schedule is stored. The contribution is
    (target - saved) / months remaining, recomputed on every read, because a
    stored schedule goes stale the moment a month is missed or the target
    changes -- and the recovery from either is the same division. What *is*
    stored is what actually moved.
    """

    __tablename__ = "sinking_funds"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    target_amount = Column(Float, nullable=False, default=0.0)
    due_on = Column(Date, nullable=False)
    #: Where contributions come from, and where they go. Both required: a
    #: contribution is an ordinary transfer, and a transfer has two ends.
    from_account_id = Column(Uuid, ForeignKey("accounts.id"), nullable=False)
    to_account_id = Column(Uuid, ForeignKey("accounts.id"), nullable=False)
    archived = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    contributions = relationship(
        "SinkingContributionModel",
        back_populates="fund",
        cascade="all, delete-orphan",
    )


class SinkingContributionModel(Base):
    """One month's money actually set aside.

    A row exists only once the transfer has happened. A *planned* contribution
    is derived and has no row, for the same reason a planned payment is not a
    transaction: nothing has moved, and a balance that counted it would report
    money as gone while it is still in the account.
    """

    __tablename__ = "sinking_contributions"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    fund_id = Column(Uuid, ForeignKey("sinking_funds.id"), nullable=False)
    #: The first of the month this covers, so one month cannot be funded twice.
    for_month = Column(Date, nullable=False)
    amount = Column(Float, nullable=False)
    #: The transfer this wrote. A transfer is two rows tied by this column, so
    #: it is the group rather than a single transaction id.
    group_id = Column(Uuid, nullable=True)
    confirmed_at = Column(DateTime, nullable=False, default=utc_now)

    fund = relationship("SinkingFundModel", back_populates="contributions")


class ReminderModel(Base):
    """Something that notifies, as opposed to a task that waits.

    A task sits on a list until you deal with it. A reminder is the other thing:
    it has no life before or after the moment it fires, and ticking it off is
    not the point -- being told is. Forcing one through a task made it a chore
    that never quite closed, which is the same reason a sat exam is an event
    rather than a task.

    `remind_at` is stored as **naive local wall time**, deliberately unlike
    `completed_at`, which is naive UTC. "Remind me at 09:00" means nine o'clock
    where the student is standing, and it should still mean that after the
    clocks change or after a flight. Storing UTC would silently move an existing
    reminder by an hour every spring. The comparison is therefore against the
    student's own local now, resolved through their timezone preference.
    """

    __tablename__ = "reminders"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    notes = Column(String, nullable=True)
    #: Local wall time. See the note above.
    remind_at = Column(DateTime, nullable=False)
    #: Optional, so a reminder about a course can say which.
    course_id = Column(Uuid, ForeignKey("courses.id"), nullable=True)
    #: When it was first surfaced. Set once, so a reminder shown on Monday and
    #: still not dismissed on Wednesday does not read as new again.
    fired_at = Column(DateTime, nullable=True)
    #: Dismissed reminders stay: what you were reminded of is a record, and
    #: deleting it on acknowledgement would make the list unreviewable.
    dismissed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    #: When it was pushed to the student's devices, by the scheduler. Separate
    #: from fired_at, which the open app stamps: a reminder can be shown in
    #: the app and still need pushing, and the app uses this to skip its own
    #: system notification for one a device already received.
    pushed_at = Column(DateTime, nullable=True)

    course = relationship("CourseModel")


class TaskSnoozeModel(Base):
    """One time a task was pushed back, and the reason given.

    A row per snooze rather than two columns on the task, because the point is
    the pattern: three snoozes all citing "waiting on lab partner" is the
    finding, and the latest reason alone cannot say it. A term's worth of these
    is readable; a term's worth of overwrites is not.

    The task's `due_date` is deliberately untouched by any of this. Moving it
    would make every later question about lateness measure against a date the
    student chose rather than the one they were given.
    """

    __tablename__ = "task_snoozes"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    task_id = Column(Uuid, ForeignKey("tasks.id"), nullable=False)
    #: When the snooze was made.
    snoozed_at = Column(DateTime, nullable=False, default=utc_now)
    #: What the task was hidden until.
    until = Column(Date, nullable=False)
    #: Free text, and the whole reason this table exists.
    reason = Column(String, nullable=True)

    task = relationship("TaskModel", back_populates="snoozes")


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


class RecurringTaskModel(Base):
    """A chore that comes back: readings every Monday, laundry every fortnight.

    The third consumer of the recurrence engine, and the one it was written for
    alongside class times and recurring payments.

    Like a standing payment and unlike a calendar event, its occurrences have to
    be real rows: each one is ticked off separately, and this week's reading
    being done says nothing about next week's. A virtual occurrence has nowhere
    to keep that.

    Unlike a standing payment, an occurrence in the near future is written too.
    A task that has not happened yet costs nothing to have sitting there -- you
    can see Monday's reading on Sunday and tick it early -- whereas a payment
    that has not happened would be money wrongly gone from a balance. So this
    materialises a rolling window ahead rather than only up to today.
    """

    __tablename__ = "recurring_tasks"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    #: School work hangs off its course, so each generated task is categorised by
    #: the course code the same way a one-off is.
    course_id = Column(Uuid, ForeignKey("courses.id"), nullable=True)

    #: The template every occurrence is stamped from.
    title = Column(String, nullable=False)
    notes = Column(String, nullable=True)
    due_time = Column(Time, nullable=True)
    estimated_minutes = Column(Integer, nullable=True)
    tags = Column(JSON, nullable=False, default=list)
    #: Stamped onto every occurrence, so a repeating chore is not stuck at the
    #: default with sixty rows to correct one at a time.
    priority = Column(Integer, nullable=False, default=3)

    #: The rule, in the same five columns events and standing payments use.
    starts_on = Column(Date, nullable=False)
    recur_freq = Column(String, nullable=False, default="weekly")
    recur_interval = Column(Integer, nullable=False, default=1)
    recur_byday = Column(String, nullable=True)
    recur_until = Column(Date, nullable=True)
    recur_count = Column(Integer, nullable=True)
    #: Occurrences cancelled individually -- a week the seminar did not run.
    skipped_dates = Column(JSON, nullable=False, default=list)

    #: Paused rather than deleted, so a term's record of what was actually done
    #: still explains itself.
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    course = relationship("CourseModel")
    tasks = relationship("TaskModel", back_populates="recurring")


class TuitionPaymentModel(Base):
    """What a tuition payment was for, beside the one ledger row that recorded it.

    The ledger answers "what left my account": one expense, fees folded in,
    deductions already taken off. This answers "what was that payment made of",
    which is a different question and the one Grades needs -- a course's share is
    its credits times the per-credit rate, gross, because a scholarship reduces
    what you pay and not what the course is worth.

    The two views do not reconcile, deliberately. A term at $250/credit over 13
    credits with $310 of fees and $1,500 of deductions is one $2,060 ledger line
    and $3,250 spread across the course pages. Both are right.
    """

    __tablename__ = "tuition_payments"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    #: The single expense this payment wrote. Deleting that row should take this
    #: with it, which the service does explicitly.
    transaction_id = Column(Uuid, ForeignKey("transactions.id"), nullable=False)
    #: Which term was paid for, matching a course's own year and semester.
    school_year = Column(Integer, nullable=True)
    semester = Column(String, nullable=True)
    #: The rate, not the total. Summed across a term's payments, so paying in two
    #: instalments means entering half the rate twice.
    cost_per_credit = Column(Float, nullable=False, default=0.0)
    #: Mandatory but not a cost of any particular course -- a U-Pass is not a
    #: cost of CPSC 210. Part of the ledger line, absent from every course page.
    fees = Column(Float, nullable=False, default=0.0)
    #: Stored rather than recomputed: it is what the bill was for. Recomputing it
    #: later would silently rewrite history when a course is added or dropped.
    credits_counted = Column(Float, nullable=False, default=0.0)
    occurred_on = Column(Date, nullable=False)

    deductions = relationship(
        "TuitionDeductionModel",
        back_populates="payment",
        cascade="all, delete-orphan",
    )


class TuitionDeductionModel(Base):
    """Something that reduced a tuition bill without being income.

    A scholarship, a bursary, a deposit paid earlier. The money never entered the
    account, so recording it as income would invent a deposit that never
    happened -- but it did reduce the cheque, so it cannot simply be dropped
    either. It lives here, named, and only the net reaches the ledger.
    """

    __tablename__ = "tuition_deductions"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    tuition_payment_id = Column(
        Uuid, ForeignKey("tuition_payments.id"), nullable=False
    )
    description = Column(String, nullable=False)
    #: Positive. The sign is in the name.
    amount = Column(Float, nullable=False)

    payment = relationship("TuitionPaymentModel", back_populates="deductions")


class TermBlackoutModel(Base):
    """A stretch of term when classes do not run.

    A reading break, a stat holiday, a strike. Set once and subtracted from every
    recurring event that belongs to a course, because one reading break applies
    to all six of your classes and entering it six times is how one of them ends
    up wrong.

    Scoped to course-linked events on purpose. The recurrence engine also drives
    recurring transactions and repeating tasks, and neither cares: rent is still
    due during reading break, and the bins still need taking out.

    Stored as a range rather than a list of dates because a reading break is a
    week and a stat holiday is a range of one, so one shape covers both.
    """

    __tablename__ = "term_blackouts"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    label = Column(String, nullable=False)
    starts_on = Column(Date, nullable=False)
    #: Inclusive, and equal to starts_on for a single day.
    ends_on = Column(Date, nullable=False)


class JobModel(Base):
    """A job the student works, and how it pays.

    Three kinds, because they are genuinely different arrangements rather than
    styling on one:

    * **hourly** -- pay is hours times a rate, so the hours are the pay.
    * **salaried** -- a fixed amount each pay period however many hours it took.
      Hours are still worth recording, but as a measure of what the job costs
      you rather than of what it pays.
    * **contract** -- you invoice, and the amount is whatever you billed. There
      is nothing to predict from hours at all.

    The pay schedule reuses the same five rule columns as class times, standing
    payments and repeating tasks, so "every second Friday" needs no mechanism of
    its own. Nothing is ever materialised from it: the rule answers "when is the
    next cheque", and an actual cheque is only ever a row the student entered.
    """

    __tablename__ = "jobs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    employer = Column(String, nullable=True)
    #: hourly | salaried | contract
    kind = Column(String, nullable=False, default="hourly")
    #: Hourly jobs only. A shift may override it for one date.
    hourly_rate = Column(Float, nullable=True)
    #: Salaried jobs only: what one pay period pays, regardless of hours.
    period_amount = Column(Float, nullable=True)
    started_on = Column(Date, nullable=True)
    #: Null while the job is current. Set when it ends, so past jobs keep their
    #: earnings history without being offered for new shifts.
    ended_on = Column(Date, nullable=True)
    #: The pay rule, in the same shape events use, so one engine reads both.
    pay_starts_on = Column(Date, nullable=True)
    recur_freq = Column(String, nullable=True)
    recur_interval = Column(Integer, nullable=False, default=1)
    recur_byday = Column(String, nullable=True)
    recur_until = Column(Date, nullable=True)
    recur_count = Column(Integer, nullable=True)
    archived = Column(Boolean, nullable=False, default=False)
    position = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    shift_records = relationship(
        "ShiftRecordModel", back_populates="job", cascade=cascade
    )
    paycheques = relationship("PaychequeModel", back_populates="job", cascade=cascade)


class ShiftRecordModel(Base):
    """What actually happened on one date of a shift.

    A repeating shift is one event row expanded on read, exactly like a lecture,
    so there is no row anywhere representing "this Friday" -- `(event_id,
    on_date)` is the only thing that identifies one, which is what this is keyed
    by.

    A record exists only once there is something to say about that date. An
    ordinary shift worked exactly as scheduled has no row at all until it is
    confirmed, and an unconfirmed past shift is counted at its scheduled hours
    and reported as assumed rather than dropped -- a forgotten confirmation
    should not make a busy fortnight read as an idle one.
    """

    __tablename__ = "shift_records"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    #: The shift event this is one date of.
    event_id = Column(Uuid, ForeignKey("events.id"), nullable=False)
    #: Denormalised from the event, so earnings can be summed per job without
    #: joining back through the calendar on every read.
    job_id = Column(Uuid, ForeignKey("jobs.id"), nullable=False)
    on_date = Column(Date, nullable=False)
    #: What was actually worked. Null means "as scheduled".
    worked_start = Column(Time, nullable=True)
    worked_end = Column(Time, nullable=True)
    confirmed = Column(Boolean, nullable=False, default=False)
    #: Always positive.
    tip_amount = Column(Float, nullable=False, default=0.0)
    #: Cash tips are money already in hand and may write their own income row.
    #: Tips paid through payroll arrive inside the paycheque's gross, so writing
    #: one for those as well would count them twice.
    tip_is_cash = Column(Boolean, nullable=False, default=True)
    tip_transaction_id = Column(Uuid, ForeignKey("transactions.id"), nullable=True)
    #: Overrides the job's rate for this date alone -- a stat holiday, a night
    #: differential. Null uses the job's own rate.
    rate_override = Column(Float, nullable=True)
    notes = Column(String, nullable=True)

    job = relationship("JobModel", back_populates="shift_records")
    event = relationship("EventModel")


class PaychequeModel(Base):
    """A cheque that actually arrived, and the hours it was meant to cover.

    The same shape as a tuition payment, in reverse. Gross pay and named
    deductions live here; only the net reaches the ledger, because a deduction
    is money that never entered the account and recording it as income would
    invent a deposit that never happened.

    `group_id` rather than a single transaction, because the net splits across
    accounts by income share and a deposit is already several rows tied together
    by that column.

    `expected_gross` is stored rather than recomputed for the same reason a
    tuition payment stores `credits_counted`: it is what the cheque was checked
    against at the time, and deriving it later would silently rewrite the
    verdict when a shift is edited months afterwards.
    """

    __tablename__ = "paycheques"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    job_id = Column(Uuid, ForeignKey("jobs.id"), nullable=False)
    #: Ties the deposit rows this wrote together. Not a foreign key, because a
    #: deposit is several rows and the column it matches carries that meaning
    #: already.
    group_id = Column(Uuid, nullable=True)
    occurred_on = Column(Date, nullable=False)
    gross_amount = Column(Float, nullable=False, default=0.0)
    #: The stretch of work this cheque was for, so it can be reconciled against
    #: the shifts inside it.
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)
    expected_gross = Column(Float, nullable=True)
    notes = Column(String, nullable=True)

    job = relationship("JobModel", back_populates="paycheques")
    deductions = relationship(
        "PaychequeDeductionModel",
        back_populates="paycheque",
        cascade="all, delete-orphan",
    )


class PaychequeDeductionModel(Base):
    """Something taken off a cheque before it arrived.

    Income tax, EI, CPP, union dues. Real money that was earned and never
    reached the account, which is why it is recorded here and not in the ledger.
    """

    __tablename__ = "paycheque_deductions"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    paycheque_id = Column(Uuid, ForeignKey("paycheques.id"), nullable=False)
    description = Column(String, nullable=False)
    #: Positive. The sign is in the name.
    amount = Column(Float, nullable=False)

    paycheque = relationship("PaychequeModel", back_populates="deductions")


# ===== Indexes =====
#
# Declared here in one block rather than as `index=True` scattered over
# twenty-three classes, so the policy is readable in one place: **every foreign
# key, plus the columns a hot query filters or orders on.** Every table in this
# app is multi-tenant, so `user_id` is in nearly every WHERE clause; without
# these, each of those is a full table scan.
#
# `ensure_indexes` in migrations.py walks this same metadata, so an existing
# database picks up anything added here without a second list to keep in step.

# Tenancy and the date window, in one composite. A leading `user_id` also
# serves the plain "everything this user owns" queries, so this is two indexes'
# worth for one index's write cost.
Index("ix_transactions_user_occurred", TransactionModel.user_id, TransactionModel.occurred_on)
Index("ix_transactions_account_id", TransactionModel.account_id)
# The two halves of a transfer, and the several rows of one deposit.
Index("ix_transactions_group_id", TransactionModel.group_id)
Index("ix_transactions_category_id", TransactionModel.category_id)
# Both the "has this rule already written this date" check and the subscription
# audit's `recurring_id IS NULL` filter read this.
Index("ix_transactions_recurring_id", TransactionModel.recurring_id)
Index("ix_transactions_course_id", TransactionModel.course_id)

Index("ix_courses_user_id", CourseModel.user_id)
Index("ix_course_category_weights_course_id", CourseCategoryWeightModel.course_id)
Index("ix_grades_course_id", GradeModel.course_id)

Index("ix_accounts_user_id", AccountModel.user_id)
Index("ix_spend_categories_user_id", SpendCategoryModel.user_id)

# budget_targets.account_id is not served by the unique index below it: that one
# leads with user_id, and an index is only usable from its first column.
Index("ix_budget_targets_account_id", BudgetTargetModel.account_id)

# Both directions get one: "what does this account budget" drives the account
# page, and "who budgets this category" is what a category delete has to find.
# The unique index below leads with user_id, so neither is served by it.
Index("ix_account_category_limits_account_id", AccountCategoryLimitModel.account_id)
Index("ix_account_category_limits_category_id", AccountCategoryLimitModel.category_id)

# The month's overrides are read as a set per account, and a category delete
# has to find them by category.
Index("ix_account_category_month_limits_account_month",
      AccountCategoryMonthLimitModel.account_id, AccountCategoryMonthLimitModel.month)
Index("ix_account_category_month_limits_category_id",
      AccountCategoryMonthLimitModel.category_id)

# A month's reading is read as "this account's, at or before the month on
# screen", so the pair is the index -- and the all-time figure on the card is the
# same question with no upper bound.
Index("ix_account_month_values_account_month",
      AccountMonthValueModel.account_id, AccountMonthValueModel.month)

Index("ix_events_user_id", EventModel.user_id)
Index("ix_events_course_id", EventModel.course_id)
Index("ix_events_grade_id", EventModel.grade_id)
Index("ix_events_job_id", EventModel.job_id)

Index("ix_tasks_user_id", TaskModel.user_id)
Index("ix_tasks_course_id", TaskModel.course_id)
Index("ix_tasks_grade_id", TaskModel.grade_id)
Index("ix_tasks_recurring_id", TaskModel.recurring_id)
Index("ix_task_snoozes_task_id", TaskSnoozeModel.task_id)

Index("ix_reminders_user_id", ReminderModel.user_id)
Index("ix_reminders_course_id", ReminderModel.course_id)

Index("ix_recurring_transactions_user_id", RecurringTransactionModel.user_id)
# Both account columns, because deleting an account has to look for a rule
# pointing at it from either end.
Index("ix_recurring_transactions_account_id", RecurringTransactionModel.account_id)
Index("ix_recurring_transactions_to_account_id", RecurringTransactionModel.to_account_id)
Index("ix_recurring_transactions_category_id", RecurringTransactionModel.category_id)
Index("ix_recurring_tasks_user_id", RecurringTaskModel.user_id)
Index("ix_recurring_tasks_course_id", RecurringTaskModel.course_id)

Index("ix_sinking_funds_user_id", SinkingFundModel.user_id)
Index("ix_sinking_funds_from_account_id", SinkingFundModel.from_account_id)
Index("ix_sinking_funds_to_account_id", SinkingFundModel.to_account_id)
Index("ix_sinking_contributions_fund_id", SinkingContributionModel.fund_id)

Index("ix_tuition_payments_user_id", TuitionPaymentModel.user_id)
Index("ix_tuition_payments_transaction_id", TuitionPaymentModel.transaction_id)
Index("ix_tuition_deductions_payment_id", TuitionDeductionModel.tuition_payment_id)

Index("ix_term_blackouts_user_id", TermBlackoutModel.user_id)

Index("ix_jobs_user_id", JobModel.user_id)
# shift_records is keyed by (event_id, on_date) conceptually -- that pair is how
# one date of a repeating shift is identified -- so the composite is the lookup.
Index("ix_shift_records_event_on_date", ShiftRecordModel.event_id, ShiftRecordModel.on_date)
Index("ix_shift_records_user_id", ShiftRecordModel.user_id)
Index("ix_shift_records_job_id", ShiftRecordModel.job_id)
# Walked when a shift is removed, to find the ledger rows a cash tip wrote.
Index("ix_shift_records_tip_transaction_id", ShiftRecordModel.tip_transaction_id)
Index("ix_paycheques_user_id", PaychequeModel.user_id)
Index("ix_paycheques_job_id", PaychequeModel.job_id)
Index("ix_paycheque_deductions_paycheque_id", PaychequeDeductionModel.paycheque_id)


# ===== Uniqueness =====
#
# Each of these was previously enforced only by a check-then-insert in Python,
# which races: two concurrent requests both read "no row exists" and both
# insert. That is also what let a fresh user's seeded accounts and categories
# double up when two GETs arrived together -- the constraint is what actually
# closes that, not the seeding code.
#
# Unique *indexes* rather than table constraints because SQLite cannot add a
# constraint to an existing table, and an index is the same enforcement.

Index("uq_courses_user_code", CourseModel.user_id, CourseModel.code, unique=True)
Index("uq_accounts_user_name", AccountModel.user_id, AccountModel.name, unique=True)
Index("uq_spend_categories_user_name", SpendCategoryModel.user_id, SpendCategoryModel.name, unique=True)
Index(
    "uq_budget_targets_user_account_month",
    BudgetTargetModel.user_id,
    BudgetTargetModel.account_id,
    BudgetTargetModel.month,
    unique=True,
)
Index(
    "uq_account_category_limits_user_account_category",
    AccountCategoryLimitModel.user_id,
    AccountCategoryLimitModel.account_id,
    AccountCategoryLimitModel.category_id,
    unique=True,
)
Index(
    "uq_account_category_month_limits_user_account_category_month",
    AccountCategoryMonthLimitModel.user_id,
    AccountCategoryMonthLimitModel.account_id,
    AccountCategoryMonthLimitModel.category_id,
    AccountCategoryMonthLimitModel.month,
    unique=True,
)
# One reading per account per month. Without this, saving the same month twice
# through a race would leave two rows and `latest_reading` would pick whichever
# the database happened to return -- a figure that changes on refresh.
Index(
    "uq_account_month_values_user_account_month",
    AccountMonthValueModel.user_id,
    AccountMonthValueModel.account_id,
    AccountMonthValueModel.month,
    unique=True,
)


class UsageEventModel(Base):
    """One user, one day, one kind of use of one module: a counter, not a log.

    Phase 0's analytics (Ideas/overhaul/phase0.md item 4). What the vision's
    gates need -- weekly actives, the universe test (two rooms in a week),
    per-module adoption, time to first value -- are all questions of *which
    days* someone used *which rooms*, so that is all this keeps: no paths, no
    content, no timestamps finer than the first and last of the day.

    Per user, like every other table, so it sits under the same row policy and
    leaves with the account. Read across users only by
    ``scripts/usage_report.py``, which prints aggregates and nothing else.
    """

    __tablename__ = "usage_events"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    day = Column(Date, nullable=False)
    #: "visit" (a page of the module was opened) or "create" (something was
    #: added in it). See app/Usage/services/usage_service.py.
    kind = Column(String, nullable=False)
    module = Column(String, nullable=False)
    count = Column(Integer, nullable=False, default=1)
    first_at = Column(DateTime, nullable=False, default=utc_now)
    last_at = Column(DateTime, nullable=False, default=utc_now)


# One counter per user, day, kind and module: a second visit increments it.
Index(
    "uq_usage_events_user_day_kind_module",
    UsageEventModel.user_id,
    UsageEventModel.day,
    UsageEventModel.kind,
    UsageEventModel.module,
    unique=True,
)


class PushSubscriptionModel(Base):
    """One browser on one device that agreed to receive push notifications.

    Phase 0 item 5. ``endpoint`` is the push service's address for that browser
    and ``p256dh``/``auth`` are its keys; all three come from the browser's
    PushManager, and the payload is encrypted to them so the push service
    carries it without being able to read it.

    The endpoint is unique across users: it identifies a browser, not an
    account, so when a second person signs in on the same browser and turns
    notifications on, the subscription moves to them (see push_service).
    """

    __tablename__ = "push_subscriptions"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    endpoint = Column(String, nullable=False, unique=True)
    p256dh = Column(String, nullable=False)
    auth = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    last_sent_at = Column(DateTime, nullable=True)


class SurveyResponseModel(Base):
    """One person's answer to one in-app question. Phase 1 item 13.

    The first question is the Sean Ellis test the Phase 1 exit gate is written
    in -- "how would you feel if you could no longer use Account?" -- and its
    answers are read only by the owner-run usage report, as counts. "dismissed"
    is an answer too: asking again after "don't ask again" is how an app stops
    being trusted.
    """

    __tablename__ = "survey_responses"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    question = Column(String, nullable=False)
    answer = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)


# One answer per person per question: answering again replaces nothing, it is refused.
Index(
    "uq_survey_responses_user_question",
    SurveyResponseModel.user_id,
    SurveyResponseModel.question,
    unique=True,
)


class ImportModel(Base):
    """One CSV import into one account. Phase 1 item 7.

    Exists so an import can be undone as a unit: every row it wrote carries its
    id in `transactions.import_id`. The counts are what was written at the time;
    what is still there is read from the rows themselves.
    """

    __tablename__ = "imports"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    account_id = Column(Uuid, ForeignKey("accounts.id"), nullable=False, index=True)
    #: The file's name as the browser gave it, for "which import was that".
    filename = Column(String, nullable=True)
    row_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=utc_now)


class SyllabusParseModel(Base):
    """One syllabus read by a language model, and what the person did with it.

    Phase 1 item 1. Kept for two reasons: the daily cap counts these, and the
    no-change measure (account-vision.md §15) is read from them -- of the
    fields the parse produced, how many the person changed before confirming.
    The document itself is not kept here (see the Phase 1 decisions on
    storage); only what was extracted.
    """

    __tablename__ = "syllabus_parses"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    #: The course the parse built, once applied. Cleared if the course is deleted.
    course_id = Column(Uuid, ForeignKey("courses.id"), nullable=True, index=True)
    filename = Column(String, nullable=True)
    provider = Column(String, nullable=False)
    model = Column(String, nullable=False)
    #: What was extracted, as the SyllabusExtract schema.
    result = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    applied_at = Column(DateTime, nullable=True)
    fields_total = Column(Integer, nullable=True)
    fields_changed = Column(Integer, nullable=True)


class GradingSchemeModel(Base):
    """An alternative way a course can be graded. Phase 1 item 4 (vision §7).

    "Choose your scheme", section-dependent weightings, "final replaces the
    midterm if higher": the course's own category weights stay its grade, and a
    scheme is a second reading of the same marks, compared beside it. The rules
    live with the weights, as a list of components, so a scheme is one row
    owned by one course -- which is also what lets the row policy say whose it
    is.
    """

    __tablename__ = "grading_schemes"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    course_id = Column(Uuid, ForeignKey("courses.id"), nullable=False, index=True)
    label = Column(String, nullable=False)
    #: [{"category", "weight", "drop_lowest", "replace_with"}], one per category.
    components = Column(JSON, nullable=False, default=list)
    position = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=utc_now)
