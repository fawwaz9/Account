"""Row-level security for Postgres: the row policies, grants and definer functions.

`install` gives every model table a policy for the app role (`APP_ROLE`) chosen by
its kind: the `users` root, per-user, child of one owned table, shared-read or
sealed. Policies identify the caller through `account_current_user()`, which is NULL
while `app.user_id` is unset, so an unidentified query sees no rows; every step that
crosses users is a `SECURITY DEFINER` function in `FUNCTION_SQL`. SQLite has no row
security, so there the services' filters stand alone and `identity.py`,
`sharing.py`, `teams.py` and `distributions.py` hold plain-query twins.
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
"""Name of each table's one row policy; dropped and recreated on every install."""

#: Tables that belong to nobody: every signed-in user reads them, no request
#: writes them (Phase 2 D9). By name, so an ownerless table still raises
#: unless someone decided, here, that it is shared.
#: Phase 3 item 2 adds reviewed course outlines (D12), written by the outline review.
SHARED_READ_TABLES = frozenset({"catalogue_courses", "catalogue_prerequisites", "shared_outlines"})

#: Tables nobody reads through the API at all (Phase 2 D25): row-level
#: security with no policy, and every grant revoked, the app role's included.
#: Only a definer function, running as the owner, writes them. By name, like
#: the shared list, and refused if the table has an owner.
SEALED_TABLES = frozenset({
    "grade_distributions", "course_intel", "office_hour_slots", "salary_figures", "merchant_categories",
})

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
    # Phase 3 item 3 (D11): the counts' one door, through the floor.
    "account_grade_distribution",
    # Phase 3 item 5 (D11): what term reviews say, rebuilt daily, read through the floor.
    "account_recount_course_intel",
    "account_course_intel",
    # Phase 3 item 11 (D11): office-hour check-ins, counted per slot above the floor.
    "account_recount_office_hours",
    "account_office_hours",
    # Phase 3 item 12 (D11, D12): shared offers, verified, published in batches of 5.
    "account_recount_salaries",
    "account_salary_figures",
    # Phase 3 item 4 (D11): a merchant's category, once 3 people agree.
    "account_recount_merchant_categories",
    "account_merchant_categories",
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

-- Phase 3 D11: whether a term's answers may reach a shown figure yet. A term
-- code is "2025W1": Fall ends Dec 31, Winter (W2) Apr 30 the next year, Spring
-- (S1) Jun 30, Summer (S2) Aug 31. Counted 180 days after it ends
-- (models.COUNTED_AFTER_DAYS), when its asking window has closed, so no figure
-- moves in step with one person's answer. A code of any other shape never is.
-- Not a definer: it reads nothing, and only the functions below call it.
CREATE OR REPLACE FUNCTION account_term_counted(p_term_code text) RETURNS boolean
    LANGUAGE sql STABLE SET search_path = public, pg_temp
    AS $$ SELECT CASE WHEN p_term_code ~ '^[0-9]{4}(W1|W2|S1|S2)$' THEN
              (CASE substr(p_term_code, 5)
                   WHEN 'W1' THEN make_date(left(p_term_code, 4)::integer, 12, 31)
                   WHEN 'W2' THEN make_date(left(p_term_code, 4)::integer + 1, 4, 30)
                   WHEN 'S1' THEN make_date(left(p_term_code, 4)::integer, 6, 30)
                   ELSE make_date(left(p_term_code, 4)::integer, 8, 31)
               END) + 180 < (now() AT TIME ZONE 'utc')::date
          ELSE false END $$;

