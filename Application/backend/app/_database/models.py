"""SQLAlchemy models for every table the app stores, with their indexes.

Each model's docstring opens with its owner, which is also its row-security kind in
`rls.py`: the `users` root, a per-user row (`user_id`), a child of one owned table,
shared-read or sealed. Columns added after a table first shipped are repeated in
`migrations.ADDED_COLUMNS`, and `ensure_indexes` builds the indexes declared here on
an existing database. `DateTime` columns hold naive UTC unless a column says
otherwise; money is a float of dollars.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    CheckConstraint, Column, String, Float, Boolean, Integer, ForeignKey, Date, DateTime, Time,
    Index, JSON, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import Uuid
from app._database.db import Base

cascade = "all, delete-orphan"
"""Relationship cascade for children that are deleted with their parent."""

# ORDERING. Every foreign key has a relationship on one side or the other, even
# where nothing reads it. The unit of work orders its deletes by relationships,
# not by foreign keys: purging a user deletes every row they own in one flush,
# and a key no relationship covers was deleted in whatever order fell out --
# accounts before the category limits that point at them, which the key refuses.
# The purge runs at startup. tests/test_db_integrity.py holds every key to this.


def utc_now() -> datetime:
    """Return the current time in UTC as a naive datetime.

    Returns:
        Now in UTC with `tzinfo` removed, matching the naive `DateTime` columns.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)

class UserModel(Base):
    """Root row: one account. Row security shows each user only their own row.

    Deleting a user removes every table they own through the cascading relationships
    declared here. Rows owned by other users that name this one (partnerships, task,
    event and team memberships) are view-only here and go by `ON DELETE CASCADE`.

    Attributes:
        id: Primary key.
        name: Display name; copied onto partnerships and memberships when they form.
        email: Sign-in address, written lower-case; unique.
        google_id: Google account subject; unique; null when not linked to Google.
        password_hash: bcrypt hash; null for an account with no password.
        auth_provider: How the account was first created: "google" or "local".
        email_verified: True once an identity provider vouched for the address; local
            signup leaves it False.
        preferences: The `UserPreferences` JSON object. Assign a new dict to save a
            change.
        session_epoch: Counter every token carries; bumping it revokes all outstanding
            sessions.
        deleted_at: When deletion was requested; null for a live account. Sign-in still
            works, and the startup purge removes the account once the grace period has
            passed.
        current_school_year: The school year the student is in now; null when unset.
        current_semester: The term they are in now: "Fall", "Winter", "Spring" or
            "Summer".
        term_label: Free-text name for the current term; null when unset.
        first_year_calendar_year: First-year anchor: the calendar year school year 1's
            Fall began. Null leaves every term undated.
        created_at: When the account was made; null for accounts older than the column.
    """
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
    account_category_limits = relationship("AccountCategoryLimitModel", cascade=cascade)
    account_category_month_limits = relationship("AccountCategoryMonthLimitModel", cascade=cascade)
    account_month_values = relationship("AccountMonthValueModel", cascade=cascade)
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
    degree_requirements = relationship("DegreeRequirementModel", cascade=cascade)
    course_equivalences = relationship("CourseEquivalenceModel", cascade=cascade)
    saved_plans = relationship("SavedPlanModel", cascade=cascade)
    prerequisite_proposals = relationship("PrerequisiteProposalModel", cascade=cascade)
    invites = relationship("InviteModel", cascade=cascade)
    term_reviews = relationship("TermReviewModel", cascade=cascade, overlaps="course,term_reviews")
    office_hour_checkins = relationship("OfficeHourCheckinModel", cascade=cascade,
                                        overlaps="course,office_hour_checkins")
    teams = relationship("TeamModel", cascade=cascade)
    job_applications = relationship("JobApplicationModel", cascade=cascade)
    salary_shares = relationship("SalaryShareModel", cascade=cascade, overlaps="application,salary_share")
    application_seasons = relationship("ApplicationSeasonModel", cascade=cascade)
    partnerships = relationship(
        "PartnershipModel", cascade=cascade, foreign_keys="PartnershipModel.user_id"
    )
    #: Partners' rows that name this user. View-only: deleting them is left to
    #: the database's ON DELETE CASCADE, because under row-level security the
    #: purge acts as this user and cannot see those rows -- and a referential
    #: action is the one thing row security does not stand in the way of.
    partnered_by = relationship(
        "PartnershipModel", foreign_keys="PartnershipModel.partner_id", viewonly=True,
    )
    #: Others' tasks this user is a member of (Phase 2 item 9a). View-only for
    #: the same reason as partnered_by: the rows hang under the owners' tasks,
    #: so the purge cannot see them, and ON DELETE CASCADE removes them.
    task_memberships = relationship(
        "TaskMemberModel", foreign_keys="TaskMemberModel.member_id", viewonly=True,
    )
    #: Others' events this user is on (Phase 2 item 9b), for the same reason.
    event_memberships = relationship(
        "EventMemberModel", foreign_keys="EventMemberModel.member_id", viewonly=True,
    )
    #: Teams this user plays on (Phase 2 item 11), for the same reason.
    team_memberships = relationship(
        "TeamMemberModel", foreign_keys="TeamMemberModel.member_id", viewonly=True,
    )

    @property
    def has_password(self) -> bool:
        """Whether the account has a password it can sign in with."""
        return self.password_hash is not None

    @property
    def has_google(self) -> bool:
        """Whether the account is linked to a Google identity."""
        return self.google_id is not None


class CourseModel(Base):
    """Per-user row: one course on the student's record.

    Deleting a course cascades to its grades, category weights, events, tasks, term
    reviews, grading schemes and prerequisite proposals. Unique per user and exact
    `code`.

    Attributes:
        id: Primary key.
        user_id: Owner.
        code: Course code as entered, such as "CPSC 210".
        name: Course title.
        semester: Term of the school year: "Fall", "Winter", "Spring" or "Summer".
        year: School year the course belongs to (1-10), not a calendar year.
        credits: Credit value; defaults to 3.
        required: True for a degree requirement, False for an elective; splits credits
            completed.
        professor: Instructor's name; optional.
        section: Section the student is in, such as "101"; Attention flags a current
            course without one.
        counting_scheme_id: The `grading_schemes` row picked as the grade; null uses the
            course's own weights. No foreign key; `scheme_service` keeps it valid.
        catalogue_course_id: Catalogue course chosen by hand; null matches by campus and
            code on each read. No foreign key; a missing row reads as no choice.
        catalogue_unlinked: True when the student said no catalogue course matches.
        final_grade: Recorded final percentage; 0 means none recorded.
        projected_before_final: Projected grade just before the final was marked or the
            result entered; written once, by the server.
        projected_on: The day `projected_before_final` was taken.
        target_grade: Target percentage; null falls back to the account default.
        average: Stored course average from marked work only, rewritten on every grade
            write; 0.0 when nothing is marked.
        start_date: First day of the course; optional.
        end_date: Last day of the course; optional.
        no_final: The course has no final exam, so a missing final grade is not flagged.
        transfer_credit: Credit granted without taking the course: counts credits, never
            an average.
        archived: Still searchable and in the credit-weighted average, but not in
            credits completed.
        links: JSON list of {"title", "url"} in the student's order. Assign a new list
            to save a change.
    """
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
    #: The grading scheme that is this course's grade, when you picked one
    #: (Phase 1 D25). Null: the course's own weights are the grade. No
    #: database foreign key -- grading_schemes already points back at courses,
    #: and like the other added `_id` columns the app keeps it honest:
    #: scheme_service only sets a scheme of this course, and clears it before
    #: that scheme is deleted.
    counting_scheme_id = Column(Uuid, nullable=True)
    #: The catalogue course you chose for this one by hand (Phase 2 D11). Null
    #: means automatic: matched by campus and code each time it is read, so a
    #: course links itself once the catalogue has it. No foreign key, like the
    #: other added `_id` columns: a catalogue row that has gone reads as no
    #: choice, and matching takes over.
    catalogue_course_id = Column(Uuid, nullable=True)
    #: You said this course has no catalogue course, so nothing is matched.
    catalogue_unlinked = Column(Boolean, nullable=False, default=False)
    final_grade = Column(Float, default=0.0)
    #: Phase 1 D34. The course's grade just before the final was marked or the
    #: result entered -- the app's last real prediction -- and the day it stood.
    #: Written once, by the server; the course page sets it against the result.
    projected_before_final = Column(Float, nullable=True)
    projected_on = Column(Date, nullable=True)
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
    term_reviews = relationship("TermReviewModel", back_populates="course", cascade=cascade,
                                overlaps="term_reviews")
    office_hour_checkins = relationship("OfficeHourCheckinModel", back_populates="course", cascade=cascade,
                                        overlaps="office_hour_checkins")
    grading_schemes = relationship("GradingSchemeModel", cascade=cascade)
    prerequisite_proposals = relationship("PrerequisiteProposalModel", cascade=cascade)

    @property
    def category_weights(self) -> dict[str, float]:
        """Map of each category name to its weight, from `category_weight_rows`."""
        return {cw.category: cw.weight for cw in self.category_weight_rows}


