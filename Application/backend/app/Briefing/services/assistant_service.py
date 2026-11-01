"""BYOAI: one revocable, read-only token that lets your own assistant read your digest.

Phase 4 item 7, under D4: off until you make a token; the token is shown once and
only its SHA-256 is kept; making a new one replaces the old; revoking deletes the
row, so the token stops working at once. A token reads the digest and nothing
else: it is not a session token, it opens no other route, and a session token
opens none of the assistant routes.
"""

import hashlib
import secrets
import uuid

from sqlalchemy.orm import Session

from app._database.identity import assistant_token_user
from app._database.models import AssistantTokenModel, UserModel

#: Every assistant token starts with this, so a session token (a JWT) can never be
#: mistaken for one, and one pasted somewhere it shouldn't be is recognisable.
TOKEN_PREFIX = "acct_"
#: Characters shown in Settings to recognise a token by: the prefix and a few more.
SHOWN = 12
#: Random bytes behind a token: 256 bits.
TOKEN_BYTES = 32
#: Longest token accepted, so an absurd header is refused before it is hashed.
MAX_TOKEN_LENGTH = 100


def token_hash(token: str) -> str:
    """Return the SHA-256 hex digest a token is stored and looked up by."""
    return hashlib.sha256(token.encode()).hexdigest()


def status(db: Session, user_id: uuid.UUID) -> AssistantTokenModel | None:
    """Return the user's token row, if they have one."""
    return db.query(AssistantTokenModel).filter(AssistantTokenModel.user_id == user_id).first()


def make(db: Session, user_id: uuid.UUID) -> tuple[str, AssistantTokenModel] | None:
    """Make a new token for the user, replacing any old one.

    Args:
        db: Request-scoped database session.
        user_id: The verified caller's id.

    Returns:
        (the token, its row); the token is not stored and can't be shown again. None
        when the user does not exist.
    """
    if db.query(UserModel.id).filter(UserModel.id == user_id).first() is None:
        return None
    db.query(AssistantTokenModel).filter(AssistantTokenModel.user_id == user_id).delete()
    token = TOKEN_PREFIX + secrets.token_urlsafe(TOKEN_BYTES)
    row = AssistantTokenModel(id=uuid.uuid4(), user_id=user_id, token_hash=token_hash(token), prefix=token[:SHOWN])
    db.add(row)
    db.commit()
    db.refresh(row)
    return token, row


def revoke(db: Session, user_id: uuid.UUID) -> bool:
    """Delete the user's token, so it stops working at once.

    Returns:
        True when there was one.
    """
    gone = db.query(AssistantTokenModel).filter(AssistantTokenModel.user_id == user_id).delete()
    db.commit()
    return gone > 0


def resolve(db: Session, presented: str | None) -> uuid.UUID | None:
    """Return the owner of a presented token, or None for anything that isn't a live one.

    Args:
        db: Open database session; needs no acting user.
        presented: The bearer value as sent.

    Returns:
        The owner's id; None for a missing, malformed, session-shaped, unknown or
        revoked token.
    """
    if not presented or not presented.startswith(TOKEN_PREFIX) or len(presented) > MAX_TOKEN_LENGTH:
        return None
    return assistant_token_user(db, token_hash(presented))