-- Phase 3 item 3 (D11): a course's counts, to anyone signed in. Only counted
-- terms (account_term_counted) at the floor (5, models.COHORT_FLOOR, checked
-- again here).
CREATE OR REPLACE FUNCTION account_grade_distribution(p_course_key text)
    RETURNS TABLE(term_code text, bucket integer, contributors integer)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ WITH counted AS (
              SELECT d.term_code
              FROM grade_distributions d
              WHERE d.course_key = p_course_key AND account_term_counted(d.term_code)
              GROUP BY d.term_code
              HAVING sum(d.contributors) >= 5)
          SELECT d.term_code::text, d.bucket, d.contributors
          FROM grade_distributions d JOIN counted USING (term_code)
          WHERE account_current_user() IS NOT NULL AND d.course_key = p_course_key
          ORDER BY d.term_code DESC, d.bucket $$;

-- Phase 3 item 5 (D11): what term reviews say about each course, rebuilt whole.
-- One answer per person per course (their latest counted term's), from live
-- accounts and reviews not skipped. A figure with fewer than 5 answers
-- (models.COHORT_FLOOR) is written as null, and a course with none at the
-- floor gets no row. Returns how many rows it wrote, never their contents.
CREATE OR REPLACE FUNCTION account_recount_course_intel() RETURNS integer
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$
DECLARE
    written integer;
BEGIN
    DELETE FROM course_intel;
    WITH answered AS (
        SELECT DISTINCT ON (r.user_id, r.course_key)
               r.course_key, r.hours_per_week, r.difficulty, r.clarity, r.would_take_again
        FROM term_reviews r JOIN users u ON u.id = r.user_id
        WHERE NOT r.skipped AND u.deleted_at IS NULL AND r.course_key IS NOT NULL
          AND account_term_counted(r.term_code)
        ORDER BY r.user_id, r.course_key, r.term_code DESC
    ), figures AS (
        SELECT course_key,
               count(hours_per_week) AS hours_n,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY hours_per_week) AS hours_median,
               count(difficulty) AS difficulty_n, avg(difficulty)::double precision AS difficulty_mean,
               count(clarity) AS clarity_n, avg(clarity)::double precision AS clarity_mean,
               count(would_take_again) AS again_n,
               (100.0 * count(*) FILTER (WHERE would_take_again)
                    / NULLIF(count(would_take_again), 0))::double precision AS again_share
        FROM answered GROUP BY course_key
    )
    INSERT INTO course_intel (id, course_key, hours_answers, hours_median, difficulty_answers, difficulty_mean,
                              clarity_answers, clarity_mean, again_answers, again_share, computed_at)
        SELECT gen_random_uuid(), course_key,
               CASE WHEN hours_n >= 5 THEN hours_n END, CASE WHEN hours_n >= 5 THEN hours_median END,
               CASE WHEN difficulty_n >= 5 THEN difficulty_n END,
               CASE WHEN difficulty_n >= 5 THEN difficulty_mean END,
               CASE WHEN clarity_n >= 5 THEN clarity_n END, CASE WHEN clarity_n >= 5 THEN clarity_mean END,
               CASE WHEN again_n >= 5 THEN again_n END, CASE WHEN again_n >= 5 THEN again_share END,
               now() AT TIME ZONE 'utc'
        FROM figures
        WHERE greatest(hours_n, difficulty_n, clarity_n, again_n) >= 5;
    GET DIAGNOSTICS written = ROW_COUNT;
    RETURN written;
END $$;

-- A course's figures, to anyone signed in, each only at the floor (checked
-- again here, so a row written by an older recount can't show less).
CREATE OR REPLACE FUNCTION account_course_intel(p_course_key text)
    RETURNS TABLE(hours_answers integer, hours_median double precision, difficulty_answers integer,
                  difficulty_mean double precision, clarity_answers integer, clarity_mean double precision,
                  again_answers integer, again_share double precision)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ SELECT CASE WHEN i.hours_answers >= 5 THEN i.hours_answers END,
                 CASE WHEN i.hours_answers >= 5 THEN i.hours_median END,
                 CASE WHEN i.difficulty_answers >= 5 THEN i.difficulty_answers END,
                 CASE WHEN i.difficulty_answers >= 5 THEN i.difficulty_mean END,
                 CASE WHEN i.clarity_answers >= 5 THEN i.clarity_answers END,
                 CASE WHEN i.clarity_answers >= 5 THEN i.clarity_mean END,
                 CASE WHEN i.again_answers >= 5 THEN i.again_answers END,
                 CASE WHEN i.again_answers >= 5 THEN i.again_share END
          FROM course_intel i
          WHERE account_current_user() IS NOT NULL AND i.course_key = p_course_key $$;

