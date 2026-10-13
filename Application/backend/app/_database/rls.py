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
  answer with an id or a boolean, never with rows -- apart from the narrow
  views sharing needs (a partner's figure, a shared task's few fields).
* ``SEALED_TABLES`` (Phase 2 D25) are read by nobody through the API: row
  security with no policy, and no grant, the app role's included. Only a
  definer function writes them.
* ``NO_DIRECT_WRITE_TABLES`` (Phase 2 D23, D24, D26) are per-user tables the app role
  may read and delete from but never write: their rows are created only by a
  definer function, for the person who accepted a link.

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

#: Tables nobody reads through the API at all (Phase 2 D25): row-level
#: security with no policy, and every grant revoked, the app role's included.
#: Only a definer function, running as the owner, writes them. By name, like
#: the shared list, and refused if the table has an owner.
SEALED_TABLES = frozenset({"grade_distributions"})

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
    # Phase 2 item 9a (D23): shared tasks.
    "account_task_invite_preview",
    "account_accept_task_invite",
    "account_shared_tasks",
    "account_set_shared_task_done",
    "account_edit_shared_task",
    "account_leave_shared_task",
    # Phase 2 item 9b (D24): shared events.
    "account_event_invite_preview",
    "account_accept_event_invite",
    "account_shared_events",
    "account_leave_shared_event",
    # Phase 2 item 13 (D25): the daily recount into the sealed table.
    "account_recount_grade_distributions",
    # Phase 2 item 11 (D26): teams and games.
    "account_on_team",
    "account_team_invite_preview",
    "account_accept_team_invite",
    "account_my_teams",
    "account_team_games",
    "account_record_team_game",
    "account_confirm_team_game",
    "account_dispute_team_game",
    "account_correct_team_game",
    "account_delete_team_game",
    "account_leave_team",
)

#: Tables the app role may read and delete from but never insert into or
#: update (Phase 2 D23). A membership row is written only by the accept
#: function, for the person holding the link -- so not even the task's owner
#: can put somebody on a task, and nobody can rewrite a copied name.
NO_DIRECT_WRITE_TABLES = frozenset({"task_members", "event_members", "team_members", "games"})

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

-- Phase 2 item 9a (D23): shared tasks. A member reaches the owner's task
-- only through these, each keyed on account_current_user(), and each ignoring
-- a repeating occurrence and an owner whose account is being deleted.

-- What a live link is for: the owner's name and the task's title.
CREATE OR REPLACE FUNCTION account_task_invite_preview(p_token_hash text)
    RETURNS TABLE(owner_name text, title text)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ SELECT u.name::text, t.title::text
          FROM task_invites i JOIN tasks t ON t.id = i.task_id JOIN users u ON u.id = t.user_id
          WHERE account_current_user() IS NOT NULL
            AND i.token_hash = p_token_hash AND i.revoked_at IS NULL
            AND i.expires_at > (now() AT TIME ZONE 'utc')
            AND t.recurring_id IS NULL AND u.deleted_at IS NULL $$;

-- The only writer of task_members: the caller joins, never anyone else. The
-- task is locked so two people accepting at once cannot both take the last
-- place. 8 is models.MAX_TASK_MEMBERS.
CREATE OR REPLACE FUNCTION account_accept_task_invite(p_token_hash text) RETURNS text
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$
DECLARE
    me uuid := account_current_user();
    inv task_invites%ROWTYPE;
    t tasks%ROWTYPE;
    my_name text;
    their_name text;
