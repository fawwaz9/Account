from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app._database.models import UserModel
from app.Auth.schemas.credentials import RegisterRequest
from app.Auth.services.password_service import (
    burn_one_verification,
    hash_password,
    verify_password,
)
from app.shared.errors import error_auth, error_user
from app.Users.schemas.academic_status import AcademicStatusUpdate
from app.Users.schemas.user import AuthProvider, UserCreate, UserPreferences, UserUpdate


def create_user(db: Session, user_data: UserCreate):
    existing = db.query(UserModel).filter(UserModel.email.ilike(user_data.email)).first()
    if existing:
        raise ValueError(error_user["already_exists"])

    user = UserModel(
        id=uuid4(),
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


def get_all_users(db: Session):
    return db.query(UserModel).all()


def get_user(db: Session, user_id: UUID):
    return db.query(UserModel).filter(UserModel.id == user_id).first()


def get_user_by_email(db: Session, email: str):
    return db.query(UserModel).filter(UserModel.email.ilike(email)).first()


def create_local_user(db: Session, data: RegisterRequest):
    """Register an email + password account."""
    existing = get_user_by_email(db, data.email)
    if existing is not None:
        # Never attach a password to someone else's account from an
        # unauthenticated endpoint — that would be account takeover by anyone
        # who knows the address. Adding a password to a Google account is done
        # while signed in, via set_password.
        if existing.has_google:
            raise ValueError(error_auth["use_google"])
        raise ValueError(error_user["already_exists"])

    user = UserModel(
        id=uuid4(),
        name=data.name,
        email=data.email,
        google_id=None,
        auth_provider=AuthProvider.LOCAL.value,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    db.commit()
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
    return db.query(UserModel).filter(UserModel.google_id == google_id).first()


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
    if new_email is not None:
        existing = (
            db.query(UserModel)
            .filter(UserModel.id != user_id, UserModel.email.ilike(new_email))
            .first()
        )
        if existing:
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
    # Dumped in JSON mode, not Python mode. model_dump() keeps real Python
    # objects, so study_day_start arrived as a datetime.time and the column
    # refused it: "Object of type time is not JSON serializable", which made
    # saving anything at all in Settings a 500. Anything stored as JSON has to
    # be serialised on the way in, whatever type is added to the model later.
    update_data.pop("preferences", None)
    if data.preferences is not None:
        merged = {
            **(user.preferences or {}),
            **data.preferences.model_dump(mode="json"),
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

    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user_id: UUID):
    user = get_user(db, user_id)
    if user is None:
        return None

    db.delete(user)
    db.commit()
    return user