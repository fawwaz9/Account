from typing import Annotated
from fastapi import Depends
from sqlalchemy.orm import Session
from app._database.db import get_db

DBSession = Annotated[Session, Depends(get_db)]