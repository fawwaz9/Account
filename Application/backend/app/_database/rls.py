"""Row-level security: the database-side half of per-user isolation.

Phase 0, item 2 (``Ideas/overhaul/phase0.md``). Until now isolation lived
entirely in application code -- every query filtering on ``user_id`` -- and a
query that forgot its filter returned every user's rows. The policies here make
Postgres refuse to return them, whatever the query says.

**How the pieces fit**

* The API connects as a dedicated role (``APP_ROLE``): no superuser, no
  BYPASSRLS, not the owner of any table. Only that role is named in the
  policies, so they constrain it and nothing else.
* Each transaction carries the caller's id in ``app.user_id``
  (``identity.act_as``). ``account_current_user()`` reads it, and returns NULL
  when it is unset -- so an un-identified query matches **no** rows rather than
  erroring or matching all of them. That is the fail-closed property.
* Every table is one of three shapes, decided from the metadata so a new table
  cannot be forgotten: the ``users`` root (a row is yours if it *is* you), a
  table with a ``user_id`` column (yours if it carries your id), or a child
  reached through exactly one parent that has one (yours if its parent is).
  A table that is none of these makes ``policy_statements`` raise.
* The few questions that cross users are ``SECURITY DEFINER`` functions that
  answer with an id or a boolean, never with rows.

**Why the owner is never forced through the policies.** Tables are owned by the
role that created them, which is the role today's API connects as. ``ENABLE
ROW LEVEL SECURITY`` without ``FORCE`` leaves the owner unaffected, so applying
all of this to production changes nothing until the API is pointed at
``APP_ROLE`` -- and pointing it back is the rollback. ``FORCE`` would make the
current API see zero rows the moment it ran.

**Postgres only.** SQLite has no row-level security; local development and the
default test run use application-level isolation alone, as they always have.
The policies are proven by ``tests/test_rls.py`` against a real Postgres.
"""
import logging

from sqlalchemy import Table, text
from sqlalchemy.engine import Engine

from app._database.db import Base
from app._database import models  # noqa: F401 - populates Base.metadata

logger = logging.getLogger("app.rls")

#: The role the API connects as once isolation is switched on. Created by hand
#: (it has a password), see Ideas/overhaul/phase0-runbook.md. Everything here
#: only GRANTs to it, and only if it exists.
APP_ROLE = "account_app"
POLICY = "account_isolation"

#: The functions the application calls. The schema gate checks they exist,
#: because an API that calls one before it is created cannot sign anyone in.
FUNCTIONS = (
    "account_current_user",
    "account_user_id_by_email",
    "account_user_id_by_google_id",
    "account_email_taken",
    "account_expired_user_ids",
    "account_release_push_endpoint",
    "account_users_with_unpushed_reminders",
)

FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION account_current_user() RETURNS uuid
    LANGUAGE sql STABLE
    AS $$ SELECT NULLIF(current_setting('app.user_id', true), '')::uuid $$;

CREATE OR REPLACE FUNCTION account_user_id_by_email(p_email text) RETURNS uuid
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ SELECT id FROM users WHERE lower(email) = lower(p_email) LIMIT 1 $$;

CREATE OR REPLACE FUNCTION account_user_id_by_google_id(p_google_id text) RETURNS uuid
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ SELECT id FROM users WHERE google_id = p_google_id LIMIT 1 $$;

