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
* The one exception is by name: ``SHARED_READ_TABLES``, world knowledge such as
  the course catalogue (Phase 2 item 1). Every identified caller may read them,
  and the app role can write none of them -- refused twice, by a SELECT-only
  grant and by a policy that covers SELECT alone. Only the tables' owner writes
  them, through an owner-run script.
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

#: Tables that belong to nobody: every signed-in user reads them, no request
#: writes them (Phase 2 D9). By name, so an ownerless table still raises
#: unless someone decided, here, that it is shared.
SHARED_READ_TABLES = frozenset({"catalogue_courses", "catalogue_prerequisites"})

#: Who may read a shared row: anyone the API has identified. Not ``true``, so an
#: un-identified query still sees nothing -- the same fail-closed rule as every
#: other table, at no cost, since every catalogue read is inside a request.
SHARED_PREDICATE = "account_current_user() IS NOT NULL"

#: Everything a grant can carry on a table besides SELECT. Revoked from the app
#: role on shared tables, so a grant left from an earlier shape is taken back.
WRITE_PRIVILEGES = "INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER"

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
    # Phase 2 item 10 (D22): invites and accountability partners.
    "account_invite_preview",
    "account_accept_partner_invite",
    "account_end_partnership",
    "account_partner_figures",
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

-- Phase 2 item 10 (D22). An invite is looked up by the hash of its token,
-- and answers with the inviter's display name and nothing else -- only for a
-- caller who is signed in, and only while the invite is live.
CREATE OR REPLACE FUNCTION account_invite_preview(p_token_hash text)
    RETURNS TABLE(inviter_name text, kind text)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ SELECT u.name::text, i.kind::text FROM invites i JOIN users u ON u.id = i.user_id
          WHERE account_current_user() IS NOT NULL
            AND i.token_hash = p_token_hash AND i.used_at IS NULL AND i.revoked_at IS NULL
            AND i.expires_at > (now() AT TIME ZONE 'utc') AND u.deleted_at IS NULL $$;

-- Accepting is the one place a row is written for someone else: both sides of
-- the partnership, together, for the signed-in caller and the invite's owner.
-- The caller is account_current_user(), never a parameter, so nobody can
-- accept on another's behalf. Answers with a status word, never a row.
CREATE OR REPLACE FUNCTION account_accept_partner_invite(p_token_hash text) RETURNS text
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$
DECLARE
    me uuid := account_current_user();
    inv invites%ROWTYPE;
    my_name text;
    their_name text;
BEGIN
    IF me IS NULL THEN RETURN 'invalid'; END IF;
    SELECT * INTO inv FROM invites
        WHERE token_hash = p_token_hash AND kind = 'partner' AND used_at IS NULL
          AND revoked_at IS NULL AND expires_at > (now() AT TIME ZONE 'utc')
        FOR UPDATE;
    IF NOT FOUND THEN RETURN 'invalid'; END IF;
    IF inv.user_id = me THEN RETURN 'own'; END IF;
    SELECT name INTO my_name FROM users WHERE id = me AND deleted_at IS NULL;
    SELECT name INTO their_name FROM users WHERE id = inv.user_id AND deleted_at IS NULL;
    IF my_name IS NULL OR their_name IS NULL THEN RETURN 'invalid'; END IF;
    IF EXISTS (SELECT 1 FROM partnerships WHERE user_id = me AND partner_id = inv.user_id) THEN
        RETURN 'already';
    END IF;
    INSERT INTO partnerships (id, user_id, partner_id, partner_name, created_at, streak_weeks)
        VALUES (gen_random_uuid(), me, inv.user_id, their_name, now() AT TIME ZONE 'utc', 0),
               (gen_random_uuid(), inv.user_id, me, my_name, now() AT TIME ZONE 'utc', 0)
        ON CONFLICT (user_id, partner_id) DO NOTHING;
    UPDATE invites SET used_at = now() AT TIME ZONE 'utc', used_by = me WHERE id = inv.id;
    RETURN 'accepted';
END $$;

-- Either side may end it, and ending removes both rows.
CREATE OR REPLACE FUNCTION account_end_partnership(p_partner uuid) RETURNS boolean
    LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ WITH gone AS (
              DELETE FROM partnerships
              WHERE account_current_user() IS NOT NULL
                AND ((user_id = account_current_user() AND partner_id = p_partner)
                  OR (user_id = p_partner AND partner_id = account_current_user()))
              RETURNING 1)
          SELECT count(*) > 0 FROM gone $$;

-- A partner's figure: three numbers from their own row, and only while both
-- rows point at each other. A row naming someone that they never agreed to
-- (only the accept function can write theirs) shows nothing.
CREATE OR REPLACE FUNCTION account_partner_figures()
    RETURNS TABLE(partner_id uuid, week_percent double precision, streak_weeks integer, figure_on date)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ SELECT theirs.user_id, theirs.week_percent, theirs.streak_weeks, theirs.figure_on
          FROM partnerships theirs
          JOIN partnerships mine
            ON mine.user_id = account_current_user() AND mine.partner_id = theirs.user_id
          WHERE theirs.partner_id = account_current_user() $$;

