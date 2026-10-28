"""User accounts: sign-up, sign-in lookups, profile and preference edits, and deletion.

Lookups by email or Google id go through the definer functions in `identity.py`
and then `act_as` the account they found, so its row can be read under row
security. Deletion is requested, revocable for `DELETION_GRACE_DAYS`, and carried
out by `purge_expired_users` at startup.
"""

import logging
from datetime import date, datetime, time, timedelta
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app._database.identity import (
    act_as,
    email_taken,
    expired_user_ids,
    user_id_by_email,
    user_id_by_google_id,
)
from app._database.models import CourseModel, UserModel, utc_now
from app.Grades.utils.terms import suggest_first_year
from app.Intake.services.storage import StorageError
from app.Intake.services.kept_files import discard_files
from app.Auth.schemas.credentials import RegisterRequest
from app.Auth.services.signup_policy import may_sign_up
from app.Auth.services.password_service import (
    burn_one_verification,
    hash_password,
    verify_password,
)
from app.shared.errors import error_auth, error_user
from app.Users.schemas.academic_status import AcademicStatusUpdate
from app.Users.schemas.user import (
    DELETION_GRACE_DAYS,
    AuthProvider,
    UserCreate,
    UserPreferences,
    UserUpdate,
)


def create_user(db: Session, user_data: UserCreate):
    """Create an account from a verified Google sign-in.

    Args:
        db: Request-scoped database session; it is made to act as the new account.
        user_data: Name, email and Google id from the verified token.

    Returns:
        The new user, with `email_verified` set.

    Raises:
        ValueError: If another account already has the email.

    Note:
        Commits. The sign-up allowlist is checked by the caller,
        `get_or_create_user_by_google_id`.
    """
    if email_taken(db, user_data.email):
        raise ValueError(error_user["already_exists"])

    # The new account's id is chosen here, so the session can act as it before
    # the insert: under row-level security a row may only be written by the
    # user it belongs to.
    new_id = uuid4()
    act_as(db, new_id)
    user = UserModel(
        id=new_id,
        name=user_data.name,
        email=user_data.email,
        google_id=user_data.google_id,
        auth_provider=AuthProvider.GOOGLE.value,
        email_verified=True,  # Google only returns a profile once it has verified the address
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user(db: Session, user_id: UUID):
    """Return the user row for an id, or None (row security shows only the actor).

    Args:
        db: Open database session.
        user_id: Id to look up.

    Returns:
        The user row, or None.
    """
    return db.query(UserModel).filter(UserModel.id == user_id).first()


def get_user_by_email(db: Session, email: str):
    """Return the account registered to an email, and make the session act as it.

    Args:
        db: Request-scoped database session.
        email: Address to look up, case-insensitively.

    Returns:
        The user, or None when no account has the address.
    """
    user_id = user_id_by_email(db, email)
    if user_id is None:
        return None
    act_as(db, user_id)
    return get_user(db, user_id)


def create_local_user(db: Session, data: RegisterRequest):
    """Register an email-and-password account.

    Args:
        db: Request-scoped database session.
        data: Name, normalised email and password.

    Returns:
        The new user; `email_verified` stays False, since nothing proves the mailbox.

    Raises:
        ValueError: If the address is not on the sign-up allowlist; if an account
            already holds it (with a message pointing to Google when that account
            uses Google); or if a concurrent registration of the same address won.

    Note:
        Commits. Never attaches a password to an existing account.
    """
    if not may_sign_up(data.email):
        raise ValueError(error_auth["not_invited"])

    existing = get_user_by_email(db, data.email)
    if existing is not None:
        # Never attach a password to someone else's account from an
        # unauthenticated endpoint — that would be account takeover by anyone
        # who knows the address. Adding a password to a Google account is done
        # while signed in, via set_password.
        if existing.has_google:
            raise ValueError(error_auth["use_google"])
        raise ValueError(error_user["already_exists"])

    new_id = uuid4()
    act_as(db, new_id)
    user = UserModel(
        id=new_id,
        name=data.name,
        email=data.email,
        google_id=None,
        auth_provider=AuthProvider.LOCAL.value,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        # The check above races: two registrations of the same address can both
        # read "no such user" and both insert. The unique index on users.email
        # is what actually decides it, and the loser has to be told the same
        # thing the check would have told it -- not handed a 500 for having
        # arrived a millisecond later.
        db.rollback()
        raise ValueError(error_user["already_exists"]) from exc

    db.refresh(user)
    return user


def authenticate_local_user(db: Session, email: str, password: str):
    """Return the user for a correct email and password, otherwise None.

    Every failure (no account, no password on the account, wrong password) returns
    None, and the no-account path spends a bcrypt verification so all take comparable
    time. The caller must answer them identically.

    Args:
        db: Request-scoped database session.
        email: The normalised address.
        password: The password as typed.

    Returns:
        The user, or None.
    """
    user = get_user_by_email(db, email)
    if user is None or not user.password_hash:
        burn_one_verification()
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def get_user_by_google_id(db: Session, google_id: str):
    """Return the account linked to a Google subject, and make the session act as it.

    Args:
        db: Open session; it acts as the account found.
        google_id: The Google account's subject (`sub`).

    Returns:
        The user row, or None when no account is linked to it.
    """
    user_id = user_id_by_google_id(db, google_id)
    if user_id is None:
        return None
    act_as(db, user_id)
    return get_user(db, user_id)


def get_or_create_user_by_google_id(db: Session, user_data: UserCreate):
    """Sign in with Google: find by Google id, then by email, or else create.

    An existing account found by email gets the Google identity linked. Only creation
    is gated by the sign-up allowlist; existing accounts always sign in.

    Args:
        db: Request-scoped database session.
        user_data: Details from a token whose email Google verified.

    Returns:
        The signed-in user.

    Raises:
        ValueError: If a new account would be needed and the address is not on the
            allowlist, or another account took the address meanwhile.
    """
    existing = get_user_by_google_id(db, user_data.google_id)
    if existing is not None:
        return existing

    email_owner = get_user_by_email(db, user_data.email)
    if email_owner is not None:
        return link_google_to_account(db, email_owner, user_data.google_id)

    # Only this branch creates. The two above found an account that already
    # exists, and those keep working regardless of the list -- the gate decides
    # who may *join*, not who may sign in.
    if not may_sign_up(user_data.email):
        raise ValueError(error_auth["not_invited"])

    return create_user(db, user_data)


def link_google_to_account(db: Session, user: UserModel, google_id: str):
    """Attach a verified Google identity to an existing account.

    An unverified account's password is dropped, since it proves nothing about who owns
    the mailbox (pre-hijacking); the email is then marked verified.

    Args:
        db: Request-scoped database session.
        user: The account to link.
        google_id: Google's subject id.

    Returns:
        The updated user.

    Note:
        Commits.
    """
    user.google_id = google_id
    if not user.email_verified:
        user.password_hash = None
    user.email_verified = True
    db.commit()
    db.refresh(user)
    return user


def set_password(db: Session, user: UserModel, new_password: str, current_password: str | None = None):
    """Add a first password, or change the current one, on the signed-in account.

    Args:
        db: Request-scoped database session.
        user: The signed-in user.
        new_password: The new password, already length-checked.
        current_password: Required when the account already has a password.

    Returns:
        The updated user.

    Raises:
        ValueError: If the current password is missing or wrong.

    Note:
        Commits and bumps `session_epoch`, revoking every outstanding session; the
        route issues a fresh token.
    """
    if user.has_password:
        if not current_password:
            raise ValueError(error_auth["current_password_required"])
        if not verify_password(current_password, user.password_hash):
            raise ValueError(error_auth["wrong_current_password"])

    user.password_hash = hash_password(new_password)
    # Every outstanding session dies with the old password. Someone who changes
    # their password *because* they think they were compromised would otherwise
    # stay compromised for the rest of the token's seven-day life.
    user.session_epoch = (user.session_epoch or 0) + 1
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user_id: UUID, data: UserUpdate):
    """Apply a partial edit to the user's name, email and preferences.

    Preferences are merged over the stored ones, as JSON, only for the keys sent. A
    changed email is no longer verified.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        data: The fields to change.

    Returns:
        The updated user, or None when the user does not exist.

    Raises:
        ValueError: If another account already has the new email.

    Note:
        Commits.
    """
    user = get_user(db, user_id)
    if user is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    new_email = update_data.get("email")
    if new_email is not None and email_taken(db, new_email, except_user_id=user_id):
        raise ValueError(error_user["already_exists"])

    # A changed address is an unproven address. Without this the verified flag
    # survives the change, which defeats the pre-hijacking guard in
    # link_google_to_account: an attacker could point their verified account at
    # someone else's email and keep their password through the link.
    if new_email is not None and new_email != user.email:
        user.email_verified = False

    # Preferences are a JSON column, so a partial patch must merge rather than
    # replace -- otherwise setting one preference silently clears the rest.
    #
    # `exclude_unset=True` is what makes that true, and for a year it was
    # missing. The incoming model was `UserPreferences`, where every field has a
    # default, so a patch naming six keys dumped all fourteen and this merge
    # wrote defaults over the eight it had not been asked about. Settings reset
    # `timezone` on every save. The fix is in the schema -- `UserUpdate` now
    # takes `UserPreferencesPatch`, whose fields are genuinely optional -- and
    # this flag is the half that makes the schema matter.
    #
    # Removing it now fails seven tests, and fails them loudly rather than
    # quietly: with the patch type in place an unset field dumps as `None`, so
    # the merge writes nulls into the column and `get_preferences` refuses them
    # on the next read. The old shape wrote plausible defaults instead, which is
    # why it survived a year. Mutation-verified either way -- the flag is
    # load-bearing, not decoration.
    #
    # Dumped in JSON mode, not Python mode. model_dump() keeps real Python
    # objects, so study_day_start arrived as a datetime.time and the column
    # refused it: "Object of type time is not JSON serializable", which made
    # saving anything at all in Settings a 500. Anything stored as JSON has to
    # be serialised on the way in, whatever type is added to the model later.
    update_data.pop("preferences", None)
    if data.preferences is not None:
        merged = {
            **(user.preferences or {}),
            **data.preferences.model_dump(mode="json", exclude_unset=True),
        }
        user.preferences = merged

    for key, value in update_data.items():
        setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user


def get_preferences(user: UserModel) -> UserPreferences:
    """Return the user's stored preferences with defaults filled in.

    Args:
        user: The user row.

    Returns:
        The preferences, every key present.

    Raises:
        pydantic.ValidationError: If a stored value no longer validates.
    """
    return UserPreferences(**(user.preferences or {}))


def update_academic_status(db: Session, user_id: UUID, data: AcademicStatusUpdate):
    """Set the student's current school year, term, term label and first-year anchor.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.
        data: The fields to change; omitted ones stay, explicit nulls clear.

    Returns:
        The updated user with `suggested_first_year` attached, or None when the user
        does not exist.

    Note:
        Commits.
    """
    user = get_user(db, user_id)
    if user is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    if "school_year" in update_data:
        user.current_school_year = update_data["school_year"]
    if "semester" in update_data:
        semester = update_data["semester"]
        user.current_semester = semester.value if hasattr(semester, "value") else semester
    if "term_label" in update_data:
        user.term_label = update_data["term_label"]
    if "first_year_calendar_year" in update_data:
        user.first_year_calendar_year = update_data["first_year_calendar_year"]

    db.commit()
    db.refresh(user)
    return attach_year_suggestion(db, user)


def attach_year_suggestion(db: Session, user: UserModel) -> UserModel:
    """Attach the first-year anchor suggested by the user's dated courses.

    Args:
        db: Open database session.
        user: The user row; `suggested_first_year` is set on it, not stored.

    Returns:
        The same user.
    """
    user.suggested_first_year = suggest_first_year(
        db.query(CourseModel).filter(CourseModel.user_id == user.id).all()
    )
    return user


def deletes_on(user: UserModel) -> date | None:
    """Return the day a deleted account stops being recoverable, else None.

    Args:
        user: The user row.

    Returns:
        `deleted_at` plus the grace period, as a date; None when not deleted.
    """
    if user.deleted_at is None:
        return None
    return (user.deleted_at + timedelta(days=DELETION_GRACE_DAYS)).date()


def delete_user(db: Session, user_id: UUID):
    """Request deletion of an account; it stays recoverable for the grace period.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.

    Returns:
        The user with `deleted_at` set, or None when the user does not exist. A repeat
        request changes nothing.

    Note:
        Commits and bumps `session_epoch`, signing every session out, so a stolen
        token that asked for this cannot keep using the account.
    """
    user = get_user(db, user_id)
    if user is None:
        return None

    if user.deleted_at is None:
        user.deleted_at = utc_now()
        user.session_epoch = (user.session_epoch or 0) + 1
        db.commit()
        db.refresh(user)

    return user


def restore_user(db: Session, user_id: UUID):
    """Cancel a pending account deletion.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.

    Returns:
        The restored user, or None when there was no pending deletion.

    Note:
        Commits.
    """
    user = get_user(db, user_id)
    if user is None or user.deleted_at is None:
        return None

    user.deleted_at = None
    db.commit()
    db.refresh(user)
    return user


def purge_expired_users(db: Session, on_day: date | None = None) -> int:
    """Delete for good every account whose deletion grace period has passed.

    Each account is purged as itself, through the ORM so every cascade runs: its kept
    syllabus files first, then its rows. An account whose files cannot be deleted, or
    whose delete fails, is rolled back, logged and left for the next purge.

    Args:
        db: A session of its own; it is made to act as each account in turn.
        on_day: Day to measure the grace period from, for tests; None means now.

    Returns:
        How many accounts were purged.

    Note:
        Commits once per account. Idempotent; runs at every startup.
    """
    cutoff = utc_now() - timedelta(days=DELETION_GRACE_DAYS)
    if on_day is not None:
        cutoff = datetime.combine(on_day, time.min) - timedelta(days=DELETION_GRACE_DAYS)

    # One account at a time, each as itself: under row-level security the
    # cascade can only see -- and so only delete -- the rows of the user the
    # session is acting for, which is exactly the set that should go.
    expired = expired_user_ids(db, cutoff)
    purged = 0
    for user_id in expired:
        act_as(db, user_id)
        user = get_user(db, user_id)
        if user is None:
            continue
        # Kept syllabi first: they live outside the database, where no cascade
        # reaches, and the rows are the only record of them. If storage cannot
        # confirm the deletes, this account waits for the next purge rather
        # than leave files nothing points to.
        try:
            discard_files(db, user_id)
        except StorageError as exc:
            logging.getLogger("audit").warning("purge of %s deferred: %s", user_id, exc)
            continue
        # This runs at startup, so a refusal here must not take the API down
        # with it: the account is rolled back whole, logged, and tried again on
        # the next start. Every key is meant to be covered (ORDERING, in
        # models.py); this is for the one that is not.
        try:
            db.delete(user)
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            logging.getLogger("audit").error("purge of %s failed, kept for the next one: %s", user_id, exc)
            continue
        purged += 1
    return purged
