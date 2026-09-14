"""Deleting an account is a request, not an execution.

The thing being protected is an entire academic and financial record, and the
mistake being protected against -- a misclick, or a stolen session asking for
it -- is usually noticed within a month. So the row is marked, every session
dies, and nothing is actually removed until the grace period has run out.
"""
import uuid
from datetime import date, timedelta

from app._database.models import AccountModel, CourseModel, UserModel, utc_now
from app.Users.schemas.user import DELETION_GRACE_DAYS, User
from app.Users.services.user_service import (
    delete_user,
    deletes_on,
    get_user,
    purge_expired_users,
    restore_user,
)
from conftest import make_account, make_course, make_user


def today_utc() -> date:
    """The date the *service* is working in, which is UTC.

    `deleted_at` is stamped with `utc_now()`, so every deadline derived from it
    is a UTC date. Comparing those against a local `date.today()` agrees only
    while the two happen to fall on the same day -- so these tests passed in the
    morning and failed in the evening for anyone behind UTC. The reference has
    to come from the same clock the code uses.
    """
    return utc_now().date()


def past_the_deadline(days_over: int = 1) -> date:
    return today_utc() + timedelta(days=DELETION_GRACE_DAYS + days_over)


# ------------------------------------------------------ deletion is a request --

def test_deleting_keeps_everything(db, user):
    make_course(db, user.id, "COSC 111")
    make_account(db, user.id, "Chequing")

    delete_user(db, user.id)

    assert db.query(UserModel).count() == 1
    assert db.query(CourseModel).count() == 1
    assert db.query(AccountModel).count() == 1


def test_deleting_records_when_it_was_asked_for(db, user):
    deleted = delete_user(db, user.id)

    assert deleted.deleted_at is not None
    assert deletes_on(deleted) == today_utc() + timedelta(days=DELETION_GRACE_DAYS)


def test_deleting_ends_every_session(db, user):
    """A stolen token that asked for this must not keep using the account."""
    before = user.session_epoch or 0

    delete_user(db, user.id)

    assert user.session_epoch == before + 1


def test_deleting_twice_does_not_move_the_deadline(db, user):
    """Otherwise asking again quietly buys another thirty days."""
    first = delete_user(db, user.id).deleted_at

    again = delete_user(db, user.id)

    assert again.deleted_at == first
    assert (user.session_epoch or 0) == 1


def test_an_account_pending_deletion_is_still_readable(db, user):
    """Sign-in has to keep working, or restore is unreachable."""
    delete_user(db, user.id)

    assert get_user(db, user.id) is not None


# --------------------------------------------------------------- restoring --

def test_restoring_clears_the_pending_deletion(db, user):
    delete_user(db, user.id)

    restored = restore_user(db, user.id)

    assert restored.deleted_at is None
    assert deletes_on(restored) is None


def test_a_restored_account_is_no_longer_purged(db, user):
    make_course(db, user.id, "COSC 111")
    delete_user(db, user.id)
    restore_user(db, user.id)

    assert purge_expired_users(db, on_day=past_the_deadline()) == 0
    assert db.query(CourseModel).count() == 1


def test_restoring_an_account_that_was_never_deleted_does_nothing(db, user):
    assert restore_user(db, user.id) is None


def test_restoring_an_unknown_user_does_nothing(db):
    assert restore_user(db, uuid.uuid4()) is None


# ----------------------------------------------------------------- purging --

def test_nothing_is_purged_inside_the_grace_period(db, user):
    make_course(db, user.id, "COSC 111")
    delete_user(db, user.id)

    assert purge_expired_users(db) == 0
    assert db.query(UserModel).count() == 1


def test_the_day_before_the_deadline_is_still_safe(db, user):
    """The boundary, in the direction that loses data if it is wrong."""
    delete_user(db, user.id)

    purged = purge_expired_users(db, on_day=today_utc() + timedelta(days=DELETION_GRACE_DAYS - 1))

    assert purged == 0
    assert db.query(UserModel).count() == 1


def test_an_expired_account_is_purged(db, user):
    make_course(db, user.id, "COSC 111")
    delete_user(db, user.id)

    assert purge_expired_users(db, on_day=past_the_deadline()) == 1
    assert db.query(UserModel).count() == 0
    assert db.query(CourseModel).count() == 0


def test_purging_leaves_live_accounts_alone(db, user):
    """The filter is what makes this safe to run on every startup."""
    other = make_user(db, "other@example.com")
    make_course(db, other.id, "AAAA 100")
    delete_user(db, user.id)

    purge_expired_users(db, on_day=past_the_deadline())

    assert get_user(db, other.id) is not None
    assert db.query(CourseModel).count() == 1


def test_purging_is_safe_to_run_twice(db, user):
    delete_user(db, user.id)

    assert purge_expired_users(db, on_day=past_the_deadline()) == 1
    assert purge_expired_users(db, on_day=past_the_deadline()) == 0


# ------------------------------------------------------------ what is sent --

def serialisable(db, user):
    """The fixture user has no google_id, which the auth-consistency validator
    refuses for the default `google` provider. Irrelevant to the deadline, so
    it is satisfied rather than worked around."""
    user.google_id = "google-123"
    db.commit()
    return user


def test_the_api_reports_the_deadline(db, user):
    serialisable(db, user)
    delete_user(db, user.id)

    sent = User.model_validate(user, from_attributes=True)

    assert sent.deleted_at is not None
    assert sent.deletes_on == today_utc() + timedelta(days=DELETION_GRACE_DAYS)


def test_a_live_account_reports_no_deadline(db, user):
    serialisable(db, user)

    sent = User.model_validate(user, from_attributes=True)

    assert sent.deleted_at is None
    assert sent.deletes_on is None
