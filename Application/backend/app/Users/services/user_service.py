from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app._database.models import UserModel
from app.shared.errors import error_user
from app.Users.schemas.user import AuthProvider, UserCreate, UserUpdate


def create_user(db: Session, user_data: UserCreate):
    existing = db.query(UserModel).filter(UserModel.email.ilike(user_data.email)).first()
    if existing:
        raise ValueError(error_user["already_exists"])

    user = UserModel(
        id=uuid4(),
        name=user_data.name,
        email=user_data.email,
        google_id=user_data.google_id,
        auth_provider=AuthProvider.GOOGLE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_all_users(db: Session):
    return db.query(UserModel).all()


def get_user(db: Session, user_id: UUID):
    return db.query(UserModel).filter(UserModel.id == user_id).first()


def get_user_by_google_id(db: Session, google_id: str):
    return db.query(UserModel).filter(UserModel.google_id == google_id).first()


def get_or_create_user_by_google_id(db: Session, user_data: UserCreate):
    """Login-or-signup entry point for the Google OAuth flow."""
    existing = get_user_by_google_id(db, user_data.google_id)
    if existing is not None:
        return existing

    # google_id is new, but the email might already belong to another
    # account (e.g. created before Google auth existed). Surface that
    # clearly rather than silently creating a duplicate.
    email_owner = db.query(UserModel).filter(UserModel.email.ilike(user_data.email)).first()
    if email_owner is not None:
        raise ValueError(error_user["already_exists"])

    return create_user(db, user_data)


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

    for key, value in update_data.items():
        setattr(user, key, value)

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