-- Phase 3 item 11 (D11): how busy each course's office hours usually are,
-- rebuilt whole. Each person's latest check-in per slot (course, local weekday
-- and hour) in the last 120 days (models.OFFICE_HOUR_WINDOW_DAYS), live
-- accounts only; no slot below 5 people (models.COHORT_FLOOR).
CREATE OR REPLACE FUNCTION account_recount_office_hours() RETURNS integer
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$
DECLARE
    written integer;
BEGIN
    DELETE FROM office_hour_slots;
    WITH latest AS (
        SELECT DISTINCT ON (c.user_id, c.course_key, c.weekday, c.hour)
               c.course_key, c.weekday, c.hour, c.wait
        FROM office_hour_checkins c JOIN users u ON u.id = c.user_id
        WHERE u.deleted_at IS NULL
          AND c.checked_at > (now() AT TIME ZONE 'utc') - interval '120 days'
        ORDER BY c.user_id, c.course_key, c.weekday, c.hour, c.checked_at DESC
    )
    INSERT INTO office_hour_slots (id, course_key, weekday, hour, people, none_votes, short_votes, long_votes,
                                   computed_at)
        SELECT gen_random_uuid(), course_key, weekday, hour, count(*),
               count(*) FILTER (WHERE wait = 'none'), count(*) FILTER (WHERE wait = 'short'),
               count(*) FILTER (WHERE wait = 'long'), now() AT TIME ZONE 'utc'
        FROM latest GROUP BY course_key, weekday, hour HAVING count(*) >= 5;
    GET DIAGNOSTICS written = ROW_COUNT;
    RETURN written;
END $$;

-- A course's slots, to anyone signed in, at the floor (checked again here).
CREATE OR REPLACE FUNCTION account_office_hours(p_course_key text)
    RETURNS TABLE(weekday integer, hour integer, people integer, none_votes integer, short_votes integer,
                  long_votes integer)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ SELECT s.weekday, s.hour, s.people, s.none_votes, s.short_votes, s.long_votes
          FROM office_hour_slots s
          WHERE account_current_user() IS NOT NULL AND s.course_key = p_course_key AND s.people >= 5
          ORDER BY s.weekday, s.hour $$;

-- Phase 3 item 12: an employer's name normalised, so "Shopify Inc." and
-- "shopify" are one employer. aggregates.employer_key is its twin. Not a
-- definer: it reads nothing.
CREATE OR REPLACE FUNCTION account_employer_key(p_name text) RETURNS text
    LANGUAGE sql IMMUTABLE SET search_path = public, pg_temp
    AS $$ SELECT regexp_replace(
              btrim(regexp_replace(
                  regexp_replace(replace(lower(coalesce(p_name, '')), '&', ' and '), '[^a-z0-9 ]', ' ', 'g'),
                  ' +', ' ', 'g')),
              '( (inc|ltd|llc|corp|corporation|co|company|limited))+$', '') $$;

-- Phase 3 item 12 (D11, D12): typical hourly pay per employer, rebuilt whole.
-- Each person's latest shared offer per employer, live accounts only, read
-- from the application now (hourly, or monthly x 12 or yearly over 2080 hours,
-- models.WORK_HOURS_PER_YEAR). An offer counts only once verified: it matches
-- the person's own hourly job at that employer within 5%, or 5 people's offers
-- there are within 10% of it. Only whole batches of 5 verified offers, oldest
-- share first, are counted, so one new share never shows as a change; no
-- employer below 5 (models.COHORT_FLOOR). Returns how many rows it wrote.
CREATE OR REPLACE FUNCTION account_recount_salaries() RETURNS integer
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$
DECLARE
    written integer;
