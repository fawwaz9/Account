"""Deleting a thing that other rows only mention.

Found by test_noninterference.py, which deletes from a world where every table
has a row: three deletes failed the foreign key and answered 500 in front of
the user. A course could not be deleted once an expense was tagged to it, a
reminder named it or a repeating task belonged to it; a spending category
could not be deleted once a recurring rule used it. (A job with a confirmed
shift is in test_jobs.py.)

The fix keeps every mentioning row and clears the mention, which is what the
dialogs already promise: a category "removes the label only", and money that
was spent stays spent.
"""
import datetime

from app._database.models import (
    RecurringTaskModel,
    RecurringTransactionModel,
    ReminderModel,
    TransactionModel,
)
from app.Finances.services.budget_service import delete_category
from app.Grades.services.course_service import delete_course
from conftest import make_account, make_category, make_course

ON = datetime.date(2026, 9, 14)


def test_a_course_others_mention_can_be_deleted(db, user):
    course = make_course(db, user.id, "CPSC 210")
    account = make_account(db, user.id, "Chequing")
    db.add_all([
        TransactionModel(user_id=user.id, account_id=account.id, kind="expense", amount=-80.0,
                         description="textbook", occurred_on=ON, course_id=course.id),
        ReminderModel(user_id=user.id, title="office hours", course_id=course.id,
                      remind_at=datetime.datetime(2026, 9, 14, 9)),
        RecurringTaskModel(user_id=user.id, title="weekly reading", course_id=course.id,
                           starts_on=ON, recur_freq="weekly", recur_interval=1, active=True),
    ])
    db.commit()

    assert delete_course(db, user.id, course.id) is not None

    # Kept, unlinked.
    assert [t.course_id for t in db.query(TransactionModel).all()] == [None]
    assert [r.course_id for r in db.query(ReminderModel).all()] == [None]
    assert [r.course_id for r in db.query(RecurringTaskModel).all()] == [None]


def test_a_category_a_recurring_rule_uses_can_be_deleted(db, user):
    account = make_account(db, user.id, "Chequing")
    category = make_category(db, user.id, "Subscriptions")
    db.add(RecurringTransactionModel(
        user_id=user.id, kind="expense", account_id=account.id, amount=15.0,
        description="music", category_id=category.id, starts_on=ON,
        recur_freq="monthly", recur_interval=1, active=True,
    ))
    db.commit()

    assert delete_category(db, user.id, category.id) is not None

    rule = db.query(RecurringTransactionModel).one()
    assert rule.category_id is None and rule.active