BEGIN
    IF me IS NULL THEN RETURN 'invalid'; END IF;
    SELECT * INTO inv FROM task_invites
        WHERE token_hash = p_token_hash AND revoked_at IS NULL
          AND expires_at > (now() AT TIME ZONE 'utc');
    IF NOT FOUND THEN RETURN 'invalid'; END IF;
    SELECT * INTO t FROM tasks WHERE id = inv.task_id FOR UPDATE;
    IF NOT FOUND OR t.recurring_id IS NOT NULL THEN RETURN 'invalid'; END IF;
    IF t.user_id = me THEN RETURN 'own'; END IF;
    SELECT name INTO my_name FROM users WHERE id = me AND deleted_at IS NULL;
    SELECT name INTO their_name FROM users WHERE id = t.user_id AND deleted_at IS NULL;
    IF my_name IS NULL OR their_name IS NULL THEN RETURN 'invalid'; END IF;
    IF EXISTS (SELECT 1 FROM task_members WHERE task_id = t.id AND member_id = me) THEN
        RETURN 'already';
    END IF;
    IF (SELECT count(*) FROM task_members WHERE task_id = t.id) >= 8 THEN RETURN 'full'; END IF;
    INSERT INTO task_members (id, task_id, member_id, member_name, owner_name, joined_at)
        VALUES (gen_random_uuid(), t.id, me, my_name, their_name, now() AT TIME ZONE 'utc')
        ON CONFLICT (task_id, member_id) DO NOTHING;
    RETURN 'accepted';
END $$;

-- The tasks the caller is a member of, with the fields a member may see:
-- never the course, the grade, the timer, priority or tags.
CREATE OR REPLACE FUNCTION account_shared_tasks()
    RETURNS TABLE(task_id uuid, owner_name text, title text, notes text, due_date date,
                  due_time time, done boolean, completed_at timestamp, member_names text[])
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ SELECT t.id, m.owner_name::text, t.title::text, t.notes::text, t.due_date, t.due_time,
                 t.done, t.completed_at,
                 ARRAY(SELECT o.member_name::text FROM task_members o
                       WHERE o.task_id = t.id ORDER BY o.joined_at, o.member_name)
          FROM task_members m
          JOIN tasks t ON t.id = m.task_id
          JOIN users u ON u.id = t.user_id
          WHERE m.member_id = account_current_user()
            AND t.recurring_id IS NULL AND u.deleted_at IS NULL $$;

-- One tick closes it for everyone, the same way the owner's tick does:
-- completed and archived together, or neither.
CREATE OR REPLACE FUNCTION account_set_shared_task_done(p_task uuid, p_done boolean) RETURNS boolean
    LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ WITH changed AS (
              UPDATE tasks t
              SET done = p_done,
                  completed_at = CASE WHEN p_done THEN now() AT TIME ZONE 'utc' END,
                  archived = p_done
              WHERE t.id = p_task AND t.recurring_id IS NULL AND p_done IS NOT NULL
                AND EXISTS (SELECT 1 FROM task_members m
                            WHERE m.task_id = t.id AND m.member_id = account_current_user())
                AND EXISTS (SELECT 1 FROM users u WHERE u.id = t.user_id AND u.deleted_at IS NULL)
              RETURNING 1)
          SELECT count(*) > 0 FROM changed $$;

-- The text, and only the text. The same limits as the API's own checks.
CREATE OR REPLACE FUNCTION account_edit_shared_task(p_task uuid, p_title text, p_notes text) RETURNS boolean
    LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ WITH changed AS (
              UPDATE tasks t SET title = btrim(p_title), notes = p_notes
              WHERE t.id = p_task AND t.recurring_id IS NULL
                AND length(btrim(coalesce(p_title, ''))) BETWEEN 1 AND 200
                AND (p_notes IS NULL OR length(p_notes) <= 2000)
                AND EXISTS (SELECT 1 FROM task_members m
                            WHERE m.task_id = t.id AND m.member_id = account_current_user())
                AND EXISTS (SELECT 1 FROM users u WHERE u.id = t.user_id AND u.deleted_at IS NULL)
              RETURNING 1)
          SELECT count(*) > 0 FROM changed $$;

-- A member removes themselves, and nobody else.
CREATE OR REPLACE FUNCTION account_leave_shared_task(p_task uuid) RETURNS boolean
    LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ WITH gone AS (
              DELETE FROM task_members
              WHERE task_id = p_task AND member_id = account_current_user()
              RETURNING 1)
          SELECT count(*) > 0 FROM gone $$;

-- Phase 2 item 9b (D24): shared events. The same shape as shared tasks, but a
-- member only sees and leaves: nothing a member does changes the event. A
-- shareable event is a one-off of the owner's own: not a repeat, not a
-- shift, not a block a grade produced.

