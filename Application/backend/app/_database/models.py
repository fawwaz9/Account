import uuid
from sqlalchemy import (
    Column, String, Float, Boolean, Integer, ForeignKey, Date, DateTime, Time, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import Uuid
from app._database.db import Base

cascade = "all, delete-orphan"

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

    user = relationship("UserModel", back_populates="courses")
    grades = relationship("GradeModel", back_populates="course", cascade=cascade)
    category_weight_rows = relationship(
        "CourseCategoryWeightModel", back_populates="course", cascade=cascade
    )

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

    course = relationship("CourseModel", back_populates="grades")

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

    account = relationship("AccountModel", back_populates="transactions")
    category = relationship("SpendCategoryModel", back_populates="transactions")


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
