"""Request and response bodies for BYOAI tokens (Phase 4 item 7, D4).

One token per user, off until made, shown once, stored only as a hash, revoked by
deleting it. It reads the digest and nothing else.
"""

from datetime import datetime

from pydantic import BaseModel


class AssistantTokenStatus(BaseModel):
    """Whether the user has a token, and what to recognise it by. Never the token.

    Attributes:
        enabled: True while a token exists.
        prefix: Its first characters, as shown when it was made.
        created_at: When it was made.
        last_used_at: When an assistant last read the digest with it.
    """
    enabled: bool
    prefix: str | None = None
    created_at: datetime | None = None
    last_used_at: datetime | None = None


class AssistantTokenMade(BaseModel):
    """A new token, the only time it is ever shown.

    Attributes:
        token: The token itself; copy it now, it can't be shown again.
        prefix: Its first characters, to recognise it by later.
        created_at: When it was made.
    """
    token: str
    prefix: str
    created_at: datetime