BEGIN
    DELETE FROM salary_figures;
    WITH shared AS (
        SELECT DISTINCT ON (s.user_id, account_employer_key(a.company))
               s.user_id, account_employer_key(a.company) AS employer_key, btrim(a.company) AS employer,
               (CASE a.offer_period WHEN 'hourly' THEN a.offer_amount
                                    WHEN 'monthly' THEN a.offer_amount * 12 / 2080
                                    ELSE a.offer_amount / 2080 END)::double precision AS hourly,
               s.shared_at
        FROM salary_shares s
        JOIN job_applications a ON a.id = s.application_id AND a.user_id = s.user_id
        JOIN users u ON u.id = s.user_id
        WHERE u.deleted_at IS NULL AND a.offer_amount > 0 AND a.offer_period IS NOT NULL
          AND account_employer_key(a.company) <> ''
        ORDER BY s.user_id, account_employer_key(a.company), s.shared_at DESC
    ), checked AS (
        SELECT sh.employer_key, sh.employer, sh.hourly, sh.shared_at,
               EXISTS (SELECT 1 FROM jobs j
                       WHERE j.user_id = sh.user_id AND j.kind = 'hourly'
                         AND account_employer_key(j.employer) = sh.employer_key
                         AND j.hourly_rate BETWEEN sh.hourly * 0.95 AND sh.hourly * 1.05) AS own_job,
               (SELECT count(*) FROM shared o
                WHERE o.employer_key = sh.employer_key AND abs(o.hourly - sh.hourly) <= 0.10 * sh.hourly) AS agreeing
        FROM shared sh
    ), verified AS (
        SELECT employer_key, employer, hourly,
               row_number() OVER (PARTITION BY employer_key ORDER BY shared_at, hourly) AS n,
               count(*) OVER (PARTITION BY employer_key) AS total
        FROM checked WHERE own_job OR agreeing >= 5
    )
    INSERT INTO salary_figures (id, employer_key, employer, people, median, p25, p75, computed_at)
        SELECT gen_random_uuid(), employer_key, mode() WITHIN GROUP (ORDER BY employer), count(*),
               percentile_cont(0.5) WITHIN GROUP (ORDER BY hourly),
               percentile_cont(0.25) WITHIN GROUP (ORDER BY hourly),
               percentile_cont(0.75) WITHIN GROUP (ORDER BY hourly),
               now() AT TIME ZONE 'utc'
        FROM verified WHERE n <= (total / 5) * 5
        GROUP BY employer_key HAVING count(*) >= 5;
    GET DIAGNOSTICS written = ROW_COUNT;
    RETURN written;
END $$;

-- Every employer's figures, to anyone signed in, at the floor (checked again).
CREATE OR REPLACE FUNCTION account_salary_figures()
    RETURNS TABLE(employer text, people integer, median double precision, p25 double precision,
                  p75 double precision)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ SELECT f.employer::text, f.people, f.median, f.p25, f.p75
          FROM salary_figures f
          WHERE account_current_user() IS NOT NULL AND f.people >= 5
          ORDER BY lower(f.employer) $$;

-- Phase 3 item 4: a transaction's description as a merchant key, the twin of
-- forecast_service.merchant_key: lower case, digits, # and * as spaces, single
-- spaces, and spaces, dashes, dots and commas trimmed. Not a definer.
CREATE OR REPLACE FUNCTION account_merchant_key(p_description text) RETURNS text
    LANGUAGE sql IMMUTABLE SET search_path = public, pg_temp
    AS $$ SELECT btrim(regexp_replace(regexp_replace(lower(coalesce(p_description, '')), '[0-9#*]+', ' ', 'g'),
                                     '[[:space:]]+', ' ', 'g'), ' -.,') $$;