CREATE OR REPLACE FUNCTION account_event_invite_preview(p_token_hash text)
    RETURNS TABLE(owner_name text, title text, starts_on date)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ SELECT u.name::text, e.title::text, e.starts_on
          FROM event_invites i JOIN events e ON e.id = i.event_id JOIN users u ON u.id = e.user_id
          WHERE account_current_user() IS NOT NULL
            AND i.token_hash = p_token_hash AND i.revoked_at IS NULL
            AND i.expires_at > (now() AT TIME ZONE 'utc')
            AND e.recur_freq IS NULL AND e.job_id IS NULL AND e.grade_id IS NULL
            AND u.deleted_at IS NULL $$;

-- The only writer of event_members. 8 is models.MAX_EVENT_MEMBERS.
CREATE OR REPLACE FUNCTION account_accept_event_invite(p_token_hash text) RETURNS text
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$
DECLARE
    me uuid := account_current_user();
    inv event_invites%ROWTYPE;
    ev events%ROWTYPE;
    my_name text;
    their_name text;
BEGIN
    IF me IS NULL THEN RETURN 'invalid'; END IF;
    SELECT * INTO inv FROM event_invites
        WHERE token_hash = p_token_hash AND revoked_at IS NULL
          AND expires_at > (now() AT TIME ZONE 'utc');
    IF NOT FOUND THEN RETURN 'invalid'; END IF;
    SELECT * INTO ev FROM events WHERE id = inv.event_id FOR UPDATE;
    IF NOT FOUND OR ev.recur_freq IS NOT NULL OR ev.job_id IS NOT NULL OR ev.grade_id IS NOT NULL THEN
        RETURN 'invalid';
    END IF;
    IF ev.user_id = me THEN RETURN 'own'; END IF;
    SELECT name INTO my_name FROM users WHERE id = me AND deleted_at IS NULL;
    SELECT name INTO their_name FROM users WHERE id = ev.user_id AND deleted_at IS NULL;
    IF my_name IS NULL OR their_name IS NULL THEN RETURN 'invalid'; END IF;
    IF EXISTS (SELECT 1 FROM event_members WHERE event_id = ev.id AND member_id = me) THEN
        RETURN 'already';
    END IF;
    IF (SELECT count(*) FROM event_members WHERE event_id = ev.id) >= 8 THEN RETURN 'full'; END IF;
    INSERT INTO event_members (id, event_id, member_id, member_name, owner_name, joined_at)
        VALUES (gen_random_uuid(), ev.id, me, my_name, their_name, now() AT TIME ZONE 'utc')
        ON CONFLICT (event_id, member_id) DO NOTHING;
    RETURN 'accepted';
END $$;

-- The events the caller is on: when and where, never the course.
CREATE OR REPLACE FUNCTION account_shared_events()
    RETURNS TABLE(event_id uuid, owner_name text, title text, kind text, location text, notes text,
                  starts_on date, start_time time, end_time time, member_names text[])
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ SELECT e.id, m.owner_name::text, e.title::text, e.kind::text, e.location::text, e.notes::text,
                 e.starts_on, e.start_time, e.end_time,
                 ARRAY(SELECT o.member_name::text FROM event_members o
                       WHERE o.event_id = e.id ORDER BY o.joined_at, o.member_name)
          FROM event_members m
          JOIN events e ON e.id = m.event_id
          JOIN users u ON u.id = e.user_id
          WHERE m.member_id = account_current_user()
            AND e.recur_freq IS NULL AND e.job_id IS NULL AND e.grade_id IS NULL
            AND u.deleted_at IS NULL $$;

CREATE OR REPLACE FUNCTION account_leave_shared_event(p_event uuid) RETURNS boolean
    LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ WITH gone AS (
              DELETE FROM event_members
              WHERE event_id = p_event AND member_id = account_current_user()
              RETURNING 1)
          SELECT count(*) > 0 FROM gone $$;

-- Phase 2 item 13 (D25). Rebuilds grade_distributions whole, from the grades
-- contributors chose to add, read from each course at this moment -- the
-- final grade, or the running average when there is none. A course-term with
-- fewer than 5 contributors (models.COHORT_FLOOR) is not written at all, so a
-- group small enough to point at a person never exists. Answers with how many
-- rows it wrote, and nothing else.
CREATE OR REPLACE FUNCTION account_recount_grade_distributions() RETURNS integer
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$
DECLARE
    written integer;
