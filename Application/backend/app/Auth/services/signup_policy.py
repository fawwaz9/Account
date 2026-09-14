"""Who is allowed to create an account.

`/register` was open to anyone who could reach it, and so, less obviously, was
`/auth/google` -- that route creates accounts too, so an allowlist guarding only
the password path leaves the other door wide open.

**This gates creation, not sign-in.** An account that already exists keeps
working whether or not its address is on the list. Otherwise adding the list
would sign out everyone already using the app, and removing an address would
destroy access to real data rather than merely declining a new signup. Taking
someone's access away is a deletion, and deletion has its own deliberate,
reversible path.

**Unset means open, and that is a real trade.** Defaulting to closed would be
the safer-sounding choice, but it would break every local clone: nobody could
create the first account, including the person who just cloned it. So unset
behaves as it always has, and `warn_if_open()` says so loudly at startup. The
deployment sets the variable; the runbook lists it among the settings that are
not defaults for a reason.
"""
import logging
import os

logger = logging.getLogger("app.signup")


def allowed_emails() -> set[str]:
    """The addresses permitted to create an account, lowercased.

    Empty means no restriction. Comma-separated, and each entry is stripped --
    "a@x.com, b@x.com" is how a person writes a list, and the space would
    otherwise make the second entry " b@x.com", which no address ever equals.
    """
    raw = os.getenv("ALLOWED_SIGNUP_EMAILS", "")
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def may_sign_up(email: str) -> bool:
    allowed = allowed_emails()
    if not allowed:
        return True
    return (email or "").strip().lower() in allowed


def warn_if_open() -> None:
    """Say, at startup, that anybody who finds this can create an account."""
    if not allowed_emails():
        logger.warning(
            "ALLOWED_SIGNUP_EMAILS is not set: anyone who can reach this server "
            "can create an account. Set it to the invited addresses."
        )
