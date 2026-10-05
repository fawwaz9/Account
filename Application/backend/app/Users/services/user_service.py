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
    return db.query(UserModel).filter(UserModel.id == user_id).first()


def get_user_by_email(db: Session, email: str):
    """The account for ``email``, and from here on the session acts for it.

    Only sign-in and registration ask this, and both are about that account:
    signing in makes it the caller, and registration needs to know what kind of
    account already holds the address. Acting as it is what lets the row be
    read under row-level security.
    """
    user_id = user_id_by_email(db, email)
    if user_id is None:
        return None
    act_as(db, user_id)
    return get_user(db, user_id)


def create_local_user(db: Session, data: RegisterRequest):
    """Register an email + password account."""
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
    """Return the user for valid credentials, otherwise None.

    The caller must not distinguish the failure cases in its response. An
    unregistered address, a Google-only account, and a wrong password all
    return None, and the no-account path still spends a bcrypt verification
    so the three take comparable time.
    """
    user = get_user_by_email(db, email)
    if user is None or not user.password_hash:
        burn_one_verification()
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def get_user_by_google_id(db: Session, google_id: str):
    """The account linked to ``google_id``; the session then acts for it."""
    user_id = user_id_by_google_id(db, google_id)
    if user_id is None:
        return None
    act_as(db, user_id)
    return get_user(db, user_id)


def get_or_create_user_by_google_id(db: Session, user_data: UserCreate):
    """Login-or-signup entry point for the Google OAuth flow.

    Google is reached only after ``verify_google_token`` has confirmed
    ``email_verified``, so arriving here proves the person controls the
    address. That is what makes linking safe.
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
    """Attach a verified Google identity to an existing local account.

    Local signup cannot verify an address — there is no verification email —
    so a password on an unverified account proves nothing about who owns the
    mailbox. Someone could register victim@example.com before the real owner
    ever signs in with Google, then keep password access to their account
    afterwards (an account pre-hijacking attack).

    Google's assertion settles ownership, so the unproven password is dropped
    at link time. The real owner can set a new one from account settings once
    signed in.
    """
    user.google_id = google_id
    if not user.email_verified:
        user.password_hash = None
    user.email_verified = True
    db.commit()
    db.refresh(user)
    return user


def set_password(db: Session, user: UserModel, new_password: str, current_password: str | None = None):
    """Add or change the password on the signed-in user's account.

    Changing an existing password requires the current one, so a stolen
    session cannot silently lock the owner out. An account with no password
    yet (Google signup) can set its first one without that step.
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
    """Stored preferences, filled in with defaults for anything unset."""
    return UserPreferences(**(user.preferences or {}))


def update_academic_status(db: Session, user_id: UUID, data: AcademicStatusUpdate):
    """Set which term the student is currently in.

    Everything past/current/future on the grades page is decided by comparing a
    course against these three fields.
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
    """Put the anchor Settings should offer onto the payload.

    Read-only and derived, so it is attached rather than stored -- the same
    shape `attach_course_code` and `attach_balances` use. A student who has
    entered no dates anywhere gets None and types the year themselves.
    """
    user.suggested_first_year = suggest_first_year(
        db.query(CourseModel).filter(CourseModel.user_id == user.id).all()
    )
    return user


def deletes_on(user: UserModel) -> date | None:
    """The day a deleted account stops being recoverable."""
    if user.deleted_at is None:
        return None
    return (user.deleted_at + timedelta(days=DELETION_GRACE_DAYS)).date()


def delete_user(db: Session, user_id: UUID):
    """Mark the account for deletion, rather than destroying it now.

    Every session is revoked at the same moment, so a stolen token that asked
    for this cannot carry on using the account while the grace period runs --
    the owner signs in again, sees the date, and undoes it.

    Nothing is removed here. `purge_expired_users` does that, once the window
    has actually passed.
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
    """Cancel a pending deletion. Returns None if there is nothing to cancel."""
    user = get_user(db, user_id)
    if user is None or user.deleted_at is None:
        return None

    user.deleted_at = None
    db.commit()
    db.refresh(user)
    return user


def purge_expired_users(db: Session, on_day: date | None = None) -> int:
    """Really delete the accounts whose grace period has run out.

    Deleted one at a time through the ORM rather than in a bulk statement, so
    the cascades on UserModel actually run -- a bulk delete bypasses them and
    would leave exactly the orphans those cascades exist to prevent.

    Idempotent, and safe to call on every startup: a user is only past the
    deadline once, and after this call they are gone.
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