CREATE OR REPLACE FUNCTION account_email_taken(p_email text, p_except uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ SELECT EXISTS (
        SELECT 1 FROM users
        WHERE lower(email) = lower(p_email) AND (p_except IS NULL OR id <> p_except)
    ) $$;

CREATE OR REPLACE FUNCTION account_expired_user_ids(p_cutoff timestamp) RETURNS SETOF uuid
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ SELECT id FROM users WHERE deleted_at IS NOT NULL AND deleted_at <= p_cutoff $$;

-- A browser's push endpoint identifies the browser, not an account: when a
-- second person turns notifications on in the same browser, the endpoint is
-- released from whoever held it. Possession of the endpoint -- an unguessable
-- URL the browser hands only to the page that subscribed -- is the proof.
CREATE OR REPLACE FUNCTION account_release_push_endpoint(p_endpoint text) RETURNS void
    LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ DELETE FROM push_subscriptions WHERE endpoint = p_endpoint $$;

-- Who has a reminder that may be due and has not been pushed, and a device to
-- push it to. remind_at is local wall time, so the caller passes a horizon
-- generous enough for every time zone and checks each user's own clock.
CREATE OR REPLACE FUNCTION account_users_with_unpushed_reminders(p_horizon timestamp)
    RETURNS SETOF uuid
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ SELECT DISTINCT r.user_id FROM reminders r
          WHERE r.dismissed_at IS NULL AND r.pushed_at IS NULL AND r.remind_at <= p_horizon
            AND EXISTS (SELECT 1 FROM push_subscriptions s WHERE s.user_id = r.user_id) $$;

-- Definer functions run with their owner's rights, so nobody but the API
-- needs to be able to call them.
REVOKE ALL ON FUNCTION account_user_id_by_email(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_user_id_by_google_id(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_email_taken(text, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_expired_user_ids(timestamp) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_release_push_endpoint(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_users_with_unpushed_reminders(timestamp) FROM PUBLIC;
"""


def _owner_parent(table: Table) -> tuple[str, str, Table] | None:
    """For a child table: (its column, the parent's column, the parent).

    A child is a table with no user_id whose path to an owner is exactly one
    non-null foreign key into a table that has one. Exactly one, because a
    child with two possible owners has no single answer to "whose is this".
    """
    candidates = []
    for column in table.columns:
        if column.nullable:
            continue
        for fk in column.foreign_keys:
            parent = fk.column.table
            if "user_id" in parent.columns:
                candidates.append((column.name, fk.column.name, parent))
    return candidates[0] if len(candidates) == 1 else None


def owner_predicate(table: Table) -> str:
    """The SQL condition under which a row of ``table`` belongs to the caller."""
    if table.name == "users":
        return "id = account_current_user()"
    if "user_id" in table.columns:
        return "user_id = account_current_user()"
    parent = _owner_parent(table)
    if parent is None:
        raise ValueError(
            f"Table {table.name!r} has no user_id and no single owning parent, so no "
            "row policy can say whose its rows are. Give it a user_id, or a single "
            "non-null foreign key to a table that has one."
        )
    column, parent_column, parent_table = parent
    return (
        f"EXISTS (SELECT 1 FROM {parent_table.name} p "
        f"WHERE p.{parent_column} = {table.name}.{column} AND p.user_id = account_current_user())"
    )


def policy_statements() -> list[str]:
    """Every statement that puts the policies in place. Idempotent."""
    statements = []
    for table in Base.metadata.sorted_tables:
        predicate = owner_predicate(table)
        statements += [
            f"ALTER TABLE {table.name} ENABLE ROW LEVEL SECURITY",
            f"DROP POLICY IF EXISTS {POLICY} ON {table.name}",
            # TO the app role alone. Other roles get no policy, which under
            # RLS means no rows -- that also closes Supabase's anon and
            # authenticated roles off from these tables.
            f"CREATE POLICY {POLICY} ON {table.name} FOR ALL TO {APP_ROLE} "
            f"USING ({predicate}) WITH CHECK ({predicate})",
        ]
    return statements


def grant_statements() -> list[str]:
    """What the app role may do: data, never schema."""
    return [
        "GRANT USAGE ON SCHEMA public TO " + APP_ROLE,
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO " + APP_ROLE,
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_current_user() TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_user_id_by_email(text) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_user_id_by_google_id(text) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_email_taken(text, uuid) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_expired_user_ids(timestamp) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_release_push_endpoint(text) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_users_with_unpushed_reminders(timestamp) TO " + APP_ROLE,
    ]


def install(engine: Engine) -> bool:
    """Create the functions and policies, and grant to the app role if it exists.

    Returns False and does nothing on SQLite. The policies name ``APP_ROLE``, so
    they cannot be created before it exists; until then only the functions are
    installed, which is all the application needs to run.
    """
    if engine.dialect.name != "postgresql":
        return False
    with engine.begin() as conn:
        conn.execute(text(FUNCTION_SQL))
        role_exists = conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": APP_ROLE}
        ).scalar() is not None
        if role_exists:
            for statement in policy_statements() + grant_statements():
                conn.execute(text(statement))
    if role_exists:
        logger.info("row-level security in place for %s", APP_ROLE)
    else:
        logger.info("functions installed; role %s does not exist, so no policies yet", APP_ROLE)
    return True


def render_sql() -> str:
    """The whole installation as one script, for review or for the SQL editor."""
    parts = [FUNCTION_SQL.strip()]
    parts += [s + ";" for s in policy_statements()]
    parts += [s + ";" for s in grant_statements()]
    return "\n".join(parts) + "\n"


if __name__ == "__main__":
    print(render_sql())
