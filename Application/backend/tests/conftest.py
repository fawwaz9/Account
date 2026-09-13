"""Test fixtures: every test gets a fresh in-memory database.

Deliberately never uses ``SessionLocal`` or the engine in app._database.db,
which are bound to the real data/app.db file. A test that can reach the live
ledger is worse than no test. The module itself is in the import graph either
way -- models.py imports ``Base`` from it -- and importing it issues no DDL;
what matters is that nothing here binds a session to that engine.
"""
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app._database.db import apply_sqlite_pragmas  # noqa: E402
from app._database.models import (  # noqa: E402
    AccountModel,
    Base,
    CourseCategoryWeightModel,
    CourseModel,
    SpendCategoryModel,
    UserModel,
)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        # One shared connection, or ":memory:" gives each connection its own
        # empty database and create_all appears to have done nothing.
        poolclass=StaticPool,
    )

    # The same pragmas the real engine sets, so the suite runs under the rules
    # the app runs under. Without foreign_keys ON here, every cascade test
    # passes whether or not the cascade is actually enforced.
    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection, _record):
        apply_sqlite_pragmas(dbapi_connection)

    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def user(db):
    return make_user(db, "owner@example.com")


def make_user(db, email: str) -> UserModel:
    row = UserModel(id=uuid.uuid4(), name=email.split("@")[0], email=email, email_verified=True)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def make_account(db, user_id: uuid.UUID, name: str, share: float = 0.0) -> AccountModel:
    row = AccountModel(
        id=uuid.uuid4(), user_id=user_id, name=name, kind="spending",
        income_share=share, archived=False, position=0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def make_category(db, user_id: uuid.UUID, name: str) -> SpendCategoryModel:
    row = SpendCategoryModel(
        id=uuid.uuid4(), user_id=user_id, name=name, archived=False, position=0
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def make_course(db, user_id: uuid.UUID, code: str, **overrides) -> CourseModel:
    fields = {
        "name": f"{code} course", "semester": "Fall", "year": 3, "credits": 3.0,
        "required": True, "final_grade": 0.0, "average": 0.0,
        "no_final": False, "transfer_credit": False, "archived": False,
    }
    weights = overrides.pop("category_weights", {"Assignment": 50.0, "Final": 50.0})
    fields.update(overrides)

    row = CourseModel(id=uuid.uuid4(), user_id=user_id, code=code, **fields)
    db.add(row)
    db.flush()
    for category, weight in weights.items():
        db.add(CourseCategoryWeightModel(course_id=row.id, category=category, weight=weight))
    db.commit()
    db.refresh(row)
    return row
