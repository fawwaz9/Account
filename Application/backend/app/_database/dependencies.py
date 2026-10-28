"""FastAPI dependency alias for the request-scoped database session."""

from typing import Annotated
from fastapi import Depends
from sqlalchemy.orm import Session
from app._database.db import get_db

DBSession = Annotated[Session, Depends(get_db)]
"""Route parameter type for a `Session` from `get_db`, closed when the request ends.

It carries no acting user; routes that read user data also depend on
`get_current_user`, which calls `act_as` on this same session.
"""