BEGIN
    DELETE FROM grade_distributions;
    WITH graded AS (
        SELECT r.course_key, r.term_code,
               CASE WHEN c.final_grade > 0 THEN c.final_grade
                    WHEN c.average > 0 THEN c.average END AS grade
        FROM term_reviews r
        JOIN courses c ON c.id = r.course_id
        JOIN users u ON u.id = r.user_id
        WHERE r.contribute_grade AND NOT r.skipped AND u.deleted_at IS NULL AND NOT c.transfer_credit
          AND r.course_key IS NOT NULL AND r.term_code IS NOT NULL
    ), counted AS (
        SELECT course_key, term_code,
               CASE WHEN grade < 50 THEN 0 ELSE LEAST(95, (floor(grade / 5) * 5)::integer) END AS bucket
        FROM graded WHERE grade IS NOT NULL
    ), enough AS (
        SELECT course_key, term_code FROM counted GROUP BY course_key, term_code HAVING count(*) >= 5
    )
    INSERT INTO grade_distributions (id, course_key, term_code, bucket, contributors, computed_at)
        SELECT gen_random_uuid(), counted.course_key, counted.term_code, counted.bucket, count(*),
               now() AT TIME ZONE 'utc'
        FROM counted JOIN enough USING (course_key, term_code)
        GROUP BY counted.course_key, counted.term_code, counted.bucket;
    GET DIAGNOSTICS written = ROW_COUNT;
    RETURN written;
END $$;