class CourseCategoryWeightModel(Base):
    """Child of `courses`: one grade category's weight in a course.

    Attributes:
        id: Integer primary key.
        course_id: Parent course.
        category: Category name, a `GradeCategory` value.
        weight: Percentage of the course grade; a bonus category's weight sits outside
            the 100.
    """
    __tablename__ = "course_category_weights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(Uuid, ForeignKey("courses.id"), nullable=False)
    category = Column(String, nullable=False)
    weight = Column(Float, nullable=False, default=0.0)

    course = relationship("CourseModel", back_populates="category_weight_rows")

class GradeModel(Base):
    """Child of `courses`: one piece of assessed work.

    Deleting a grade cascades to the task or calendar event its date raised.

    Attributes:
        id: Primary key.
        course_id: Parent course.
        name: Assessment name.
        category: Category name, a `GradeCategory` value.
        score: Points earned; null means unmarked, not zero.
        max_score: Points possible.
        excluded: Dropped: kept on the course but left out of every average.
        weight: Copy of the category's weight, kept in step by `sync_grade_weights`.
        due_date: When the work is due; a dated grade raises a task or a calendar block.
        due_time: Time of day on `due_date`; null means end of day for a task and all
            day for an event. Requires `due_date`.
        duration_minutes: Length of the calendar block; needs `due_time`.
        schedule_as: What the date raises: "task" (closes when the score lands) or
            "event" (a calendar block).
    """
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
    """Per-user row: one account money sits in. Unique per user and name.

    Attributes:
        id: Primary key.
        user_id: Owner.
        name: Account name.
        kind: Account kind: "spending", "savings", "investment", "emergency", "debt" or
            "other". Safe-to-spend counts spending accounts only.
        income_share: Default share of a deposit, as a percentage; deposits split by
            each account's part of the shares' total.
        archived: Archived accounts keep their history but are no longer offered.
        position: Display order.
        counts_toward_net_worth: Counted account: False drops it from net worth and
            every multi-account figure; read through `Finances/services/counted.py`.
    """

    __tablename__ = "accounts"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    #: spending | savings | investment | emergency | debt | other.
    #:
    #: Mostly styling and sensible defaults, with exceptions worth knowing:
    #: safe-to-spend and the forecast count only "spending" accounts, the year
    #: plan counts spending, savings and emergency as liquid, only "investment"
    #: takes market-value readings, and the last spending and savings accounts
    #: are protected. Per-account control is `counts_toward_net_worth`; do not
    #: load more meaning onto this -- `group_id` already shows where that ends up.
    kind = Column(String, nullable=False, default="spending")
    #: Share of incoming money this account takes by default, as a percentage.
    income_share = Column(Float, nullable=False, default=0.0)
    #: Archived accounts keep their history but stop being offered.
    archived = Column(Boolean, nullable=False, default=False)
    position = Column(Integer, nullable=False, default=0)
    #: Whether this account counts -- toward net worth *and* every analytic:
    #: safe to spend, the forecast, the year plan, spending summaries (Phase 1
    #: D39, the owner's call; until then it was net worth only). Defaults to
    #: counting, and any account may turn it off -- the student owns the data
    #: and knows why a pot should not count: money lent out, a joint account,
    #: one held for somebody else. Unticked, the analytics treat it as absent;
    #: its ledger and page stay. Read through Finances/services/counted.py.
    #:
    #: Independent of `kind`: any kind may be unticked. The column keeps its old
    #: name because renaming a Postgres column buys nothing a reader sees.
    counts_toward_net_worth = Column(
        Boolean, nullable=False, default=True, server_default="1"
    )

    user = relationship("UserModel", back_populates="accounts")
    transactions = relationship(
        "TransactionModel", back_populates="account", cascade=cascade
    )


class TransactionModel(Base):
    """Per-user row: money that entered or left one account.

    A balance is the plain sum of an account's rows, and a transfer is two rows that
    cancel out.

    Attributes:
        id: Primary key.
        user_id: Owner.
        account_id: The account the money moved in.
        kind: "income", "expense" or "transfer".
        amount: Signed dollars: positive into the account, negative out of it.
        description: Free text; optional.
        occurred_on: Local date the money moved.
        group_id: Ties a transfer's two rows, or a deposit's allocations, together; null
            otherwise.
        category_id: Spending category; expenses only, null otherwise.
        recurring_id: The standing instruction that wrote this row; with `occurred_on`
            it stops a payment being written twice.
        course_id: Course the expense was for, such as a textbook; never set by tuition.
        import_id: CSV import that wrote this row, so the import can be undone whole.
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
    source_import = relationship("ImportModel")  # delete order only, see ORDERING
    course = relationship("CourseModel")


class SpendCategoryModel(Base):
    """Per-user row: a spending category, such as groceries. Unique per user and name.

    Attributes:
        id: Primary key.
        user_id: Owner.
        name: Category name.
        archived: Archived categories keep their history but are no longer offered.
        position: Display order.
    """

    __tablename__ = "spend_categories"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    archived = Column(Boolean, nullable=False, default=False)
    position = Column(Integer, nullable=False, default=0)

    transactions = relationship("TransactionModel", back_populates="category")


class BudgetTargetModel(Base):
    """Per-user row: what one account plans to spend in one month.

    Unique per user, account and month.

    Attributes:
        id: Primary key.
        user_id: Owner.
        account_id: The account the plan is for.
        month: First day of the month; normalised on the way in.
        planned_amount: Planned spending in dollars.
    """

    __tablename__ = "budget_targets"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    account_id = Column(Uuid, ForeignKey("accounts.id"), nullable=False)
    account = relationship("AccountModel")  # delete order only, see ORDERING
    #: Always the first of the month, normalized on the way in so a month is
    #: one value rather than any of twenty-eight.
    month = Column(Date, nullable=False)
    planned_amount = Column(Float, nullable=False, default=0.0)


class AccountCategoryLimitModel(Base):
    """Per-user row: an account's standing monthly limit for one spending category.

    Keyed on the (account, category) pair so the limit and the spending it is measured
    against cover the same money. A row of 0 is a real limit; no row means no limit.
    Unique per user, account and category. See `Finances/utils/limits.py`.

    Attributes:
        id: Primary key.
        user_id: Owner.
        account_id: The account spending against the limit.
        category_id: The spending category limited.
        limit_amount: Monthly ceiling in dollars.
    """

    __tablename__ = "account_category_limits"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    account_id = Column(Uuid, ForeignKey("accounts.id"), nullable=False)
    account = relationship("AccountModel")  # delete order only, see ORDERING
    category_id = Column(Uuid, ForeignKey("spend_categories.id"), nullable=False)
    category = relationship("SpendCategoryModel")  # delete order only, see ORDERING
    limit_amount = Column(Float, nullable=False, default=0.0)


class AccountCategoryMonthLimitModel(Base):
    """Per-user row: one month's override of an account's standing category limit.

    A row exists only for a month that differs from `account_category_limits`, so
    changing the standing limit moves every month nobody overrode. Its presence, not its
    value, makes it apply: 0 means nothing this month. Unique per user, account,
    category and month.

    Attributes:
        id: Primary key.
        user_id: Owner.
        account_id: The account spending against the limit.
        category_id: The spending category limited.
        month: First day of the month overridden.
        limit_amount: That month's ceiling in dollars.
    """

    __tablename__ = "account_category_month_limits"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    account_id = Column(Uuid, ForeignKey("accounts.id"), nullable=False)
    account = relationship("AccountModel")  # delete order only, see ORDERING
    category_id = Column(Uuid, ForeignKey("spend_categories.id"), nullable=False)
    category = relationship("SpendCategoryModel")  # delete order only, see ORDERING
    #: Always the first of the month, normalized on the way in.
    month = Column(Date, nullable=False)
    limit_amount = Column(Float, nullable=False, default=0.0)


class AccountMonthValueModel(Base):
    """Per-user row: one month's reading of what an investment account is worth.

    Stores how far market value sits above or below the ledger balance, a level that a
    later deposit does not move. Readings do not sum: all-time gain is the latest row
    (see `Finances/utils/returns.py`). Unique per user, account and month; rows stay but
    go unread if the account stops being an investment.

    Attributes:
        id: Primary key.
        user_id: Owner.
        account_id: The investment account read.
        month: First day of the month the reading is for.
        difference_amount: Market value minus ledger balance in dollars; positive is a
            gain.
        market_value: The value as typed, shown back on the form; never used in
            arithmetic.
    """

    __tablename__ = "account_month_values"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    account_id = Column(Uuid, ForeignKey("accounts.id"), nullable=False)
    account = relationship("AccountModel")  # delete order only, see ORDERING
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
    """Per-user row: something on the calendar on a date, optionally repeating.

    Class times, exams, shifts, blocks raised by dated grades and personal events share
    this table. A repeat is stored as its recurrence rule and expanded on read, so an
    occurrence has no row of its own. Deleting an event cascades to its members and
    invites.

    Attributes:
        id: Primary key.
        user_id: Owner.
        course_id: Course the event belongs to; null for a personal event.
        grade_id: Dated grade that raised this block; null otherwise.
        job_id: Job this shift belongs to; null for anything that is not a shift.
        title: Event title.
        kind: Card theme: "lecture", "lab", "discussion", "midterm", "final",
            "deadline", "personal" or "shift".
        location: Where it happens; optional.
        notes: Free text; optional.
        starts_on: Local date of the first (or only) occurrence.
        start_time: Local start time; null for an all-day event.
        end_time: Local end time; null for an all-day event.
        recur_freq: "daily", "weekly" or "monthly"; null for a one-off.
        recur_interval: Repeat every this many periods.
        recur_byday: Weekly only: weekdays such as "MO,WE,FR"; empty means the weekday
            of `starts_on`.
        recur_until: Inclusive last date; never set with `recur_count`.
        recur_count: Number of occurrences; never set with `recur_until`.
        skipped_dates: JSON list of ISO dates the rule would produce but that were
            cancelled. Assign a new list to save a change.
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
    job = relationship("JobModel")  # delete order only, see ORDERING
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
    #: Who else is on it, and the link that lets them join (Phase 2 item 9b).
    members = relationship("EventMemberModel", back_populates="event", cascade="all, delete-orphan")
    invites = relationship("EventInviteModel", back_populates="event", cascade="all, delete-orphan")


