from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status

from app.Auth.dependencies import CurrentUser


def verify_user_access(user_id: UUID, current_user: CurrentUser) -> UUID:
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this resource",
        )
    return user_id


VerifiedUserId = Annotated[UUID, Depends(verify_user_access)]