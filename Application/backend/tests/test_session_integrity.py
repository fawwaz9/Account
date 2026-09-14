"""Regression tests for audit #21: a stolen token could not be revoked.

Covers the revocation mechanism (a token's session epoch against the account's),
the claims a token is now required to carry, and the login throttle from audit #6.
"""
import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.Auth.services.login_throttle import SlidingWindowLimiter, account_key
from app.Auth.services.session_service import (
    create_access_token,
    decode_access_token,
    is_revoked,
)
from app.config import JWT_ALGORITHM, settings
from app.Users.services.user_service import set_password


# ------------------------------------------------------------------ claims --

def test_token_round_trips_with_its_epoch(user):
    claims = decode_access_token(create_access_token(user.id, 7))

    assert claims.user_id == user.id
    assert claims.session_epoch == 7


def test_a_token_with_no_epoch_claim_reads_as_epoch_zero():
    """Tokens minted before the claim existed must not all be refused at once."""
    token = jwt.encode(
        {
            "sub": "00000000-0000-0000-0000-000000000001",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        settings.JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )

    assert decode_access_token(token).session_epoch == 0


def test_a_token_without_sub_is_rejected_not_a_500():
    """audit #47: the old decoder raised KeyError and surfaced as a 500."""
    token = jwt.encode(
        {"exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        settings.JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )

    with pytest.raises(ValueError):
        decode_access_token(token)


def test_a_token_without_exp_is_rejected():
    """A token that never expires used to verify happily."""
    token = jwt.encode(
        {"sub": "00000000-0000-0000-0000-000000000001"},
        settings.JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )

    with pytest.raises(ValueError):
        decode_access_token(token)


def test_a_sub_that_is_not_a_uuid_is_rejected():
    token = jwt.encode(
        {
            "sub": "not-a-uuid",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        settings.JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )

    with pytest.raises(ValueError):
        decode_access_token(token)


# -------------------------------------------------------------- revocation --

def test_a_matching_epoch_is_not_revoked():
    assert is_revoked(0, 0) is False
    assert is_revoked(3, 3) is False


def test_a_stale_epoch_is_revoked():
    assert is_revoked(0, 1) is True
    assert is_revoked(2, 5) is True


def test_an_epoch_from_the_future_is_also_refused():
    """Only reachable if something has gone astray; fail closed either way."""
    assert is_revoked(5, 2) is True


def test_a_null_epoch_reads_as_zero():
    """Rows predating the column come back as NULL, not 0."""
    assert is_revoked(0, None) is False
    assert is_revoked(1, None) is True


def test_setting_a_password_revokes_every_outstanding_session(db, user):
    """The point of the whole mechanism: a password change kills old tokens."""
    old_claims = decode_access_token(create_access_token(user.id, user.session_epoch or 0))
    assert is_revoked(old_claims.session_epoch, user.session_epoch) is False

    set_password(db, user, "a-new-password")
    db.refresh(user)

    assert user.session_epoch == 1
    assert is_revoked(old_claims.session_epoch, user.session_epoch) is True


def test_a_token_minted_right_after_the_change_still_works(db, user):
    """The flaw that sank the timestamp approach: no same-second ambiguity here.

    With `iat` compared against a revocation *time*, signing back in within the
    same second as the password change was refused, because whole-second `iat`
    cannot distinguish before from after. Integer equality has no such window.
    """
    set_password(db, user, "a-new-password")
    db.refresh(user)

    fresh = decode_access_token(create_access_token(user.id, user.session_epoch))
    assert is_revoked(fresh.session_epoch, user.session_epoch) is False


def test_each_password_change_revokes_again(db, user):
    set_password(db, user, "first-password")
    db.refresh(user)
    after_first = decode_access_token(create_access_token(user.id, user.session_epoch))

    set_password(db, user, "second-password", current_password="first-password")
    db.refresh(user)

    assert user.session_epoch == 2
    assert is_revoked(after_first.session_epoch, user.session_epoch) is True


# ---------------------------------------------------------------- throttle --

def test_the_limiter_allows_up_to_its_ceiling_then_refuses():
    limiter = SlidingWindowLimiter(max_attempts=3, window_seconds=60)

    for _ in range(3):
        assert limiter.retry_after("k") is None
        limiter.record_attempt("k")

    retry = limiter.retry_after("k")
    assert retry is not None and retry > 0


def test_a_success_clears_the_history():
    """One forgotten password then the right one must not leave you locked out."""
    limiter = SlidingWindowLimiter(max_attempts=2, window_seconds=60)
    limiter.record_attempt("k")
    limiter.record_attempt("k")
    assert limiter.retry_after("k") is not None

    limiter.reset("k")
    assert limiter.retry_after("k") is None


def test_the_window_slides():
    limiter = SlidingWindowLimiter(max_attempts=1, window_seconds=1)
    limiter.record_attempt("k")
    assert limiter.retry_after("k") is not None

    time.sleep(1.1)
    assert limiter.retry_after("k") is None, "the attempt should have aged out"


def test_keys_do_not_share_a_budget():
    limiter = SlidingWindowLimiter(max_attempts=1, window_seconds=60)
    limiter.record_attempt("one")

    assert limiter.retry_after("one") is not None
    assert limiter.retry_after("two") is None


def test_account_keys_are_case_and_whitespace_insensitive():
    """Otherwise " Owner@Example.com " is a fresh budget every time."""
    assert account_key(" Owner@Example.com ", "1.2.3.4") == account_key(
        "owner@example.com", "1.2.3.4"
    )


def test_the_same_address_from_a_different_client_is_a_different_key():
    assert account_key("a@b.com", "1.2.3.4") != account_key("a@b.com", "5.6.7.8")


def test_tracked_keys_are_capped():
    """An attacker rotating the address they guess must not grow this forever."""
    limiter = SlidingWindowLimiter(max_attempts=5, window_seconds=600)
    for index in range(5000):
        limiter.record_attempt(f"key-{index}")

    assert len(limiter._hits) <= 4096