-- Phase 3 item 4 (D11): the category most people file each merchant under,
-- rebuilt whole. One vote per person per merchant: the unarchived category
-- holding 80% of their expenses there (categorize_service.MAP_AGREEMENT), from
-- live accounts that haven't switched sharing off. Transfers, payments and the
-- like are never merchants (aggregates.NOT_MERCHANTS), nor keys under 3
-- letters. Written only at 3 people (models.MERCHANT_FLOOR) holding 75% of the
-- votes, so a contested merchant stays out. Returns how many rows it wrote.
CREATE OR REPLACE FUNCTION account_recount_merchant_categories() RETURNS integer
    LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$
DECLARE
    written integer;
BEGIN
    DELETE FROM merchant_categories;
    WITH chosen AS (
        SELECT t.user_id, account_merchant_key(t.description) AS merchant_key, lower(c.name) AS category_name,
               count(*) AS n
        FROM transactions t
        JOIN spend_categories c ON c.id = t.category_id AND c.user_id = t.user_id AND NOT c.archived
        JOIN users u ON u.id = t.user_id
        WHERE t.kind = 'expense' AND u.deleted_at IS NULL
          AND coalesce((u.preferences ->> 'share_merchant_categories')::boolean, true)
        GROUP BY t.user_id, account_merchant_key(t.description), lower(c.name)
    ), votes AS (
        SELECT DISTINCT ON (user_id, merchant_key) user_id, merchant_key, category_name, n,
               sum(n) OVER (PARTITION BY user_id, merchant_key) AS total
        FROM chosen
        WHERE length(merchant_key) >= 3
          AND merchant_key !~ '[[:<:]](transfer|etransfer|interac|payment|deposit|withdrawal|atm|cheque|refund|payroll|paypal|venmo)[[:>:]]'
        ORDER BY user_id, merchant_key, n DESC, category_name
    ), tallied AS (
        SELECT merchant_key, category_name, count(*) AS people,
               sum(count(*)) OVER (PARTITION BY merchant_key) AS voters
        FROM votes WHERE n >= 0.8 * total
        GROUP BY merchant_key, category_name
    )
    INSERT INTO merchant_categories (id, merchant_key, category_name, people, computed_at)
        SELECT gen_random_uuid(), merchant_key, category_name, people, now() AT TIME ZONE 'utc'
        FROM tallied WHERE people >= 3 AND people >= 0.75 * voters;
    GET DIAGNOSTICS written = ROW_COUNT;
    RETURN written;
END $$;