class TaskModel(Base):
    """Per-user row: something to do, with or without a due date.

    Deleting a task cascades to its snoozes, members and invites.

    Attributes:
        id: Primary key.
        user_id: Owner.
        course_id: Course the work belongs to; its code is the task's category.
        grade_id: Dated grade that raised the task; the task closes when that grade is
            marked.
        recurring_id: Repeating task that materialised this occurrence; null for a
            one-off.
        occurrence_date: Date the rule produced, the occurrence's fixed identity;
            `due_date` may move, this never does.
        title: Task title.
        notes: Free text; optional.
        due_date: Local due date; null for an undated task.
        due_time: Local due time; null means end of day.
        estimated_minutes: Expected effort in minutes; summed into the week's load.
        actual_minutes: Time it really took, in minutes; null means not given.
        timer_started_at: When the running timer started; null when no timer runs.
        tags: JSON list of free-text labels. Assign a new list to save a change.
        priority: 1 (lowest) to 5 (highest); coursework starts from its grade category.
        snoozed_until: Snooze: hidden until this local date; the due date does not move.
        done: Whether the task is complete.
        completed_at: When it was completed; null while open.
        archived: Completed tasks archive rather than disappear.
        created_at: When the task was created.
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
    #: Phase 1 D35. How long it actually took, from the question on completion
    #: or the timer. Null is "not said", which counts for nothing.
    actual_minutes = Column(Integer, nullable=True)
    #: When the running timer started (UTC); null when none is running. Kept on
    #: the server so a timer survives a reload or a second device.
    timer_started_at = Column(DateTime, nullable=True)
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
    #: Who else is on it, and the link that lets them join (Phase 2 item 9a).
    members = relationship("TaskMemberModel", back_populates="task", cascade="all, delete-orphan")
    invites = relationship("TaskInviteModel", back_populates="task", cascade="all, delete-orphan")


class SinkingFundModel(Base):
    """Per-user row: a sinking fund saving toward a target by a due date.

    The monthly contribution is derived on every read, never stored; only money actually
    moved is stored, as `sinking_contributions`.

    Attributes:
        id: Primary key.
        user_id: Owner.
        name: Fund name.
        target_amount: Amount to have saved, in dollars.
        due_on: Date the money is needed.
        from_account_id: Account contributions are transferred out of.
        to_account_id: Account contributions are transferred into.
        archived: Archived funds keep their history but are no longer shown.
        created_at: When the fund was created.
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
    from_account = relationship("AccountModel", foreign_keys=[from_account_id])  # delete order only, see ORDERING
    to_account_id = Column(Uuid, ForeignKey("accounts.id"), nullable=False)
    to_account = relationship("AccountModel", foreign_keys=[to_account_id])  # delete order only, see ORDERING
    archived = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    contributions = relationship(
        "SinkingContributionModel",
        back_populates="fund",
        cascade="all, delete-orphan",
    )


class SinkingContributionModel(Base):
    """Child of `sinking_funds`: one month's contribution, once the transfer happened.

    A planned contribution has no row.

    Attributes:
        id: Primary key.
        fund_id: Parent fund.
        for_month: First day of the month the contribution covers.
        amount: Dollars set aside.
        group_id: `group_id` of the transfer's two ledger rows.
        confirmed_at: When the contribution was recorded.
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
    """Per-user row: a reminder that notifies at a moment, unlike a task that waits.

    Attributes:
        id: Primary key.
        user_id: Owner.
        title: What to be reminded of.
        notes: Free text; optional.
        remind_at: When to fire, as naive local wall time in the user's zone (not UTC).
        course_id: Course the reminder is about; optional.
        fired_at: When the app first surfaced it; set once.
        dismissed_at: When it was dismissed; dismissed reminders are kept.
        created_at: When the reminder was created.
        pushed_at: When the scheduler pushed it to the user's devices; null until then.
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
    """Child of `tasks`: one snooze of a task and the reason given.

    Attributes:
        id: Primary key.
        task_id: Parent task.
        snoozed_at: When the snooze was made.
        until: Local date the task was hidden until.
        reason: Free-text reason; optional.
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
    """Per-user row: a standing instruction, such as rent on the 1st.

    Stores the recurrence rule and a template. Each occurrence on or before today is
    materialised once into a real transaction pointing back through
    `transactions.recurring_id`; later occurrences stay projections.

    Attributes:
        id: Primary key.
        user_id: Owner.
        kind: "income", "expense", "transfer" or "deposit".
        account_id: The account paid from or into, or a transfer's source; null for a
            deposit, which splits by income share.
        to_account_id: A transfer's destination; null otherwise.
        amount: Dollars, always positive; the sign is applied when a payment is written.
        description: Free text; optional.
        category_id: Spending category; expenses only.
        starts_on: First date of the rule.
        recur_freq: "daily", "weekly" or "monthly".
        recur_interval: Repeat every this many periods.
        recur_byday: Weekly only: weekdays such as "MO,FR".
        recur_until: Inclusive last date; never set with `recur_count`.
        recur_count: Number of occurrences; never set with `recur_until`.
        skipped_dates: JSON list of ISO dates cancelled from the rule. Assign a new list
            to save a change.
        active: False pauses the instruction without deleting it.
        created_at: When the instruction was created.
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
    """Per-user row: a repeating task and the template its occurrences copy.

    Occurrences are materialised as real tasks over a rolling window (14 days back to
    60 ahead) so each can be ticked off on its own.

    Attributes:
        id: Primary key.
        user_id: Owner.
        course_id: Course each occurrence belongs to; optional.
        title: Title stamped on each occurrence.
        notes: Notes stamped on each occurrence.
        due_time: Due time stamped on each occurrence; null means end of day.
        estimated_minutes: Effort estimate stamped on each occurrence.
        tags: JSON list of labels stamped on each occurrence.
        priority: Priority (1-5) stamped on each occurrence.
        starts_on: First date of the rule.
        recur_freq: "daily", "weekly" or "monthly".
        recur_interval: Repeat every this many periods.
        recur_byday: Weekly only: weekdays such as "MO,WE".
        recur_until: Inclusive last date; never set with `recur_count`.
        recur_count: Number of occurrences; never set with `recur_until`.
        skipped_dates: JSON list of ISO dates cancelled from the rule. Assign a new list
            to save a change.
        active: False pauses the rule without deleting it.
        created_at: When the rule was created.
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
    """Per-user row: what a tuition payment covered, beside its one ledger row.

    A course's share of a term is its credits times `cost_per_credit`, gross of
    deductions; only the net reaches the ledger. Deleting either this or its transaction
    deletes the other, done by the tuition service.

    Attributes:
        id: Primary key.
        user_id: Owner.
        transaction_id: The single expense row the payment wrote.
        school_year: School year paid for, matching `courses.year`.
        semester: Term paid for, matching `courses.semester`.
        cost_per_credit: Per-credit rate in dollars; instalments enter part of the rate
            each.
        fees: Mandatory fees in dollars; in the ledger line, on no course page.
        credits_counted: Credits the bill covered, stored as billed.
        occurred_on: Date of the payment.
    """

    __tablename__ = "tuition_payments"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    #: The single expense this payment wrote. Deleting that row should take this
    #: with it, which the service does explicitly.
    transaction_id = Column(Uuid, ForeignKey("transactions.id"), nullable=False)
    transaction = relationship("TransactionModel")  # delete order only, see ORDERING
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
    """Child of `tuition_payments`: a deduction from a tuition bill, such as a bursary.

    Never income: the money did not enter an account.

    Attributes:
        id: Primary key.
        tuition_payment_id: Parent payment.
        description: What the deduction was.
        amount: Dollars, always positive.
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
    """Per-user row: a blackout, a stretch when classes do not run.

    Cancels occurrences of course-linked events only; standing payments and repeating
    tasks ignore it.

    Attributes:
        id: Primary key.
        user_id: Owner.
        label: Name, such as "Reading break".
        starts_on: First day of the blackout.
        ends_on: Last day, inclusive; equals `starts_on` for one day.
    """

    __tablename__ = "term_blackouts"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    label = Column(String, nullable=False)
    starts_on = Column(Date, nullable=False)
    #: Inclusive, and equal to starts_on for a single day.
    ends_on = Column(Date, nullable=False)


