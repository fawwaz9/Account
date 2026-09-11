"""Regression tests for the account-takeover path in Ideas/audit.md."""
import uuid

from app.Users.schemas.user import UserUpdate
from app.Users.services.user_service import link_google_to_account, update_user
from conftest import make_user


def test_changing_email_clears_the_verified_flag(db, user):
    """audit #1: the flag survived an email change, defeating the link guard."""
    assert user.email_verified is True

    update_user(db, user.id, UserUpdate(email="somebody-else@example.com"))

    db.refresh(user)
    assert user.email == "somebody-else@example.com"
    assert user.email_verified is False


def test_repeating_the_same_email_leaves_the_flag_alone(db, user):
    update_user(db, user.id, UserUpdate(email=user.email))

    db.refresh(user)
    assert user.email_verified is True


def test_google_link_drops_a_password_on_a_hijacked_address(db):
    """The whole chain: verified account repointed at a victim's address."""
    attacker = make_user(db, "attacker@example.com")
    attacker.password_hash = "a-real-hash"
    db.commit()

    update_user(db, attacker.id, UserUpdate(email="victim@example.com"))
    db.refresh(attacker)

    # The victim now signs in with Google on their own address.
    link_google_to_account(db, attacker, google_id=str(uuid.uuid4()))

    db.refresh(attacker)
    assert attacker.password_hash is None, "the unproven password must not survive"
