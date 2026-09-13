"""The audit's medium and low service-level findings.

Each of these was a case where the server answered confidently and wrongly: a
rejected edit that had already been applied, a search that matched something
other than what was typed, a read that queued a write, an empty list standing in
for an error.
"""
import uuid
from datetime import date

import pytest

from app._database.models import TransactionModel
from app.Grades.schemas.course import CourseUpdate
from app.Grades.services.course_service import search_courses, update_course
from app.Grades.services.grade_service import calculate_letter_grade
from app.Grades.utils.terms import course_result_grade
from app.Finances.services.transaction_service import list_transactions
from conftest import make_account, make_course, make_user


# ------------------------------------------------- #27 the half-applied patch --

def test_a_rejected_weight_does_not_leave_the_rest_of_the_patch_applied(db, user):
    """The fields used to be committed before the weights were even validated.

    The rejection has to come from the *service*, not the schema, or this tests
    nothing: `CourseUpdate` sums only the weights submitted, while the service
    merges them over the ones the course already has and checks that total. So
    the case is a patch that is fine on its own and only breaks the ceiling once
    merged -- which is the one that reaches the half-applied commit.
    """
    course = make_course(
        db, user.id, "COSC 111", name="Original name",
        category_weights={"Assignment": 100.0, "Final": 100.0},
    )

    with pytest.raises(ValueError):
        update_course(db, user.id, course.id, CourseUpdate(
            name="Changed name",
            # 50 on its own passes the schema; merged it makes 250, past 200.
            category_weights={"Lab": 50.0},
        ))

    db.rollback()
    db.expire_all()
    assert db.get(type(course), course.id).name == "Original name"


def test_an_accepted_patch_still_applies_both_halves(db, user):
    course = make_course(db, user.id, "COSC 111", name="Original name")

    update_course(db, user.id, course.id, CourseUpdate(
        name="Changed name",
        category_weights={"Assignment": 40.0, "Final": 60.0},
    ))

    db.refresh(course)
    assert course.name == "Changed name"
    assert course.category_weights["Assignment"] == 40.0


def test_a_patch_with_no_weights_still_commits(db, user):
    course = make_course(db, user.id, "COSC 111", name="Original name")

    update_course(db, user.id, course.id, CourseUpdate(name="Changed name"))

    db.expire_all()
    assert db.get(type(course), course.id).name == "Changed name"


# ------------------------------------------------------- #52 search wildcards --

def test_an_underscore_is_searched_for_literally(db, user):
    """To LIKE, `_` matches any single character -- so this matched everything."""
    make_course(db, user.id, "COSC 111", name="Computer Science")
    make_course(db, user.id, "DATA_101", name="Data")

    matches = search_courses(db, user.id, "_")

    assert [course.code for course in matches] == ["DATA_101"]


def test_a_percent_is_searched_for_literally(db, user):
    make_course(db, user.id, "COSC 111", name="Computer Science")
    make_course(db, user.id, "MATH 200", name="100% proofs")

    matches = search_courses(db, user.id, "100%")

    assert [course.code for course in matches] == ["MATH 200"]


def test_an_ordinary_search_still_works(db, user):
    make_course(db, user.id, "COSC 111", name="Computer Science")
    make_course(db, user.id, "MATH 200", name="Calculus")

    assert [course.code for course in search_courses(db, user.id, "cosc")] == ["COSC 111"]


# ------------------------------------------ #51 a read that queued a write --

def test_a_fresh_average_can_be_used_without_writing_it_to_the_row(db, user):
    """The letter routes recomputed the average onto the mapped column."""
    course = make_course(db, user.id, "COSC 111")
    course.average = 0.0

    letter = calculate_letter_grade(course, 91.0)

    assert letter == "A+"
    # The override is read instead of the column, and the column is untouched.
    assert course.average == 0.0


def test_the_stored_average_is_used_when_no_override_is_given(db, user):
    course = make_course(db, user.id, "COSC 111")
    course.average = 91.0

    assert course_result_grade(course) == 91.0
    assert course_result_grade(course, 55.0) == 55.0


def test_a_submitted_final_still_beats_the_override(db, user):
    """The precedence rule does not change just because a value was passed in."""
    course = make_course(db, user.id, "COSC 111", final_grade=88.0)

    assert course_result_grade(course, 40.0) == 88.0


# ------------------------------- #43 and #44 empty lists standing in for errors --

def test_an_inverted_date_range_is_rejected(db, user):
    with pytest.raises(ValueError, match="after its end"):
        list_transactions(
            db, user.id, start=date(2026, 10, 1), end=date(2026, 9, 1),
        )


def test_a_range_of_one_day_is_fine(db, user):
    """The guard is `>`, not `>=`: a single day is a legitimate window."""
    day = date(2026, 9, 1)
    assert list_transactions(db, user.id, start=day, end=day) == []