class JobModel(Base):
    """Per-user row: a job the student works, and how it pays.

    The pay schedule is either the shared recurrence rule or set days of the month
    (`pay_month_days`, `pay_last_day`, `pay_nth_weekdays`); see
    `Jobs/services/pay_schedule.py`. Nothing is materialised from it. Deleting a job
    cascades to its shift records and paycheques.

    Attributes:
        id: Primary key.
        user_id: Owner.
        name: Job title.
        employer: Employer name; optional.
        kind: "hourly", "salaried" or "contract".
        hourly_rate: Hourly jobs: dollars per hour; a shift record may override it.
        period_amount: Salaried jobs: dollars per pay period.
        started_on: First day of the job; optional.
        ended_on: Last day; null while the job is current.
        pay_starts_on: First pay date of the rule.
        recur_freq: Pay rule frequency; null for no schedule, "monthly" when paid on set
            days.
        recur_interval: Pay every this many periods.
        recur_byday: Weekly pay rules: weekdays such as "FR".
        recur_until: Inclusive last pay date; never set with `recur_count`.
        recur_count: Number of pay dates; never set with `recur_until`.
        pay_month_days: Days of the month paid, such as "15,30"; a day a month lacks
            pays on its last day.
        pay_last_day: Also pays on the last day of every month.
        pay_nth_weekdays: Nth weekdays paid, such as "-1FR" or "2TH,4TH"; never with
            month days.
        pay_weekend: A pay date on a weekend moves to the "previous" or "next" weekday,
            or "keep"s.
        archived: Archived jobs keep their history but are no longer offered.
        position: Display order.
        created_at: When the job was created.
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
    #: Pay on set days of the month (next.md, decided 2026-10-03), the one
    #: shape the shared rule cannot say. When any of these is set the job pays
    #: by them instead of by the rule above, and `recur_freq` reads "monthly"
    #: so "has a pay schedule" keeps one meaning. See Jobs/services/pay_schedule.py.
    #: "15,30": days of the month. A day the month lacks pays on its last day,
    #: the opposite of the shared rule, which skips it (rent must not move;
    #: pay must not vanish in February).
    pay_month_days = Column(String, nullable=True)
    #: And the last day of every month.
    pay_last_day = Column(Boolean, nullable=False, default=False)
    #: "-1FR" (the last Friday), "2TH,4TH". Stands alone: never with dates.
    pay_nth_weekdays = Column(String, nullable=True)
    #: A date landing on a weekend: "previous" weekday, "next", or "keep".
    pay_weekend = Column(String, nullable=True)
    archived = Column(Boolean, nullable=False, default=False)
    position = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    shift_records = relationship(
        "ShiftRecordModel", back_populates="job", cascade=cascade
    )
    paycheques = relationship("PaychequeModel", back_populates="job", cascade=cascade)


class ShiftRecordModel(Base):
    """Per-user row: a shift record, what actually happened on one date of a shift.

    Identified by `(event_id, on_date)`, since a repeating shift has no row per date.
    A row exists only once there is something to say; an unconfirmed past shift counts
    at its scheduled hours, flagged as assumed.

    Attributes:
        id: Primary key.
        user_id: Owner.
        event_id: The shift event this is one date of.
        job_id: The shift's job, copied from the event for per-job sums.
        on_date: The occurrence date.
        worked_start: Actual start time; null means as scheduled.
        worked_end: Actual end time; null means as scheduled.
        confirmed: Whether the student confirmed the shift.
        tip_amount: Tips in dollars, always positive.
        tip_is_cash: True for cash in hand; False for tips paid inside the paycheque's
            gross.
        tip_transaction_id: Income row a cash tip wrote; null if none.
        rate_override: Hourly rate for this date only; null uses the job's rate.
        notes: Free text; optional.
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
    tip_transaction = relationship("TransactionModel")  # delete order only, see ORDERING
    #: Overrides the job's rate for this date alone -- a stat holiday, a night
    #: differential. Null uses the job's own rate.
    rate_override = Column(Float, nullable=True)
    notes = Column(String, nullable=True)

    job = relationship("JobModel", back_populates="shift_records")
    event = relationship("EventModel")