-- Definer functions run with their owner's rights, so nobody but the API
-- needs to be able to call them.
REVOKE ALL ON FUNCTION account_user_id_by_email(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_user_id_by_google_id(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_email_taken(text, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_expired_user_ids(timestamp) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_release_push_endpoint(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_users_with_unpushed_reminders(timestamp) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_invite_preview(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_accept_partner_invite(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_end_partnership(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_partner_figures() FROM PUBLIC;

-- PUBLIC is not the only way in. Supabase's default privileges grant every new
-- function to anon and authenticated by name, and its Data API lets anon call
-- any of them. So: every definer function, every grantee but its owner and
-- the app role.
DO $$
DECLARE r record;
BEGIN
    FOR r IN
        SELECT p.oid::regprocedure AS fn, g.rolname
        FROM pg_proc p
        CROSS JOIN LATERAL aclexplode(p.proacl) a
        JOIN pg_roles g ON g.oid = a.grantee
        WHERE p.pronamespace = 'public'::regnamespace
          AND p.prosecdef
          AND left(p.proname, 8) = 'account_'
          AND a.grantee <> p.proowner
          AND g.rolname <> 'account_app'
    LOOP
        EXECUTE format('REVOKE ALL ON FUNCTION %s FROM %I', r.fn, r.rolname);
    END LOOP;
END $$;
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


def is_shared(table: Table) -> bool:
    """Whether ``table`` is on the shared list -- and if it is, that it is shaped
    like one.

    A table with an owner on the list would hand every user's rows in it to
    everyone, so naming one raises rather than quietly sharing it.
    """
    if table.name not in SHARED_READ_TABLES:
        return False
    if table.name == "users" or "user_id" in table.columns or _owner_parent(table) is not None:
        raise ValueError(
            f"Table {table.name!r} is listed in SHARED_READ_TABLES but has an owner. "
            "Shared tables hold world knowledge; a table with a user_id is per-user."
        )
    return True


def _check_shared_list() -> None:
    """Every shared name is a real table. A typo would leave the real table
    raising -- loud, but for the wrong reason -- and the list claiming a share
    that does not exist."""
    unknown = SHARED_READ_TABLES - set(Base.metadata.tables)
    if unknown:
        raise ValueError(f"SHARED_READ_TABLES names tables no model builds: {sorted(unknown)}")


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
    _check_shared_list()
    statements = []
    for table in Base.metadata.sorted_tables:
        if is_shared(table):
            statements += [
                f"ALTER TABLE {table.name} ENABLE ROW LEVEL SECURITY",
                f"DROP POLICY IF EXISTS {POLICY} ON {table.name}",
                # FOR SELECT and nothing else. Under row-level security a
                # command with no policy is refused, so this alone stops every
                # write -- the grant below stops them a second time.
                f"CREATE POLICY {POLICY} ON {table.name} FOR SELECT TO {APP_ROLE} "
                f"USING ({SHARED_PREDICATE})",
            ]
            continue
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
    """What the app role may do: data, never schema.

    Table by table from the metadata, never ``ALL TABLES``: a table the models
    don't build (production still holds one left by a rollback) gets no policy,
    so a grant on it would hand the app role every user's rows in it.
    """
    tables = Base.metadata.sorted_tables
    return [
        "GRANT USAGE ON SCHEMA public TO " + APP_ROLE,
        *(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table.name} TO {APP_ROLE}"
            for table in tables
            if not is_shared(table)
        ),
        *(statement for table in tables if is_shared(table) for statement in _shared_grants(table)),
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_current_user() TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_user_id_by_email(text) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_user_id_by_google_id(text) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_email_taken(text, uuid) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_expired_user_ids(timestamp) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_release_push_endpoint(text) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_users_with_unpushed_reminders(timestamp) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_invite_preview(text) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_accept_partner_invite(text) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_end_partnership(uuid) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_partner_figures() TO " + APP_ROLE,
    ]


def _shared_grants(table: Table) -> list[str]:
    """SELECT to the app role, and nothing to anyone else.

    Everyone else, not only PUBLIC: Supabase's default privileges grant every
    new table to anon and authenticated by name (Phase 0 D11), with TRUNCATE
    among them, which row-level security does not cover. So every grantee but
    the owner and the app role loses everything, the way the definer functions
    are locked down above.
    """
    name = table.name
    return [
        f"REVOKE ALL ON {name} FROM PUBLIC",
        f"""DO $$
DECLARE r record;
BEGIN
    FOR r IN
        SELECT DISTINCT g.rolname
        FROM pg_class c
        CROSS JOIN LATERAL aclexplode(c.relacl) a
        JOIN pg_roles g ON g.oid = a.grantee
        WHERE c.oid = 'public.{name}'::regclass
          AND a.grantee <> c.relowner
          AND g.rolname <> '{APP_ROLE}'
    LOOP
        EXECUTE format('REVOKE ALL ON public.{name} FROM %I', r.rolname);
    END LOOP;
END $$""",
        f"REVOKE {WRITE_PRIVILEGES} ON {name} FROM {APP_ROLE}",
        f"GRANT SELECT ON {name} TO {APP_ROLE}",
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
