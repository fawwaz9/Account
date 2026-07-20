from uuid import UUID, uuid4

from app.shared.errors import error_user
from app.temp_data.store import users
from app.Users.schemas.user import UserCreate, UserDetail, UserUpdate


def create_user(user_data: UserCreate):
    for user in users:
        if user.email.lower() == user_data.email.lower():
            raise ValueError(error_user["already_exists"])

    user = UserDetail(
        id=uuid4(),
        courses=[],
        **user_data.model_dump()
    )
    users.append(user)
    return user


def get_all_users():
    return users


def get_user(user_id: UUID):
    for user in users:
        if user.id == user_id:
            return user

    return None


def update_user(user_id: UUID, data: UserUpdate):
    user = get_user(user_id)
    if user is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    new_email = update_data.get("email")
    if new_email is not None:
        for existing_user in users:
            if existing_user.id != user_id and existing_user.email.lower() == new_email.lower():
                raise ValueError(error_user["already_exists"])

    for key, value in update_data.items():
        setattr(user, key, value)

    return user


def delete_user(user_id: UUID):
    user = get_user(user_id)
    if user is None:
        return None

    users.remove(user)
    return user
