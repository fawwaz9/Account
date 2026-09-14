"""Only invited addresses may create an account.

`/register` was open to anyone who could reach it, and so -- less obviously --
was `/auth/google`, because that route creates accounts too. An allowlist
guarding one door and not the other is not a gate.
"""
import uuid

import pytest

from app.Auth.schemas.credentials import RegisterRequest
from app.Auth.services.signup_policy import allowed_emails, may_sign_up
from app.Users.schemas.user import UserCreate
from app.Users.services.user_service import (
    create_local_user,
    get_or_create_user_by_google_id,
)
from conftest import make_user


def invite(monkeypatch, *emails):
    monkeypatch.setenv("ALLOWED_SIGNUP_EMAILS", ", ".join(emails))


def registration(email="invited@example.com"):
    return RegisterRequest(name="Invited", email=email, password="correct-horse-battery")


def google(email="invited@example.com"):
    return UserCreate(name="Invited", email=email, google_id=str(uuid.uuid4()))


# ------------------------------------------------------------ parsing the list --

def test_an_unset_list_allows_everyone(monkeypatch):
    """The default, so a fresh clone can create its first account."""
    monkeypatch.delenv("ALLOWED_SIGNUP_EMAILS", raising=False)
    assert allowed_emails() == set()
    assert may_sign_up("anyone@example.com")


def test_the_list_survives_the_spaces_people_type(monkeypatch):
    invite(monkeypatch, "a@example.com", "b@example.com")
    assert allowed_emails() == {"a@example.com", "b@example.com"}


def test_matching_ignores_case(monkeypatch):
    """Addresses are not case sensitive, and nobody types them consistently."""
    invite(monkeypatch, "Invited@Example.com")
    assert may_sign_up("invited@example.com")
    assert may_sign_up("  INVITED@EXAMPLE.COM  ")


# -------------------------------------------------------------- the front door --

def test_an_invited_address_can_register(monkeypatch, db):
    invite(monkeypatch, "invited@example.com")
    user = create_local_user(db, registration())
    assert user.email == "invited@example.com"


def test_an_uninvited_address_cannot_register(monkeypatch, db):
    invite(monkeypatch, "invited@example.com")
    with pytest.raises(ValueError, match="invitation only"):
        create_local_user(db, registration("stranger@example.com"))


def test_nothing_is_written_when_registration_is_refused(monkeypatch, db):
    """The refusal comes before the insert, not after it."""
    from app._database.models import UserModel

    invite(monkeypatch, "invited@example.com")
    before = db.query(UserModel).count()
    with pytest.raises(ValueError):
        create_local_user(db, registration("stranger@example.com"))
    assert db.query(UserModel).count() == before


# --------------------------------------------------------------- the side door --

def test_an_invited_address_can_sign_up_through_google(monkeypatch, db):
    invite(monkeypatch, "invited@example.com")
    user = get_or_create_user_by_google_id(db, google())
    assert user.email == "invited@example.com"


def test_an_uninvited_address_cannot_sign_up_through_google(monkeypatch, db):
    """The door an allowlist on `create_local_user` alone would leave open.

    `get_or_create_user_by_google_id` creates accounts as readily as
    registration does, so guarding only the password path is not a gate -- it is
    a sign on one of two entrances.
    """
    invite(monkeypatch, "invited@example.com")
    with pytest.raises(ValueError, match="invitation only"):
        get_or_create_user_by_google_id(db, google("stranger@example.com"))


# ------------------------------------------------ it gates joining, not signing in --

def test_an_existing_account_still_works_when_it_is_not_on_the_list(monkeypatch, db):
    """Adding the list must not sign out the people already using the app.

    And removing an address must decline a new signup rather than destroy
    access to real data -- taking someone's access away is a deletion, and
    deletion has its own deliberate, reversible path.
    """
    existing = make_user(db, "already-here@example.com")
    existing.google_id = "google-abc"
    db.commit()

    invite(monkeypatch, "someone-else@example.com")

    found = get_or_create_user_by_google_id(
        db, UserCreate(name="Already Here", email="already-here@example.com", google_id="google-abc")
    )
    assert found.id == existing.id


def test_linking_google_to_an_existing_account_is_not_gated(monkeypatch, db):
    """Also a find, not a create: the account already exists."""
    existing = make_user(db, "already-here@example.com")
    db.commit()

    invite(monkeypatch, "someone-else@example.com")

    linked = get_or_create_user_by_google_id(
        db, UserCreate(name="Already Here", email="already-here@example.com", google_id="google-xyz")
    )
    assert linked.id == existing.id
    assert linked.google_id == "google-xyz"