-- The agreed category name for each merchant key asked about, to anyone signed
-- in, at the floor (checked again). Never a count.
CREATE OR REPLACE FUNCTION account_merchant_categories(p_keys text[])
    RETURNS TABLE(merchant_key text, category_name text)
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
    AS $$ SELECT m.merchant_key::text, m.category_name::text
          FROM merchant_categories m
          WHERE account_current_user() IS NOT NULL AND m.people >= 3 AND m.merchant_key = ANY(p_keys) $$;

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
REVOKE ALL ON FUNCTION account_grade_distribution(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_term_counted(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_recount_course_intel() FROM PUBLIC;
REVOKE ALL ON FUNCTION account_course_intel(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_recount_office_hours() FROM PUBLIC;
REVOKE ALL ON FUNCTION account_office_hours(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_employer_key(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_recount_salaries() FROM PUBLIC;
REVOKE ALL ON FUNCTION account_salary_figures() FROM PUBLIC;
REVOKE ALL ON FUNCTION account_merchant_key(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION account_recount_merchant_categories() FROM PUBLIC;
REVOKE ALL ON FUNCTION account_merchant_categories(text[]) FROM PUBLIC;
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
"""Script creating or replacing every function in `FUNCTIONS`, then locking them down.

Each definer function loses `EXECUTE` for `PUBLIC`, then for every other grantee but
its owner and `account_app`, which strips Supabase's default grants to anon and
authenticated. `grant_statements` grants `EXECUTE` back to the app role alone.
"""


def _owner_parent(table: Table) -> tuple[str, str, Table] | None:
    """Return the single foreign key that makes a table a child of an owned table.

    A candidate is a non-null column with a foreign key into a table that has a
    `user_id` column.

    Returns:
        (child column, parent column, parent table) when there is exactly one
        candidate; None when there are none or several.
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
    """Return whether a table is in `SHARED_READ_TABLES`, checking it has no owner.

    Args:
        table: A model table.

    Returns:
        True if the table is listed as shared-read.

    Raises:
        ValueError: If a listed table is `users`, has a `user_id` column or is a child
            of an owned table, since sharing it would show every user's rows to all.
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
    """Raise ValueError if `NO_DIRECT_WRITE_TABLES` names an unknown or shared table."""
    unknown = NO_DIRECT_WRITE_TABLES - set(Base.metadata.tables)
    if unknown:
        raise ValueError(f"NO_DIRECT_WRITE_TABLES names tables no model builds: {sorted(unknown)}")
    both = NO_DIRECT_WRITE_TABLES & SHARED_READ_TABLES
    if both:
        raise ValueError(f"Tables on both lists: {sorted(both)}")


def is_sealed(table: Table) -> bool:
    """Return whether a table is in `SEALED_TABLES`, checking it has no owner.

    Args:
        table: A model table.

    Returns:
        True if the table is listed as sealed.

    Raises:
        ValueError: If a listed table is `users`, has a `user_id` column or is a child
            of an owned table, since sealing it would hide the owner's own rows.
    """
    if table.name not in SEALED_TABLES:
        return False
    if table.name == "users" or "user_id" in table.columns or _owner_parent(table) is not None:
        raise ValueError(f"Table {table.name!r} is listed in SEALED_TABLES but has an owner.")
    return True


def _check_sealed_list() -> None:
    """Raise ValueError if `SEALED_TABLES` names an unknown or doubly listed table."""
    unknown = SEALED_TABLES - set(Base.metadata.tables)
    if unknown:
        raise ValueError(f"SEALED_TABLES names tables no model builds: {sorted(unknown)}")
    both = SEALED_TABLES & (SHARED_READ_TABLES | NO_DIRECT_WRITE_TABLES)
    if both:
        raise ValueError(f"Tables on both lists: {sorted(both)}")


def _check_shared_list() -> None:
    """Raise ValueError if `SHARED_READ_TABLES` names a table no model builds."""
    unknown = SHARED_READ_TABLES - set(Base.metadata.tables)
    if unknown:
        raise ValueError(f"SHARED_READ_TABLES names tables no model builds: {sorted(unknown)}")


def owner_predicate(table: Table) -> str:
    """Return the SQL condition under which a row of a table belongs to the acting user.

    Args:
        table: A model table that is neither shared-read nor sealed.

    Returns:
        `id = account_current_user()` for `users`, `user_id = account_current_user()`
        for a per-user table, or an `EXISTS` subquery requiring the parent row's
        `user_id` to be the acting user for a child table.

    Raises:
        ValueError: If the table has no `user_id` and no single owning parent.
    """
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
    """Return the SQL that enables row security and creates every table's policy.

    Each model table gets `ENABLE ROW LEVEL SECURITY` and loses any existing `POLICY`.
    A sealed table then gets no policy at all, so no role but the owner sees a row. A
    shared-read table gets a `FOR SELECT` policy for `APP_ROLE` admitting any
    identified caller (`SHARED_PREDICATE`). Every other table, no-direct-write ones
    included, gets a `FOR ALL` policy for `APP_ROLE` with `owner_predicate` as both
    `USING` and `WITH CHECK`; other roles get none, so they see nothing.

    Returns:
        The statements in table dependency order; running them again is harmless.

    Raises:
        ValueError: If a table list names an unknown or doubly listed table, a listed
            table has an owner, or a table fits no kind.

    Note:
        Row security is enabled but never forced, so the tables' owner, and every
        definer function it owns, is not bound by these policies.
    """
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
    """Return the SQL that sets exactly what `APP_ROLE` may do: data, never schema.

    In order: `USAGE` on schema `public`. For each root, per-user and child table,
    every privilege revoked from all roles but the owner and the app role, then
    `SELECT, INSERT, UPDATE, DELETE` granted to the app role, except that
    `NO_DIRECT_WRITE_TABLES` instead lose `INSERT, UPDATE, TRUNCATE` and get only
    `SELECT, DELETE`. Sealed tables lose every privilege for every role, the app role's
    included; shared-read tables keep `SELECT` alone. Last come `USAGE, SELECT` on all
    sequences and `EXECUTE` on each function in `FUNCTIONS`.

    Returns:
        Statements naming model tables one at a time, so a table no model builds is
        never granted.

    Raises:
        ValueError: If a shared-read or sealed table has an owner.
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
        "GRANT EXECUTE ON FUNCTION account_grade_distribution(text) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_recount_course_intel() TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_course_intel(text) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_recount_office_hours() TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_office_hours(text) TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_recount_salaries() TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_salary_figures() TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_recount_merchant_categories() TO " + APP_ROLE,
        "GRANT EXECUTE ON FUNCTION account_merchant_categories(text[]) TO " + APP_ROLE,
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
    """Return SQL leaving a shared-read table readable by the app role alone.

    It revokes everything from all roles but the owner and the app role, revokes
    `WRITE_PRIVILEGES` from the app role, then grants it `SELECT`.
    """
    name = table.name
    return [
        *_revoke_from_others(name),
        f"REVOKE {WRITE_PRIVILEGES} ON {name} FROM {APP_ROLE}",
        f"GRANT SELECT ON {name} TO {APP_ROLE}",
    ]


def _revoke_from_others(name: str) -> list[str]:
    """Return SQL that strips every role but the owner and the app role from a table.

    It revokes from `PUBLIC`, then walks the table's ACL and revokes from each named
    grantee, which removes Supabase's default grants (TRUNCATE included, which row
    security does not cover).
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
    """Return SQL revoking every privilege on a sealed table except its owner's.

    `PUBLIC`, each named grantee and `APP_ROLE` all lose everything.
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
    LOOP
        EXECUTE format('REVOKE ALL ON public.{name} FROM %I', r.rolname);
    END LOOP;
END $$""",
        f"REVOKE ALL ON {name} FROM {APP_ROLE}",
    ]


def install(engine: Engine) -> bool:
    """Install the definer functions, plus policies and grants once the app role exists.

    Runs `FUNCTION_SQL`, then `policy_statements()` and `grant_statements()`, in one
    transaction, so a failure leaves the database as it was. Until `APP_ROLE` exists
    only the functions are installed, which is all the API needs to run as the owner.

    Args:
        engine: Engine connected as the tables' owner.

    Returns:
        True on Postgres, whether or not the role existed; False on any other database,
        where nothing is done.

    Raises:
        ValueError: If a table fits no row-security kind or a table list is wrong;
            nothing is committed.

    Note:
        Idempotent: functions are replaced, and every policy is dropped and recreated.
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
    """Return the whole installation as one SQL script, for review or the SQL editor.

    Returns:
        `FUNCTION_SQL` followed by every policy and grant statement, each ending in a
        semicolon, whether or not the app role exists yet.

    Raises:
        ValueError: As `policy_statements` does.
    """
    parts = [FUNCTION_SQL.strip()]
    parts += [s + ";" for s in policy_statements()]
    parts += [s + ";" for s in grant_statements()]
    return "\n".join(parts) + "\n"


if __name__ == "__main__":
    print(render_sql())