def test_an_unknown_account_is_rejected(db, user):
    with pytest.raises(LookupError, match="does not exist"):
        list_transactions(db, user.id, account_id=uuid.uuid4())


def test_another_users_account_is_also_unknown(db, user):
    """Ownership, not just existence -- otherwise this is an id oracle."""
    other = make_user(db, "other@example.com")
    theirs = make_account(db, other.id, "Chequing")

    with pytest.raises(LookupError):
        list_transactions(db, user.id, account_id=theirs.id)


def test_a_real_account_with_no_rows_still_returns_an_empty_list(db, user):
    """An account that exists and is empty is a fact, not an error."""
    account = make_account(db, user.id, "Chequing")

    assert list_transactions(db, user.id, account_id=account.id) == []


def test_rows_come_back_for_a_valid_window(db, user):
    account = make_account(db, user.id, "Chequing")
    db.add(TransactionModel(
        id=uuid.uuid4(), user_id=user.id, account_id=account.id, kind="income",
        amount=100.0, description="Opening", occurred_on=date(2026, 9, 15),
    ))
    db.commit()

    rows = list_transactions(
        db, user.id, start=date(2026, 9, 1), end=date(2026, 9, 30),
    )

    assert len(rows) == 1


# ------------------------------------------ #46 a Google sign-in that 500'd --

def test_a_google_token_without_a_name_claim_is_accepted(monkeypatch):
    """`name` rides on the profile scope, so indexing for it 500'd without one."""
    from app.Auth.services import google_auth_service

    monkeypatch.setattr(
        google_auth_service.id_token, "verify_oauth2_token",
        lambda *_args, **_kwargs: {
            "email_verified": True, "email": "sam@example.com", "sub": "google-123",
        },
    )

    created = google_auth_service.verify_google_token("any-token")

    assert created.email == "sam@example.com"
    assert created.name == "sam"


def test_a_name_is_used_when_the_claim_is_present(monkeypatch):
    from app.Auth.services import google_auth_service

    monkeypatch.setattr(
        google_auth_service.id_token, "verify_oauth2_token",
        lambda *_args, **_kwargs: {
            "email_verified": True, "email": "sam@example.com",
            "sub": "google-123", "name": "Sam Okafor",
        },
    )

    assert google_auth_service.verify_google_token("any-token").name == "Sam Okafor"


def test_a_network_failure_is_not_reported_as_a_bad_token(monkeypatch):
    """Unreachable is not invalid: one is a 503, the other a 401."""
    from google.auth.exceptions import TransportError

    from app.Auth.services import google_auth_service

    def unreachable(*_args, **_kwargs):
        raise TransportError("connection refused")

    monkeypatch.setattr(google_auth_service.id_token, "verify_oauth2_token", unreachable)

    with pytest.raises(google_auth_service.GoogleUnavailable):
        google_auth_service.verify_google_token("any-token")


def test_an_actually_invalid_token_is_still_rejected(monkeypatch):
    from app.Auth.services import google_auth_service

    def invalid(*_args, **_kwargs):
        raise ValueError("Token expired")

    monkeypatch.setattr(google_auth_service.id_token, "verify_oauth2_token", invalid)

    with pytest.raises(ValueError, match="Invalid Google token"):
        google_auth_service.verify_google_token("any-token")


# ------------------------------------ #49 concurrent registration returned 500 --

def test_registering_an_address_that_appears_between_check_and_insert(db, monkeypatch):
    """The unique index decides the race; the loser gets the ordinary message.

    The pre-check has to be neutralised or this never reaches the insert and
    tests only the check -- which is precisely the path that does *not* race.
    Returning None from it is what the losing caller genuinely sees: it read
    before the winner committed.
    """
    from app.Auth.schemas.credentials import RegisterRequest
    from app.Users.services import user_service

    payload = RegisterRequest(name="Sam", email="sam@example.com", password="hunter2hunter2")
    user_service.create_local_user(db, payload)

    monkeypatch.setattr(user_service, "get_user_by_email", lambda *_args, **_kwargs: None)

    with pytest.raises(ValueError, match="already"):
        user_service.create_local_user(db, payload)


def test_the_losing_registration_leaves_the_session_usable(db, monkeypatch):
    """Without the rollback the session stays poisoned for the rest of the request."""
    from app.Auth.schemas.credentials import RegisterRequest
    from app.Users.services import user_service

    payload = RegisterRequest(name="Sam", email="sam@example.com", password="hunter2hunter2")
    winner = user_service.create_local_user(db, payload)

    monkeypatch.setattr(user_service, "get_user_by_email", lambda *_args, **_kwargs: None)
    with pytest.raises(ValueError):
        user_service.create_local_user(db, payload)

    assert user_service.get_user(db, winner.id) is not None