class PaychequeModel(Base):
    """Per-user row: a paycheque that arrived: gross, deductions and the period covered.

    Only the net reaches the ledger, as a deposit split across accounts by income share.

    Attributes:
        id: Primary key.
        user_id: Owner.
        job_id: The job that paid.
        group_id: `group_id` of the deposit rows the net wrote; null if none.
        occurred_on: Date the cheque arrived.
        gross_amount: Gross pay in dollars.
        period_start: First day of the work period covered; optional.
        period_end: Last day of the work period covered; optional.
        expected_gross: Gross predicted from shifts when the cheque was checked, stored
            as it stood then.
        notes: Free text; optional.
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
    """Child of `paycheques`: a deduction taken off a cheque, such as income tax.

    Attributes:
        id: Primary key.
        paycheque_id: Parent paycheque.
        description: What the deduction was.
        amount: Dollars, always positive.
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
    """Per-user row: one day's count of one kind of use of one module.

    A counter, not a log: unique per user, day, kind and module. Read across users only
    by `scripts/usage_report.py`, which prints aggregates.

    Attributes:
        id: Primary key.
        user_id: Owner.
        day: The user's local date.
        kind: "visit", "prompted_visit" (a visit opened from a push) or "create".
        module: Module name, such as "grades".
        count: Times recorded that day.
        first_at: First time recorded that day.
        last_at: Last time recorded that day.
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
    """Per-user row: one browser that agreed to receive push notifications.

    `endpoint` identifies a browser, not an account, so it is unique across users and
    moves to whoever turns notifications on there last.

    Attributes:
        id: Primary key.
        user_id: Owner.
        endpoint: The push service's URL for the browser; unique.
        p256dh: The browser's public key the payload is encrypted to.
        auth: The browser's authentication secret.
        created_at: When the browser subscribed.
        last_sent_at: When a push last went to it; null if never.
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
    """Per-user row: one answer to one in-app question. Unique per user and question.

    Attributes:
        id: Primary key.
        user_id: Owner.
        question: Question key, such as "disappointment".
        answer: Answer key: "very", "somewhat", "not" or "dismissed".
        created_at: When it was answered.
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
    """Per-user row: one CSV import into one account, so it can be undone whole.

    Attributes:
        id: Primary key.
        user_id: Owner.
        account_id: The account imported into.
        filename: File name as the browser gave it; optional.
        row_count: Rows written at the time.
        created_at: When the import ran.
    """

    __tablename__ = "imports"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    account_id = Column(Uuid, ForeignKey("accounts.id"), nullable=False, index=True)
    account = relationship("AccountModel")  # delete order only, see ORDERING
    #: The file's name as the browser gave it, for "which import was that".
    filename = Column(String, nullable=True)
    row_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=utc_now)


class SyllabusParseModel(Base):
    """Per-user row: one syllabus read by a language model, and what became of it.

    Counts toward the daily parse cap and measures how many fields were changed before
    confirming. The file, when kept, is the bucket object `object_name`.

    Attributes:
        id: Primary key.
        user_id: Owner.
        course_id: Course the parse built once applied; null before that or if deleted.
        filename: Uploaded file name; optional.
        provider: Model provider that answered.
        model: Model name that answered.
        result: The extraction as a `SyllabusExtract` JSON object.
        created_at: When the parse ran.
        applied_at: When the person confirmed it; null until then.
        fields_total: Fields the parse produced; null until applied.
        fields_changed: Fields the person changed before confirming; null until applied.
        media_type: MIME type of the uploaded file, for serving it back.
        file_kept: True once the file is stored in the bucket.
    """

    __tablename__ = "syllabus_parses"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    #: The course the parse built, once applied. Cleared if the course is deleted.
    course_id = Column(Uuid, ForeignKey("courses.id"), nullable=True, index=True)
    course = relationship("CourseModel")  # delete order only, see ORDERING
    filename = Column(String, nullable=True)
    provider = Column(String, nullable=False)
    model = Column(String, nullable=False)
    #: What was extracted, as the SyllabusExtract schema.
    result = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    applied_at = Column(DateTime, nullable=True)
    fields_total = Column(Integer, nullable=True)
    fields_changed = Column(Integer, nullable=True)
    #: What the uploaded file was, for serving it back.
    media_type = Column(String, nullable=True)
    #: True once the file is in the bucket. A failed upload leaves it False and
    #: the parse still stands; the extraction is what the app runs on.
    file_kept = Column(Boolean, nullable=False, default=False)

    @property
    def object_name(self) -> str:
        """Bucket object name for the uploaded file: "syllabi/<id>"."""
        return f"syllabi/{self.id}"


class GradingSchemeModel(Base):
    """Child of `courses`: an alternative grading scheme for a course.

    A second reading of the same marks, compared beside the course's own weights or
    picked as its grade through `courses.counting_scheme_id`.

    Attributes:
        id: Primary key.
        course_id: Parent course.
        label: Scheme name.
        components: JSON list, one per category: {"category", "weight", "drop_lowest",
            "replace_with"}.
        position: Display order.
        created_at: When the scheme was created.
    """

    __tablename__ = "grading_schemes"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    course_id = Column(Uuid, ForeignKey("courses.id"), nullable=False, index=True)
    label = Column(String, nullable=False)
    #: [{"category", "weight", "drop_lowest", "replace_with"}], one per category.
    components = Column(JSON, nullable=False, default=list)
    position = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=utc_now)


class SavedPlanModel(Base):
    """Per-user row: a year plan as it stood when saved. Each save adds a row.

    Attributes:
        id: Primary key.
        user_id: Owner.
        saved_at: When it was saved.
        saved_on: The user's local date when saved; finished months compare with the
            plan in force before they began.
        starts_on: First day the plan covers.
        ends_on: Last day the plan covers.
        starting_balance: Liquid balance the plan started from, in dollars.
        months: JSON list of {month, money_in, money_out, end_balance}.
    """

    __tablename__ = "saved_plans"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    saved_at = Column(DateTime, nullable=False, default=utc_now)
    #: The student's own date when it was saved: what "before March began" is
    #: measured against.
    saved_on = Column(Date, nullable=False)
    starts_on = Column(Date, nullable=False)
    ends_on = Column(Date, nullable=False)
    starting_balance = Column(Float, nullable=False)
    #: The plan's monthly rows: [{month, money_in, money_out, end_balance}].
    months = Column(JSON, nullable=False, default=list)


class DegreeRequirementModel(Base):
    """Per-user row: one requirement of the student's programme.

    Attributes:
        id: Primary key.
        user_id: Owner.
        name: Requirement name.
        kind: "courses" (every item met) or "credits" (`credits_needed` from matching
            courses).
        items: JSON list of course codes, alternatives ("MATH 100 | MATH 180") or
            patterns ("CPSC 3xx", "300+").
        credits_needed: Credits required; set for "credits" requirements.
        shares: True when a course may count here and toward another requirement too.
        position: Display order.
        created_at: When the requirement was created.
    """

    __tablename__ = "degree_requirements"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    kind = Column(String, nullable=False)
    items = Column(JSON, nullable=False, default=list)
    credits_needed = Column(Float, nullable=True)
    shares = Column(Boolean, nullable=False, default=False)
    position = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=utc_now)


class CourseEquivalenceModel(Base):
    """Per-user row: courses taken that count as other courses.

    Matched by code, so a mapping survives deleting and re-adding a course. Applies
    once every source course is on the record, and replaces them so nothing counts
    twice.

    Attributes:
        id: Primary key.
        user_id: Owner.
        from_codes: JSON list of the codes taken.
        counts_as: JSON list of the codes they count as.
        credits: Credits granted; null uses the source courses' total.
        note: Free text; optional.
        created_at: When the mapping was created.
    """

    __tablename__ = "course_equivalences"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    from_codes = Column(JSON, nullable=False, default=list)
    counts_as = Column(JSON, nullable=False, default=list)
    credits = Column(Float, nullable=True)
    note = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)



# --------------------------------------------------------------------------
# Shared tables (Phase 2 Part A). Not per-user: every signed-in user reads
# them and no request writes them. rls.SHARED_READ_TABLES names each one, and
# only the owner-run review script, connected as the tables' owner, can write.
# --------------------------------------------------------------------------

#: The campuses a catalogue course can belong to (Phase 2 D7). A plain value,
#: not the vision's organizations tree, until leagues need one.
CAMPUSES = ("UBCV", "UBCO")
PREREQUISITE_KINDS = ("prerequisite", "corequisite")
"""Kinds of rule a catalogue prerequisite or a proposal may hold."""
#: Where a catalogue fact came from. `ubc-calendar` only once UBC has agreed
#: in writing (Phase 2 D2).
CATALOGUE_SOURCES = ("reviewed-proposal", "ubc-calendar")


def _one_of(column: str, values: tuple[str, ...]) -> str:
    """Return a SQL `IN` check that `column` holds one of `values`."""
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class CatalogueCourseModel(Base):
    """Shared-read: a course as the university offers it, one row for everyone.

    Written only by the owner-run review script. Unique per campus, subject and number.

    Attributes:
        id: Primary key.
        campus: "UBCV" or "UBCO"; checked by the database.
        subject: Subject code without a campus suffix, such as "CPSC".
        number: Course number as text, such as "210".
        title: Course title; optional.
        credits: Credit value; optional.
        created_at: When the row was added.
    """

    __tablename__ = "catalogue_courses"
    __table_args__ = (
        UniqueConstraint("campus", "subject", "number", name="uq_catalogue_course"),
        CheckConstraint(_one_of("campus", CAMPUSES), name="ck_catalogue_course_campus"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    campus = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    number = Column(String, nullable=False)
    title = Column(String, nullable=True)
    credits = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    prerequisites = relationship(
        "CataloguePrerequisiteModel", back_populates="course", cascade=cascade
    )


class CataloguePrerequisiteModel(Base):
    """Shared-read: what a catalogue course requires, for one calendar session.

    Unique per course, kind and session. A check constraint lets only a
    "ubc-calendar" row carry `source_text`, so wording from a student's syllabus never
    becomes shared.

    Attributes:
        id: Primary key.
        catalogue_course_id: The catalogue course; deleted with it.
        kind: "prerequisite" or "corequisite".
        session: Calendar session, such as "2026W" or "2026S".
        rule: JSON AND/OR tree over course keys, "one of" groups and credit thresholds.
        note: What the tree cannot say, such as year standing; optional.
        source: "reviewed-proposal" or "ubc-calendar".
        source_text: The calendar's own sentence; only on "ubc-calendar" rows.
        reviewed_at: When the row was reviewed.
    """

    __tablename__ = "catalogue_prerequisites"
    __table_args__ = (
        UniqueConstraint("catalogue_course_id", "kind", "session", name="uq_catalogue_prerequisite"),
        CheckConstraint(_one_of("kind", PREREQUISITE_KINDS), name="ck_catalogue_prerequisite_kind"),
        CheckConstraint(_one_of("source", CATALOGUE_SOURCES), name="ck_catalogue_prerequisite_source"),
        CheckConstraint(
            "source = 'ubc-calendar' OR source_text IS NULL",
            name="ck_catalogue_prerequisite_private_wording",
        ),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    catalogue_course_id = Column(
        Uuid, ForeignKey("catalogue_courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind = Column(String, nullable=False)
    #: The calendar session the rule is from, as "2026W" or "2026S" (fact C).
    session = Column(String, nullable=False)
    rule = Column(JSON, nullable=False)
    note = Column(String, nullable=True)
    source = Column(String, nullable=False)
    source_text = Column(String, nullable=True)
    reviewed_at = Column(DateTime, nullable=False, default=utc_now)

    course = relationship("CatalogueCourseModel", back_populates="prerequisites")


#: Where your own rule came from (Phase 2 item 4).
PROPOSAL_SOURCES = ("syllabus", "typed")
#: Where it stands in the owner's review (item 6). Pending until reviewed;
#: editing it puts it back to pending.
PROPOSAL_STATUSES = ("pending", "accepted", "rejected")


class PrerequisiteProposalModel(Base):
    """Per-user row: the student's own prerequisite rule for one of their courses.

    Applies to its owner at once and is also a proposal the owner-run review may copy,
    as a rule without its wording, into the shared catalogue. Unique per course and
    kind.

    Attributes:
        id: Primary key.
        user_id: Owner.
        course_id: The course the rule is for.
        kind: "prerequisite" or "corequisite".
        rule: JSON rule tree in the catalogue's shape.
        note: What the tree cannot say; optional.
        source: "syllabus" or "typed".
        source_text: The sentence from the student's syllabus; never copied to a shared
            row.
        session: Calendar session the course was in, when the first-year anchor is set.
        status: Review status: "pending", "accepted" or "rejected"; editing resets it to
            pending.
        created_at: When the proposal was created.
        updated_at: When it last changed.
        reviewed_at: When the review decided it; null while pending.
    """

    __tablename__ = "prerequisite_proposals"
    __table_args__ = (
        UniqueConstraint("course_id", "kind", name="uq_prerequisite_proposal"),
        CheckConstraint(_one_of("kind", PREREQUISITE_KINDS), name="ck_prerequisite_proposal_kind"),
        CheckConstraint(_one_of("source", PROPOSAL_SOURCES), name="ck_prerequisite_proposal_source"),
        CheckConstraint(_one_of("status", PROPOSAL_STATUSES), name="ck_prerequisite_proposal_status"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    course_id = Column(Uuid, ForeignKey("courses.id"), nullable=False, index=True)
    kind = Column(String, nullable=False)
    rule = Column(JSON, nullable=False)
    note = Column(String, nullable=True)
    source = Column(String, nullable=False)
    source_text = Column(String, nullable=True)
    session = Column(String, nullable=True)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now)
    reviewed_at = Column(DateTime, nullable=True)


#: What an invite is for (Phase 2 B2). Partners first; tasks and teams later.
INVITE_KINDS = ("partner",)
#: How long a link works.
INVITE_DAYS = 7


class InviteModel(Base):
    """Per-user row: an invite link the user sent to connect with someone.

    Only the token's SHA-256 is stored. Read and accepted only through definer
    functions, which reveal the inviter's display name and nothing more.

    Attributes:
        id: Primary key.
        user_id: The inviter.
        kind: What the invite is for; only "partner" today.
        token_hash: SHA-256 of the link's token; unique.
        created_at: When the link was made.
        expires_at: When the link stops working, 7 days after creation.
        used_at: When it was accepted; null while unused.
        used_by: Who accepted; no foreign key, so it never blocks deleting that account.
        revoked_at: When the inviter cancelled it; null otherwise.
    """

    __tablename__ = "invites"
    __table_args__ = (
        CheckConstraint(_one_of("kind", INVITE_KINDS), name="ck_invite_kind"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    kind = Column(String, nullable=False)
    token_hash = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    #: Who accepted. No foreign key: it is history, and must not stop that
    #: person's account from being deleted.
    used_by = Column(Uuid, nullable=True)
    revoked_at = Column(DateTime, nullable=True)


class PartnershipModel(Base):
    """Per-user row: the user's side of an accountability partnership.

    The accept function writes both sides together. Each row holds its owner's own
    figure, which the partner reads through `account_partner_figures` only while both
    rows point at each other. Unique per (user, partner); never the user themselves.

    Attributes:
        id: Primary key.
        user_id: Owner.
        partner_id: The partner; the row is deleted with the partner's account.
        partner_name: Partner's display name, copied when the partnership began.
        created_at: When the partnership began.
        week_percent: Owner's share of this week's tasks done, 0-100; null when nothing
            was due.
        streak_weeks: Owner's run of good weeks before this one.
        figure_on: Owner's local date when the figure was worked out.
    """

    __tablename__ = "partnerships"
    __table_args__ = (
        UniqueConstraint("user_id", "partner_id", name="uq_partnership"),
        CheckConstraint("user_id <> partner_id", name="ck_partnership_not_self"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    partner_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    partner_name = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    #: Your figure, as of `figure_on` (your local date when it was worked out).
    week_percent = Column(Float, nullable=True)
    streak_weeks = Column(Integer, nullable=False, default=0)
    figure_on = Column(Date, nullable=True)


#: How many people besides the owner a task can hold (Phase 2 D23). The same
#: figure is written into account_accept_task_invite, and a test holds the two
#: together.
MAX_TASK_MEMBERS = 8


class TaskMemberModel(Base):
    """Child of `tasks`; no direct write: someone else on one of the user's tasks.

    Only the task's owner sees or removes the row. The API's role may not insert or
    update it; `account_accept_task_invite` writes it for the person who accepted.
    Unique per task and member.

    Attributes:
        id: Primary key.
        task_id: Parent task; deleted with it.
        member_id: The member; deleted with the member's account.
        member_name: Member's display name, copied on joining.
        owner_name: Task owner's display name, copied on joining.
        joined_at: When the member joined.
    """

    __tablename__ = "task_members"
    __table_args__ = (UniqueConstraint("task_id", "member_id", name="uq_task_member"),)

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    task_id = Column(Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    #: The member. ON DELETE CASCADE because their purge acts as them and
    #: cannot see this row, which belongs to the task's owner.
    member_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    member_name = Column(String, nullable=False)
    owner_name = Column(String, nullable=False)
    joined_at = Column(DateTime, nullable=False, default=utc_now)

    task = relationship("TaskModel", back_populates="members")


class TaskInviteModel(Base):
    """Child of `tasks`: the link that lets people join one of the user's tasks.

    Usable by several people; making a new link cancels the old one. Only the token's
    SHA-256 is stored.

    Attributes:
        id: Primary key.
        task_id: Parent task; deleted with it.
        token_hash: SHA-256 of the link's token; unique.
        created_at: When the link was made.
        expires_at: When the link stops working.
        revoked_at: When it was cancelled; null otherwise.
    """

    __tablename__ = "task_invites"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    task_id = Column(Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)

    task = relationship("TaskModel", back_populates="invites")


#: How many people besides the owner an event can hold (Phase 2 D24). Written
#: into account_accept_event_invite too; a test holds the two together.
MAX_EVENT_MEMBERS = 8


class EventMemberModel(Base):
    """Child of `events`; no direct write: someone else on one of the user's events.

    Only the event's owner sees or removes the row; `account_accept_event_invite`
    writes it. A member only sees the event and may leave. Unique per event and member.

    Attributes:
        id: Primary key.
        event_id: Parent event; deleted with it.
        member_id: The member; deleted with the member's account.
        member_name: Member's display name, copied on joining.
        owner_name: Event owner's display name, copied on joining.
        joined_at: When the member joined.
    """

    __tablename__ = "event_members"
    __table_args__ = (UniqueConstraint("event_id", "member_id", name="uq_event_member"),)

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    event_id = Column(Uuid, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    #: ON DELETE CASCADE: the member's purge cannot see this row (it is the
    #: event owner's), so the database removes it.
    member_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    member_name = Column(String, nullable=False)
    owner_name = Column(String, nullable=False)
    joined_at = Column(DateTime, nullable=False, default=utc_now)

    event = relationship("EventModel", back_populates="members")


class EventInviteModel(Base):
    """Child of `events`: the link that lets people join one of the user's events.

    Usable by several people; one live link per event. Only the token's SHA-256 is
    stored.

    Attributes:
        id: Primary key.
        event_id: Parent event; deleted with it.
        token_hash: SHA-256 of the link's token; unique.
        created_at: When the link was made.
        expires_at: When the link stops working.
        revoked_at: When it was cancelled; null otherwise.
    """

    __tablename__ = "event_invites"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    event_id = Column(Uuid, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)

    event = relationship("EventModel", back_populates="invites")


#: Phase 2 item 13 (D25). Below this many contributors, a course-term's grade
#: counts are never written, even to the sealed table. The same figure is in
#: account_recount_grade_distributions; a test holds the two together.
COHORT_FLOOR = 5

#: Phase 3 D11. A term's answers reach a shown figure only this many days after
#: the term ends, when its asking window (term_review_service.ASK_UNTIL_DAYS)
#: has closed, so no figure moves in step with one person's answer. Written into
#: the read functions too; a test holds them together.
COUNTED_AFTER_DAYS = 180


class TermReviewModel(Base):
    """Per-user row: the student's end-of-term answers about one finished course.

    Holds no copy of the grade, only whether to add it to the course's distribution;
    the recount reads the grade from the course when it runs. Unique per user and
    course; the 1-5 ratings and the hours are checked by the database.

    Attributes:
        id: Primary key.
        user_id: Owner.
        course_id: The course reviewed.
        course_key: Snapshot of the key counts are grouped by, such as "UBCV CPSC 221".
        term_code: Snapshot of the term, such as "2025W1".
        hours_per_week: Typical weekly hours, 0-80.
        difficulty: Rating 1-5.
        clarity: Rating 1-5.
        would_take_again: Yes, no, or null for no answer.
        contribute_grade: Opt-in to add the grade to the distribution; changeable at any
            time.
        skipped: The student declined the review; it is not asked again.
        created_at: When the review was first saved.
        updated_at: When it last changed.
    """

    __tablename__ = "term_reviews"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id", name="uq_term_review"),
        CheckConstraint("difficulty IS NULL OR difficulty BETWEEN 1 AND 5", name="ck_term_review_difficulty"),
        CheckConstraint("clarity IS NULL OR clarity BETWEEN 1 AND 5", name="ck_term_review_clarity"),
        CheckConstraint("hours_per_week IS NULL OR hours_per_week BETWEEN 0 AND 80", name="ck_term_review_hours"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    course_id = Column(Uuid, ForeignKey("courses.id"), nullable=False, index=True)
    course_key = Column(String, nullable=True)
    term_code = Column(String, nullable=True)
    hours_per_week = Column(Integer, nullable=True)
    difficulty = Column(Integer, nullable=True)
    clarity = Column(Integer, nullable=True)
    would_take_again = Column(Boolean, nullable=True)
    #: Opt-in, and changeable at any time, after the answers have locked too.
    contribute_grade = Column(Boolean, nullable=False, default=False)
    #: "Not this one": asked, declined, not asked again.
    skipped = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now)

    course = relationship("CourseModel", back_populates="term_reviews", overlaps="term_reviews")


class GradeDistributionModel(Base):
    """Sealed: how many contributors' grades fell in each band, per course and term.

    The API's role can neither read nor write it. Only
    `account_recount_grade_distributions` writes it, rebuilding it whole and skipping
    any
    course-term below `COHORT_FLOOR` contributions. Unique per course, term and bucket.

    Attributes:
        id: Primary key.
        course_key: Course, such as "UBCV CPSC 221".
        term_code: Term, such as "2025W1".
        bucket: Band's lower bound: 0 for anything below 50, then 50, 55 ... 95.
        contributors: Grades counted in the band.
        computed_at: When the recount wrote it.
    """

    __tablename__ = "grade_distributions"
    __table_args__ = (
        UniqueConstraint("course_key", "term_code", "bucket", name="uq_grade_distribution"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    course_key = Column(String, nullable=False)
    term_code = Column(String, nullable=False)
    #: The band's lower bound: 0 for anything below 50, then 50, 55, ... 95.
    bucket = Column(Integer, nullable=False)
    contributors = Column(Integer, nullable=False)
    computed_at = Column(DateTime, nullable=False, default=utc_now)


class CourseIntelModel(Base):
    """Sealed: what term reviews say about a course, pooled across its closed terms.

    The API's role can neither read nor write it. Only `account_recount_course_intel`
    writes it, rebuilding it whole from each person's latest review of the course in
    a term whose asking window has closed (`COUNTED_AFTER_DAYS`). A figure with fewer
    than `COHORT_FLOOR` answers is written as null, and a course with no figure at
    the floor gets no row. Unique per course.

    Attributes:
        id: Primary key.
        course_key: Course, such as "UBCV CPSC 221".
        hours_answers: How many people gave their weekly hours; null below the floor.
        hours_median: Their median weekly hours; null below the floor.
        difficulty_answers: How many rated difficulty; null below the floor.
        difficulty_mean: Mean difficulty, 1-5; null below the floor.
        clarity_answers: How many rated instructor clarity; null below the floor.
        clarity_mean: Mean clarity, 1-5; null below the floor.
        again_answers: How many said whether they'd take it again; null below the floor.
        again_share: Percentage of those who said yes, 0-100; null below the floor.
        computed_at: When the recount wrote it.
    """

    __tablename__ = "course_intel"
    __table_args__ = (UniqueConstraint("course_key", name="uq_course_intel"),)

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    course_key = Column(String, nullable=False)
    hours_answers = Column(Integer, nullable=True)
    hours_median = Column(Float, nullable=True)
    difficulty_answers = Column(Integer, nullable=True)
    difficulty_mean = Column(Float, nullable=True)
    clarity_answers = Column(Integer, nullable=True)
    clarity_mean = Column(Float, nullable=True)
    again_answers = Column(Integer, nullable=True)
    again_share = Column(Float, nullable=True)
    computed_at = Column(DateTime, nullable=False, default=utc_now)


#: Phase 3 item 11. How a line at office hours looked, from a check-in.
OFFICE_HOUR_WAITS = ("none", "short", "long")
#: Check-ins older than this many days no longer count toward a slot.
OFFICE_HOUR_WINDOW_DAYS = 120


class OfficeHourCheckinModel(Base):
    """Per-user row: the student was at a course's office hours and said how the line was.

    Keeps the local weekday and hour it was made at, in the student's own time zone,
    and the course key it is counted under, as snapshots; the daily recount reads
    them into the sealed slot counts. Never shown to anyone else as a row.

    Attributes:
        id: Primary key.
        user_id: Owner.
        course_id: The course whose office hours these were.
        course_key: Snapshot of the key counts are grouped by, such as "UBCV CPSC 221".
        weekday: Local weekday, 0 Monday to 6 Sunday.
        hour: Local hour, 0-23.
        wait: How the line was: "none", "short" or "long".
        checked_at: When it was made (naive UTC).
    """

    __tablename__ = "office_hour_checkins"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_office_hour_checkin_weekday"),
        CheckConstraint("hour BETWEEN 0 AND 23", name="ck_office_hour_checkin_hour"),
        CheckConstraint(_one_of("wait", OFFICE_HOUR_WAITS), name="ck_office_hour_checkin_wait"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    course_id = Column(Uuid, ForeignKey("courses.id"), nullable=False, index=True)
    course_key = Column(String, nullable=False)
    weekday = Column(Integer, nullable=False)
    hour = Column(Integer, nullable=False)
    wait = Column(String, nullable=False)
    checked_at = Column(DateTime, nullable=False, default=utc_now)

    course = relationship("CourseModel", back_populates="office_hour_checkins", overlaps="office_hour_checkins")


class OfficeHourSlotModel(Base):
    """Sealed: how busy a course's office hours usually are, per weekday and hour.

    The API's role can neither read nor write it. Only `account_recount_office_hours`
    writes it, rebuilding it whole from each person's latest check-in per slot in the
    last `OFFICE_HOUR_WINDOW_DAYS`, and writing no slot below `COHORT_FLOOR` people.
    Unique per course, weekday and hour.

    Attributes:
        id: Primary key.
        course_key: Course, such as "UBCV CPSC 221".
        weekday: Local weekday, 0 Monday to 6 Sunday.
        hour: Local hour, 0-23.
        people: Distinct people whose check-in counted.
        none_votes: How many found no line.
        short_votes: How many found a short line.
        long_votes: How many found a long line.
        computed_at: When the recount wrote it.
    """

    __tablename__ = "office_hour_slots"
    __table_args__ = (UniqueConstraint("course_key", "weekday", "hour", name="uq_office_hour_slot"),)

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    course_key = Column(String, nullable=False)
    weekday = Column(Integer, nullable=False)
    hour = Column(Integer, nullable=False)
    people = Column(Integer, nullable=False)
    none_votes = Column(Integer, nullable=False)
    short_votes = Column(Integer, nullable=False)
    long_votes = Column(Integer, nullable=False)
    computed_at = Column(DateTime, nullable=False, default=utc_now)


#: Phase 3 item 12. Hours in a working year, for an offer's hourly equivalent:
#: 40 a week for 52 weeks. A monthly offer is 12 months of it.
WORK_HOURS_PER_YEAR = 2080


class SalaryShareModel(Base):
    """Per-user row: the student's consent to count one offer's pay, with no name.

    Holds no amount: the daily recount reads the offer from the application when it
    runs, so a corrected offer counts as corrected and a withdrawn consent (the row
    deleted) is gone at the next recount. One per application.

    Attributes:
        id: Primary key.
        user_id: Owner.
        application_id: The application whose offer is shared.
        shared_at: When the student chose to share it; the order batches are filled in.
    """

    __tablename__ = "salary_shares"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    #: A unique index rather than a constraint, so it also serves the foreign key.
    application_id = Column(Uuid, ForeignKey("job_applications.id"), nullable=False, unique=True, index=True)
    shared_at = Column(DateTime, nullable=False, default=utc_now)

    application = relationship("JobApplicationModel", back_populates="salary_share", overlaps="salary_shares")


class SalaryFigureModel(Base):
    """Sealed: typical hourly pay at one employer, from verified shared offers.

    The API's role can neither read nor write it. Only `account_recount_salaries`
    writes it, rebuilding it whole from each person's latest shared offer per
    employer. An offer counts only once verified: it matches the person's own
    recorded job there within 5%, or 5 people's offers there agree within 10%. Only
    whole batches of 5 verified offers, oldest first, are counted, so one new share
    never shows as a change. Unique per employer.

    Attributes:
        id: Primary key.
        employer_key: The employer's name normalised (`aggregates.employer_key`).
        employer: The employer's name as most people wrote it.
        people: Offers counted, a multiple of 5.
        median: Median hourly pay in dollars.
        p25: The 25th percentile, the bottom of the middle half.
        p75: The 75th percentile, the top of the middle half.
        computed_at: When the recount wrote it.
    """

    __tablename__ = "salary_figures"
    __table_args__ = (UniqueConstraint("employer_key", name="uq_salary_figure_employer"),)

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    employer_key = Column(String, nullable=False)
    employer = Column(String, nullable=False)
    people = Column(Integer, nullable=False)
    median = Column(Float, nullable=False)
    p25 = Column(Float, nullable=False)
    p75 = Column(Float, nullable=False)
    computed_at = Column(DateTime, nullable=False, default=utc_now)


#: How many people besides the captain a team can hold (Phase 2 D26). Written
#: into account_accept_team_invite too; a test holds the two together.
MAX_TEAM_MEMBERS = 30


class TeamModel(Base):
    """Per-user row: a team on the Fitness page, owned by its captain.

    Members, the link and the games hang beneath it; other players reach it only through
    definer functions.

    Attributes:
        id: Primary key.
        user_id: The captain.
        name: Team name.
        sport: Free text, such as "Ultimate"; optional.
        created_at: When the team was created.
    """

    __tablename__ = "teams"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    #: Free text: "Ultimate", "Rec volleyball". No per-sport templates yet.
    sport = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    members = relationship("TeamMemberModel", back_populates="team", cascade="all, delete-orphan")
    invites = relationship("TeamInviteModel", back_populates="team", cascade="all, delete-orphan")
    games = relationship("GameModel", back_populates="team", cascade="all, delete-orphan")


class TeamMemberModel(Base):
    """Child of `teams`; no direct write: someone on a team.

    Only the captain sees or removes the row; `account_accept_team_invite` writes it.
    Unique per team and member.

    Attributes:
        id: Primary key.
        team_id: Parent team; deleted with it.
        member_id: The player; deleted with the player's account.
        member_name: Player's display name, copied on joining.
        owner_name: Captain's display name, copied on joining.
        joined_at: When the player joined.
    """

    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("team_id", "member_id", name="uq_team_member"),)

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    team_id = Column(Uuid, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    member_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    member_name = Column(String, nullable=False)
    owner_name = Column(String, nullable=False)
    joined_at = Column(DateTime, nullable=False, default=utc_now)

    team = relationship("TeamModel", back_populates="members")


class TeamInviteModel(Base):
    """Child of `teams`: a team's join link; many may use it, one live per team.

    Attributes:
        id: Primary key.
        team_id: Parent team; deleted with it.
        token_hash: SHA-256 of the link's token; unique.
        created_at: When the link was made.
        expires_at: When the link stops working.
        revoked_at: When it was cancelled; null otherwise.
    """

    __tablename__ = "team_invites"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    team_id = Column(Uuid, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)

    team = relationship("TeamModel", back_populates="invites")


class GameModel(Base):
    """Child of `teams`; no direct write: one game a team played.

    The API's role may only read and delete it; every write, the captain's included,
    goes through a definer function, so a score counts only once someone else confirms
    it. Players are kept as an id with no foreign key plus a copied name. Scores are
    checked to 0-999.

    Attributes:
        id: Primary key.
        team_id: Parent team; deleted with it.
        played_on: Date of the game.
        opponent: Opponent's name.
        our_score: The team's score.
        their_score: The opponent's score.
        recorded_by: Id of the player who recorded it.
        recorded_by_name: Their name, copied.
        confirmed_by: Id of the player who confirmed it; null while unconfirmed.
        confirmed_by_name: Their name, copied.
        confirmed_at: When it was confirmed.
        disputed_by: Id of the player disputing it; null when undisputed.
        disputed_by_name: Their name, copied.
        disputed_our: The disputer's version of our score; set only with `disputed_by`.
        disputed_their: The disputer's version of their score; set only with
            `disputed_by`.
        created_at: When it was recorded.
    """

    __tablename__ = "games"
    __table_args__ = (
        CheckConstraint("our_score BETWEEN 0 AND 999 AND their_score BETWEEN 0 AND 999", name="ck_game_scores"),
        CheckConstraint(
            "(disputed_by IS NULL AND disputed_our IS NULL AND disputed_their IS NULL) OR "
            "(disputed_by IS NOT NULL AND disputed_our BETWEEN 0 AND 999 AND disputed_their BETWEEN 0 AND 999)",
            name="ck_game_dispute",
        ),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    team_id = Column(Uuid, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    played_on = Column(Date, nullable=False)
    opponent = Column(String, nullable=False)
    our_score = Column(Integer, nullable=False)
    their_score = Column(Integer, nullable=False)
    recorded_by = Column(Uuid, nullable=False)
    recorded_by_name = Column(String, nullable=False)
    confirmed_by = Column(Uuid, nullable=True)
    confirmed_by_name = Column(String, nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    disputed_by = Column(Uuid, nullable=True)
    disputed_by_name = Column(String, nullable=True)
    disputed_our = Column(Integer, nullable=True)
    disputed_their = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    team = relationship("TeamModel", back_populates="games")


#: Phase 3 item 1 (D2, D3): the statuses an application moves through. The
#: last four end it; "no reply" can still be followed by a late answer.
APPLICATION_STATUSES = (
    "applied", "screening", "interview", "offer", "accepted", "rejected", "no_reply", "withdrawn",
)
OFFER_PERIODS = ("hourly", "monthly", "yearly")
"""Periods an offer's pay may be quoted per."""


