"""Check that the Supabase connection string is usable, and is the right one.

    python scripts/check_db_connection.py                  # reads ../.env
    python scripts/check_db_connection.py path/to/.env

Reads `SUPABASE_DATABASE_URL` from the env file and checks, in order: that it is
Postgres, that it is the transaction pooler (not the direct host or session mode),
that the username carries the project reference, and that six queries succeed past
psycopg's prepare threshold. Each failure names its fix. The password is described
(length, character classes), never printed.
"""

from __future__ import annotations

import string
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app._database.db import (  # noqa: E402
    connect_args_for,
    engine_kwargs_for,
    normalize_database_url,
)

VARIABLE = "SUPABASE_DATABASE_URL"
"""The env-file variable holding the Supabase connection string."""
#: Characters that mean something structural inside a URL, so a password
#: containing one has to be percent-encoded or the string parses into the wrong
#: pieces -- and sends the wrong password, or connects to the wrong host.
NEEDS_ENCODING = set("@:/?#[]%&= ")


def read(env_path: Path, key: str) -> str | None:
    """Return a variable's value from an env file, unquoted, or None if absent.

    Args:
        env_path: The env file; a missing file reads as nothing.
        key: The variable's name.

    Returns:
        The value after the first `=`, stripped of quotes; None when not set.
    """
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        if line.strip().startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def fail(problem: str, *fixes: str) -> int:
    """Print a failed check with its suggested fixes, and return exit status 1.

    Args:
        problem: What went wrong.
        *fixes: Suggestions, one per line.

    Returns:
        1, the script's exit status.
    """
    print(f"\n  FAIL  {problem}")
    for fix in fixes:
        print(f"        -> {fix}")
    return 1


def describe_password(password: str) -> int:
    """Explain why authentication failed without showing the password, and return 1.

    Checks in order: no password, the dashboard's `[YOUR-PASSWORD]` brackets left in,
    the placeholder itself, unencoded URL-reserved characters; otherwise the password
    is well formed and simply wrong.

    Args:
        password: The password parsed from the URL.

    Returns:
        1, always: this is only reached after a failed authentication.
    """
    print(f"  password: {len(password)} characters")

    if not password:
        return fail("there is no password in the string at all.",
                    "copy the whole line from the dashboard again")

    if password.startswith("[") and password.endswith("]"):
        return fail(
            "the password still has square brackets around it.",
            "`[YOUR-PASSWORD]` means replace the whole token, brackets included.",
            f"remove the first and last character, leaving {len(password) - 2}.",
        )

    if "YOUR-PASSWORD" in password or "your-password" in password.lower():
        return fail("the password is still the placeholder.",
                    "replace it with the database password set when the project was created")

    reserved = sorted({c for c in password if c in NEEDS_ENCODING})
    if reserved:
        encoded = ", ".join(f"{c!r} -> %{ord(c):02X}" for c in reserved)
        return fail(
            f"the password contains {reserved}, which are reserved inside a URL.",
            f"percent-encode them: {encoded}",
            "unencoded, the URL parses into the wrong pieces and sends the wrong password",
        )

    classes = []
    if any(c.isalpha() for c in password):
        classes.append("letters")
    if any(c.isdigit() for c in password):
        classes.append("digits")
    other = sorted({c for c in password if c not in string.ascii_letters + string.digits})
    if other:
        classes.append(f"other {other}")
    print(f"  it is written correctly -- {', '.join(classes)}, all URL-safe.")
    return fail("so this is simply not the password Supabase has.",
                "Settings -> Database -> Reset database password, then paste the new string")


def main() -> int:
    """Run every check against the connection string in the env file.

    The env file is the first argument, or `Application/.env` by default.

    Returns:
        0 when the string is right and the database answered; 1 at the first failed
        check.
    """
    env_path = Path(sys.argv[1]) if len(sys.argv) > 1 else BACKEND_DIR.parent / ".env"

    raw = read(env_path, VARIABLE)
    if raw is None:
        if read(env_path, "DATABASE_URL"):
            return fail(f"found DATABASE_URL, not {VARIABLE}.",
                        "rename it -- DATABASE_URL is what the app reads, so setting it here "
                        "points local development at the cloud database")
        return fail(f"no {VARIABLE} in {env_path}.", "see step 17 of the runbook")

    print(f"  read {VARIABLE} from {env_path}  ({len(raw)} characters)")

    url = make_url(normalize_database_url(raw))
    if url.get_backend_name() != "postgresql":
        return fail(f"this parses as {url.get_backend_name()}, not Postgres.", "copy it again")

    host = url.host or ""
    if host.startswith("db.") and host.endswith(".supabase.co"):
        return fail("this is the DIRECT connection, not the pooler.",
                    "it is IPv6 only, so Cloud Run cannot reach it at all",
                    "take the Transaction pooler string instead")
    if "pooler.supabase.com" not in host:
        print(f"  WARN  host does not look like a Supabase pooler: {host}")
    else:
        print(f"  ok    pooled host. Region: {host.split('.')[0]}  <- Cloud Run goes here too")

    if url.port == 5432 and "pooler" in host:
        return fail("port 5432 on the pooler host is SESSION mode.",
                    "take the Transaction pooler string (port 6543)",
                    "session mode holds a backend connection per client, which is the "
                    "opposite of what something that scales to zero wants")
    if url.port == 6543:
        print("  ok    port 6543 -- transaction pooler, the right one for Cloud Run")
    else:
        print(f"  WARN  unexpected port {url.port}")

    if "pooler" in host and url.username and "." not in url.username:
        return fail(f"the username is {url.username!r}, with no project reference.",
                    "the pooler needs postgres.<project-ref>, which only the pooler string has")

    print(f"  ok    driver resolved to {url.get_driver_name()}")
    args = connect_args_for(raw)
    prepared = "disabled" if args.get("prepare_threshold", 0) is None else "ENABLED -- wrong for the pooler"
    print(f"  ok    prepared statements: {prepared}")

    print("\n  connecting...")
    engine = create_engine(url.render_as_string(hide_password=False),
                           connect_args=args, **engine_kwargs_for(raw))
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SHOW server_version")).scalar()
            tables = conn.execute(text(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
            )).scalar()
            # Six, deliberately. psycopg starts preparing at the fifth execution
            # of a query, so anything less would not exercise the one setting
            # that transaction-mode pooling actually requires.
            for _ in range(6):
                conn.execute(text("SELECT 1"))
    except Exception as exc:
        # Matched case-insensitively against the wording psycopg and Supavisor
        # actually use, which is not the wording their documentation uses:
        # Supavisor says "(ENOTFOUND) tenant/user <name> not found", not
        # "Tenant or user not found". A matcher written from the docs silently
        # falls through to the generic branch and the specific advice is lost.
        first = str(exc).splitlines()[0].lower()
        if "password authentication failed" in first:
            return describe_password(url.password or "")
        if "tenant" in first and "not found" in first:
            return fail("the pooler does not recognise this user.",
                        "on the pooler the username must be postgres.<project-ref> -- "
                        "check it was not truncated when it was pasted")
        if "prepared statement" in first:
            return fail("prepared statements are reaching the pooler.",
                        "connect_args_for is not applying prepare_threshold=None -- see D2.6")
        return fail(str(exc).splitlines()[0][:200], "unexpected -- worth reading in full")
    finally:
        engine.dispose()

    print(f"  ok    connected. Postgres {version}")
    print("  ok    six queries through the pooler, past psycopg's prepare threshold")
    print(f"  ok    public schema holds {tables} tables"
          f"{'  -- empty' if tables == 0 else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