-- Phase 2 item 11 (D26): teams. "On the team" means the captain or a member,
-- of a captain whose account is not being deleted. Every game write goes
-- through these, the captain's included.
CREATE OR REPLACE FUNCTION account_on_team(p_team uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ SELECT account_current_user() IS NOT NULL AND EXISTS (
              SELECT 1 FROM teams t JOIN users u ON u.id = t.user_id
              WHERE t.id = p_team AND u.deleted_at IS NULL
                AND (t.user_id = account_current_user()
                     OR EXISTS (SELECT 1 FROM team_members m
                                WHERE m.team_id = t.id AND m.member_id = account_current_user()))) $$;

CREATE OR REPLACE FUNCTION account_team_invite_preview(p_token_hash text)
    RETURNS TABLE(captain_name text, team_name text, sport text)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ SELECT u.name::text, t.name::text, t.sport::text
          FROM team_invites i JOIN teams t ON t.id = i.team_id JOIN users u ON u.id = t.user_id
          WHERE account_current_user() IS NOT NULL
            AND i.token_hash = p_token_hash AND i.revoked_at IS NULL
            AND i.expires_at > (now() AT TIME ZONE 'utc') AND u.deleted_at IS NULL $$;

-- The only writer of team_members. 30 is models.MAX_TEAM_MEMBERS.
CREATE OR REPLACE FUNCTION account_accept_team_invite(p_token_hash text) RETURNS text
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$
DECLARE
    me uuid := account_current_user();
    inv team_invites%ROWTYPE;
    tm teams%ROWTYPE;
    my_name text;
    their_name text;
BEGIN
    IF me IS NULL THEN RETURN 'invalid'; END IF;
    SELECT * INTO inv FROM team_invites
        WHERE token_hash = p_token_hash AND revoked_at IS NULL
          AND expires_at > (now() AT TIME ZONE 'utc');
    IF NOT FOUND THEN RETURN 'invalid'; END IF;
    SELECT * INTO tm FROM teams WHERE id = inv.team_id FOR UPDATE;
    IF NOT FOUND THEN RETURN 'invalid'; END IF;
    IF tm.user_id = me THEN RETURN 'own'; END IF;
    SELECT name INTO my_name FROM users WHERE id = me AND deleted_at IS NULL;
    SELECT name INTO their_name FROM users WHERE id = tm.user_id AND deleted_at IS NULL;
    IF my_name IS NULL OR their_name IS NULL THEN RETURN 'invalid'; END IF;
    IF EXISTS (SELECT 1 FROM team_members WHERE team_id = tm.id AND member_id = me) THEN
        RETURN 'already';
    END IF;
    IF (SELECT count(*) FROM team_members WHERE team_id = tm.id) >= 30 THEN RETURN 'full'; END IF;
    INSERT INTO team_members (id, team_id, member_id, member_name, owner_name, joined_at)
        VALUES (gen_random_uuid(), tm.id, me, my_name, their_name, now() AT TIME ZONE 'utc')
        ON CONFLICT (team_id, member_id) DO NOTHING;
    RETURN 'accepted';
END $$;

-- The teams the caller plays on as a member (a captain reads their own).
CREATE OR REPLACE FUNCTION account_my_teams()
    RETURNS TABLE(team_id uuid, team_name text, sport text, captain_name text, member_names text[])
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ SELECT t.id, t.name::text, t.sport::text, m.owner_name::text,
                 ARRAY(SELECT o.member_name::text FROM team_members o
                       WHERE o.team_id = t.id ORDER BY o.joined_at, o.member_name)
          FROM team_members m JOIN teams t ON t.id = m.team_id JOIN users u ON u.id = t.user_id
          WHERE m.member_id = account_current_user() AND u.deleted_at IS NULL $$;

-- A team's games, for anyone on it. Names, and whether it was you -- never
-- another person's id.
CREATE OR REPLACE FUNCTION account_team_games(p_team uuid)
    RETURNS TABLE(game_id uuid, played_on date, opponent text, our_score integer, their_score integer,
                  recorded_by_name text, recorded_by_me boolean, confirmed_by_name text,
                  confirmed_at timestamp, disputed_by_name text, disputed_by_me boolean,
                  disputed_our integer, disputed_their integer)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ SELECT g.id, g.played_on, g.opponent::text, g.our_score, g.their_score,
                 g.recorded_by_name::text, g.recorded_by = account_current_user(),
                 g.confirmed_by_name::text, g.confirmed_at,
                 g.disputed_by_name::text, coalesce(g.disputed_by = account_current_user(), false),
                 g.disputed_our, g.disputed_their
          FROM games g
          WHERE g.team_id = p_team AND account_on_team(p_team)
          ORDER BY g.played_on DESC, g.created_at DESC $$;

CREATE OR REPLACE FUNCTION account_record_team_game(p_team uuid, p_played_on date, p_opponent text,
                                                    p_ours integer, p_theirs integer) RETURNS uuid
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$
DECLARE
    me uuid := account_current_user();
    my_name text;
    new_id uuid := gen_random_uuid();
BEGIN
    IF NOT account_on_team(p_team) OR p_played_on IS NULL
       OR length(btrim(coalesce(p_opponent, ''))) NOT BETWEEN 1 AND 60
       OR p_ours IS NULL OR p_theirs IS NULL
       OR p_ours NOT BETWEEN 0 AND 999 OR p_theirs NOT BETWEEN 0 AND 999 THEN
        RETURN NULL;
    END IF;
    SELECT name INTO my_name FROM users WHERE id = me;
    INSERT INTO games (id, team_id, played_on, opponent, our_score, their_score,
                       recorded_by, recorded_by_name, created_at)
        VALUES (new_id, p_team, p_played_on, btrim(p_opponent), p_ours, p_theirs,
                me, my_name, now() AT TIME ZONE 'utc');
    RETURN new_id;
END $$;

-- Someone else agrees. Not the recorder, not once confirmed, and not over
-- someone else's dispute: a disputed game is settled by its recorder
-- correcting it. Confirming your own dispute withdraws it.
CREATE OR REPLACE FUNCTION account_confirm_team_game(p_game uuid) RETURNS boolean
    LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ WITH changed AS (
              UPDATE games g
              SET confirmed_by = account_current_user(),
                  confirmed_by_name = (SELECT name FROM users WHERE id = account_current_user()),
                  confirmed_at = now() AT TIME ZONE 'utc',
                  disputed_by = NULL, disputed_by_name = NULL, disputed_our = NULL, disputed_their = NULL
              WHERE g.id = p_game AND account_on_team(g.team_id)
                AND g.recorded_by <> account_current_user() AND g.confirmed_by IS NULL
                AND (g.disputed_by IS NULL OR g.disputed_by = account_current_user())
              RETURNING 1)
          SELECT count(*) > 0 FROM changed $$;

CREATE OR REPLACE FUNCTION account_dispute_team_game(p_game uuid, p_ours integer, p_theirs integer) RETURNS boolean
    LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ WITH changed AS (
              UPDATE games g
              SET disputed_by = account_current_user(),
                  disputed_by_name = (SELECT name FROM users WHERE id = account_current_user()),
                  disputed_our = p_ours, disputed_their = p_theirs
              WHERE g.id = p_game AND account_on_team(g.team_id)
                AND g.recorded_by <> account_current_user() AND g.confirmed_by IS NULL
                AND p_ours BETWEEN 0 AND 999 AND p_theirs BETWEEN 0 AND 999
              RETURNING 1)
          SELECT count(*) > 0 FROM changed $$;

-- The recorder fixes their own unconfirmed game; a correction clears a dispute.
CREATE OR REPLACE FUNCTION account_correct_team_game(p_game uuid, p_played_on date, p_opponent text,
                                                     p_ours integer, p_theirs integer) RETURNS boolean
    LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ WITH changed AS (
              UPDATE games g
              SET played_on = p_played_on, opponent = btrim(p_opponent), our_score = p_ours,
                  their_score = p_theirs,
                  disputed_by = NULL, disputed_by_name = NULL, disputed_our = NULL, disputed_their = NULL
              WHERE g.id = p_game AND account_on_team(g.team_id)
                AND g.recorded_by = account_current_user() AND g.confirmed_by IS NULL
                AND p_played_on IS NOT NULL
                AND length(btrim(coalesce(p_opponent, ''))) BETWEEN 1 AND 60
                AND p_ours BETWEEN 0 AND 999 AND p_theirs BETWEEN 0 AND 999
              RETURNING 1)
          SELECT count(*) > 0 FROM changed $$;

-- The recorder, while it's unconfirmed; or the captain, any time.
CREATE OR REPLACE FUNCTION account_delete_team_game(p_game uuid) RETURNS boolean
    LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ WITH gone AS (
              DELETE FROM games g
              WHERE g.id = p_game AND account_on_team(g.team_id)
                AND ((g.recorded_by = account_current_user() AND g.confirmed_by IS NULL)
                     OR EXISTS (SELECT 1 FROM teams t
                                WHERE t.id = g.team_id AND t.user_id = account_current_user()))
              RETURNING 1)
          SELECT count(*) > 0 FROM gone $$;

CREATE OR REPLACE FUNCTION account_leave_team(p_team uuid) RETURNS boolean
    LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ WITH gone AS (
              DELETE FROM team_members
              WHERE team_id = p_team AND member_id = account_current_user()
              RETURNING 1)
          SELECT count(*) > 0 FROM gone $$;

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
REVOKE ALL ON FUNCTION account_task_invite_preview(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_accept_task_invite(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_shared_tasks() FROM PUBLIC;
REVOKE ALL ON FUNCTION account_set_shared_task_done(uuid, boolean) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_edit_shared_task(uuid, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_leave_shared_task(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_event_invite_preview(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_accept_event_invite(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_shared_events() FROM PUBLIC;
REVOKE ALL ON FUNCTION account_leave_shared_event(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_recount_grade_distributions() FROM PUBLIC;
REVOKE ALL ON FUNCTION account_on_team(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_team_invite_preview(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_accept_team_invite(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_my_teams() FROM PUBLIC;
REVOKE ALL ON FUNCTION account_team_games(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_record_team_game(uuid, date, text, integer, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_confirm_team_game(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_dispute_team_game(uuid, integer, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_correct_team_game(uuid, date, text, integer, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_delete_team_game(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_leave_team(uuid) FROM PUBLIC;

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


def _check_no_direct_write_list() -> None:
    """Every name is a real table, and none is shared: a shared table is
    already read-only, and a typo would leave the real table writable."""
    unknown = NO_DIRECT_WRITE_TABLES - set(Base.metadata.tables)
    if unknown:
        raise ValueError(f"NO_DIRECT_WRITE_TABLES names tables no model builds: {sorted(unknown)}")
    both = NO_DIRECT_WRITE_TABLES & SHARED_READ_TABLES
    if both:
        raise ValueError(f"Tables on both lists: {sorted(both)}")


def is_sealed(table: Table) -> bool:
    """Whether ``table`` is sealed -- and if it is, that it has no owner. A
    sealed table with an owner would hide that owner's own rows from them."""
    if table.name not in SEALED_TABLES:
        return False
    if table.name == "users" or "user_id" in table.columns or _owner_parent(table) is not None:
        raise ValueError(f"Table {table.name!r} is listed in SEALED_TABLES but has an owner.")
    return True


def _check_sealed_list() -> None:
    unknown = SEALED_TABLES - set(Base.metadata.tables)
    if unknown:
        raise ValueError(f"SEALED_TABLES names tables no model builds: {sorted(unknown)}")
    both = SEALED_TABLES & (SHARED_READ_TABLES | NO_DIRECT_WRITE_TABLES)
    if both:
        raise ValueError(f"Tables on both lists: {sorted(both)}")


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
    _check_no_direct_write_list()
    _check_sealed_list()
    statements = []
    for table in Base.metadata.sorted_tables:
        if is_sealed(table):
            # Row security on and no policy at all: under RLS a command with no
            # policy is refused, so no role but the owner sees a row.
            statements += [
                f"ALTER TABLE {table.name} ENABLE ROW LEVEL SECURITY",
                f"DROP POLICY IF EXISTS {POLICY} ON {table.name}",
            ]
            continue
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
    private = [table for table in tables if not is_shared(table) and not is_sealed(table)]
    return [
        "GRANT USAGE ON SCHEMA public TO " + APP_ROLE,
        # Every other grantee first, so only the app role's grants below stand
        # (D6). Shared and sealed tables do the same in their own helpers.
        *(statement for table in private for statement in _revoke_from_others(table.name)),
        *(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table.name} TO {APP_ROLE}"
            for table in private
            if table.name not in NO_DIRECT_WRITE_TABLES
        ),
        *(statement for table in tables if is_sealed(table) for statement in _sealed_grants(table)),
        # Read and delete only. The REVOKE takes back a write grant left by
        # an earlier shape, as the shared tables' does.
        *(
            statement
            for table in tables
            if table.name in NO_DIRECT_WRITE_TABLES
            for statement in (
                f"REVOKE INSERT, UPDATE, TRUNCATE ON {table.name} FROM {APP_ROLE}",
                f"GRANT SELECT, DELETE ON {table.name} TO {APP_ROLE}",
            )
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
        "GRANT EXECUTE ON FUNCTION account_task_invite_preview(text) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_accept_task_invite(text) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_shared_tasks() TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_set_shared_task_done(uuid, boolean) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_edit_shared_task(uuid, text, text) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_leave_shared_task(uuid) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_event_invite_preview(text) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_accept_event_invite(text) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_shared_events() TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_leave_shared_event(uuid) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_recount_grade_distributions() TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_on_team(uuid) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_team_invite_preview(text) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_accept_team_invite(text) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_my_teams() TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_team_games(uuid) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_record_team_game(uuid, date, text, integer, integer) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_confirm_team_game(uuid) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_dispute_team_game(uuid, integer, integer) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_correct_team_game(uuid, date, text, integer, integer) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_delete_team_game(uuid) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_leave_team(uuid) TO " + APP_ROLE,
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
        *_revoke_from_others(name),
        f"REVOKE {WRITE_PRIVILEGES} ON {name} FROM {APP_ROLE}",
        f"GRANT SELECT ON {name} TO {APP_ROLE}",
    ]


def _revoke_from_others(name: str) -> list[str]:
    """Take every privilege on a table from everyone but its owner and the app role.

    Supabase's default privileges grant every new table to anon, authenticated
    and service_role by name, TRUNCATE included, which row-level security does
    not cover. That held for every per-user table until Phase 3 batch 1's
    read-back showed it (D6): only shared tables had been locked down. Reached
    only through the Data API, which is off -- but one setting is not a
    boundary, so no role but the API's keeps a grant.
    """
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
    ]


def _sealed_grants(table: Table) -> list[str]:
    """Nothing to anyone but the owner -- the app role included."""
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
    LOOP
        EXECUTE format('REVOKE ALL ON public.{name} FROM %I', r.rolname);
    END LOOP;
END $$""",
        f"REVOKE ALL ON {name} FROM {APP_ROLE}",
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