class JobApplicationModel(Base):
    """Per-user row: one job or internship application.

    `status` repeats the latest step so lists need not read every history; the history
    in `application_steps` is what the statistics read. Status and offer period are
    checked by the database.

    Attributes:
        id: Primary key.
        user_id: Owner.
        company: Employer name.
        role: Job title applied for.
        applied_on: Date applied; decides which seasons include it.
        source: Where the posting was found; optional.
        link: Posting URL; optional.
        location: Job location; optional.
        notes: Free text; optional.
        status: Latest status: "applied", "screening", "interview", "offer", "accepted",
            "rejected", "no_reply" or "withdrawn".
        deadline: Application deadline, also shown on the calendar; optional.
        follow_up_on: Date to follow up; optional.
        offer_amount: Offered pay in dollars; optional.
        offer_period: "hourly", "monthly" or "yearly"; null without an offer.
        created_at: When the application was recorded.
        updated_at: When it last changed.
    """

    __tablename__ = "job_applications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('applied','screening','interview','offer','accepted','rejected','no_reply','withdrawn')",
            name="ck_application_status",
        ),
        CheckConstraint(
            "offer_period IS NULL OR offer_period IN ('hourly','monthly','yearly')",
            name="ck_application_offer_period",
        ),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    company = Column(String, nullable=False)
    role = Column(String, nullable=False)
    applied_on = Column(Date, nullable=False)
    #: Where you found it: a job board, a referral, a career fair.
    source = Column(String, nullable=True)
    link = Column(String, nullable=True)
    location = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    status = Column(String, nullable=False, default="applied")
    #: Shown on the calendar too (D4).
    deadline = Column(Date, nullable=True)
    follow_up_on = Column(Date, nullable=True)
    offer_amount = Column(Float, nullable=True)
    offer_period = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now)

    steps = relationship(
        "ApplicationStepModel", back_populates="application", cascade=cascade,
        order_by="(ApplicationStepModel.on_date, ApplicationStepModel.created_at)",
    )
    salary_share = relationship("SalaryShareModel", back_populates="application", cascade=cascade, uselist=False,
                                overlaps="salary_shares")


