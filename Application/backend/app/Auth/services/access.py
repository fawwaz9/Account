"""The guard for routes with a `user_id` in the path: it must be the signed-in user."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status

from app.Auth.dependencies import CurrentUser


def verify_user_access(user_id: UUID, current_user: CurrentUser) -> UUID:
    """Return the path's `user_id` if it is the signed-in user's own.

    Args:
        user_id: The `user_id` path parameter.
        current_user: The signed-in user.

    Returns:
        The same `user_id`.

    Raises:
        HTTPException: 403 when it is another user's id.
    """
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this resource",
        )
    return user_id


VerifiedUserId = Annotated[UUID, Depends(verify_user_access)]
"""Route parameter type for a path `user_id` checked to be the caller's own."""