class ApplicationStepModel(Base):
    """Child of `job_applications`: one change of status and the day it happened.

    The first step, "applied", is written with the application and moves with its date.

    Attributes:
        id: Primary key.
        application_id: Parent application; deleted with it.
        status: The status reached, from the same list as `job_applications.status`.
        on_date: Day it happened.
        note: Free text; optional.
        created_at: When the step was recorded.
    """

    __tablename__ = "application_steps"
    __table_args__ = (
        CheckConstraint(
            "status IN ('applied','screening','interview','offer','accepted','rejected','no_reply','withdrawn')",
            name="ck_application_step_status",
        ),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    application_id = Column(
        Uuid, ForeignKey("job_applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status = Column(String, nullable=False)
    on_date = Column(Date, nullable=False)
    note = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    application = relationship("JobApplicationModel", back_populates="steps")


class ApplicationSeasonModel(Base):
    """Per-user row: a named recruiting season, a month range used as a filter.

    An application belongs to every season whose months include its applied date, so
    seasons may overlap.

    Attributes:
        id: Primary key.
        user_id: Owner.
        name: Season name.
        starts_month: First day of the first month.
        ends_month: First day of the last month, which counts whole; never before
            `starts_month`.
        created_at: When the season was created.
    """

    __tablename__ = "application_seasons"
    __table_args__ = (
        CheckConstraint("ends_month >= starts_month", name="ck_application_season_order"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    starts_month = Column(Date, nullable=False)
    ends_month = Column(Date, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
