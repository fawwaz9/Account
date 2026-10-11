# Phase 2 — production runbook

Written for: you. **Part A is deployed (2026-10-07).** Each step is written as
the work it deploys is built, per the template. Part A deploys as one batch once its
items are built and you say "deploy". The steps below grow with each item. A new
role for automatic approval (D5) would come later.

## 0. Send the calendar request (yours; changes nothing in the app)

The draft and who to send it to are in `Ideas/overhaul/calender-request.md`.
Tell me when UBC answers.

## The Part A batch: DEPLOYED 2026-10-07 (`11925ac`, `account-api-00039-vmr`)

Done in order: the backup (run 37556774219), step 1 (yours), then
`deploy.run.sh all`. The schema gate passed, reporting row-level security on
for 38 of 38 tables. The 6 new routes answer 401 against a 404 control. The
live site matches the build (29 files). **Check 1 passed** (2026-10-07, yours): both
catalogue tables were empty after the schema step, so nothing got in during
the D9 window. **Still to confirm:** check 2 (only `account_app | SELECT` on
the catalogue).

| What | Commits | Schema change |
|---|---|---|
| Items 1–2: the shared-read policy and the catalogue tables (D9, D10) | on `phase2` | **New tables `catalogue_courses`, `catalogue_prerequisites`**; their read-only policy and grants |
| Item 3: linking your courses to the catalogue (D11) | on `phase2` | **New columns `courses.catalogue_course_id` (UUID), `courses.catalogue_unlinked` (boolean, default false)** |
| Items 4 and 7: your own prerequisites, met or not (D12) | on `phase2` | **New table `prerequisite_proposals`** (per-user; the usual policy) |
| Item 6: the owner review script (D13) | on `phase2` | None. A script you run, step R below |
| Item 5: the syllabus reader picks up prerequisites (D14) | on `phase2` | None |

### 1. Apply the schema (adds two tables; nothing is dropped or rewritten)

Pre-flight is the same as Phase 1's: a backup, via **Backup database** → Run
workflow. Then, from `Application/backend` on the `phase2` branch:

```sh
git checkout phase2
set -a; source ../.env; set +a
DATABASE_URL="$SUPABASE_DATABASE_URL" .venv/bin/python -m app._database.schema
```

**What this adds:**
- **`catalogue_courses`,** with its unique key on (campus, subject, number) and
  its campus check.
- **`catalogue_prerequisites`,** with its unique key on (course, kind, session),
  its checks (including "only a `ubc-calendar` row carries the source text"),
  and an index on the course.
- **For both:** row security on, and a `SELECT`-only policy for `account_app`.
  `account_app` is granted `SELECT` alone. **Every other grantee is revoked,**
  which takes away Supabase's default grants to `anon` and `authenticated`.
- **`prerequisite_proposals`,** with indexes on `user_id` and `course_id`, its
  unique key on (course, kind) and its checks. It is per-user, so it gets the
  usual row policy (`user_id = account_current_user()`) and the usual four
  grants.
- **Two columns on `courses`:** `ALTER TABLE courses ADD COLUMN catalogue_course_id UUID`
  and `... ADD COLUMN catalogue_unlinked BOOLEAN NOT NULL DEFAULT false`. Existing
  rows read null and false, so every course starts on automatic matching.
  Nothing is backfilled.
- **Install re-runs for every table,** as it did in Phase 1, so the existing
  policies and grants are re-asserted unchanged.

**The live app doesn't notice.** Nothing in the running API reads these tables.

**Verify, in the SQL editor:**
1. **Both tables are empty.** This should return `0 | 0`. It covers the D9
   window, the seconds between creating a table and locking it:

   ```sql
   SELECT (SELECT count(*) FROM catalogue_courses), (SELECT count(*) FROM catalogue_prerequisites);
   ```

2. **Who may touch them.** This should return exactly two rows, both `account_app`
   and `SELECT`. No `anon`, no `authenticated`, no `PUBLIC`:

   ```sql
   SELECT table_name, grantee, privilege_type FROM information_schema.role_table_grants
   WHERE table_name IN ('catalogue_courses', 'catalogue_prerequisites')
     AND grantee <> (SELECT tableowner FROM pg_tables WHERE tablename = 'catalogue_courses')
   ORDER BY 1, 2, 3;
   ```

3. **The policies.** This should return two rows, each `{account_app}` and
   `SELECT`:

   ```sql
   SELECT tablename, roles, cmd FROM pg_policies
   WHERE tablename IN ('catalogue_courses', 'catalogue_prerequisites');
   ```

   The same query for `prerequisite_proposals` should return `{account_app}`
   and `ALL`, the per-user shape.

4. **The course columns.** This should return `uuid` and `boolean`:

   ```sql
   SELECT column_name, data_type FROM information_schema.columns
   WHERE table_name = 'courses' AND column_name IN ('catalogue_course_id', 'catalogue_unlinked');
   ```

5. **Negative control.** Run the query from check 2 against an existing per-user
   table, `courses`. It still shows `account_app` with all four verbs, so the
   check above is telling `SELECT`-only apart from the usual grant.

**Undo:** not needed. The tables are new, and the old API never reads them.
Dropping them would also be safe while they are empty.

### R. Reviewing proposals (yours, whenever you like; only this writes the shared catalogue)

This isn't a deploy step. Run it once the batch is live and people have
entered prerequisites. From `Application/backend`:

```sh
set -a; source ../.env; set +a
CATALOGUE_REVIEW_URL="$SUPABASE_DATABASE_URL" .venv/bin/python scripts/catalogue_review.py
```

**What it does:**
- **It lists pending proposals** as groups, each with an 8-character id and a
  count of accounts. It prints no names, ids, notes or wording.
- **To share a rule:** `... scripts/catalogue_review.py approve <id>`. Add
  `--session 2026W` when it asks, `--campus UBCV` for a code with no campus
  suffix, and `--replace` to overwrite an existing rule.
- **To decline one:** `... scripts/catalogue_review.py reject <id>`. It keeps
  applying to whoever proposed it.

**It must connect as the tables' owner,** the same URL the schema step uses.
It refuses `account_app`, and any role that can't write the catalogue. Check
that by pointing it at the API's own URL once: it must print "Connected as
account_app ... Review runs as the tables' owner" and exit.

**Verify an approval:** open the course page of a course with that code. The
Prerequisites panel shows "Shared, reviewed".

**Undo an approval:** delete the row in the SQL editor. It is instant, and the
proposals' status stays "accepted":

```sql
DELETE FROM catalogue_prerequisites WHERE id = '<row id>';
```

## The 12a and 14 batch: the rate limiter per caller (D18), shifts near exams and the tax packet (D21). DEPLOYED 2026-10-08 (`867938d`, `account-api-00040-w6n`); switch on, checked 2026-10-10

| What | Commits | Schema change |
|---|---|---|
| Item 12a: `TRUSTED_PROXY_HOPS` and `client_address.py` | on `phase2` | None |
| Item 14: shift conflicts, the tax packet, the exam-buffer preference | on `phase2` | None (the preference lives in the existing JSON) |

### 1. Deploy the API (reversible; the live app doesn't notice)

```sh
git checkout phase2
./Application/deploy.run.sh all
```

With `TRUSTED_PROXY_HOPS` unset, the new code ignores `X-Forwarded-For`, so
throttling behaves exactly as before. The frontend gains:
- the "Shifts near exams" panel, on Jobs and Calendar
- the tax packet, on Jobs
- "Keep clear before an exam", in Settings, under Calendar

**Also verify:** `/api/jobs/<id>/shift-conflicts` and
`/api/jobs/<id>/tax-packet?calendar_year=2026` answer 401 against a 404
control. Then open Jobs: the tax packet shows this year's recorded cheques.

**Verify, the negative control first.** Send one sign-in with a forged header:

```sh
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://account-api-210502804146.us-west1.run.app/api/auth/login \
  -H 'Content-Type: application/json' -H 'X-Forwarded-For: 203.0.113.7' \
  -d '{"email":"xff-check@example.invalid","password":"not-the-password"}'
```

It answers `401`. Then read the audit line:

```sh
gcloud logging read 'resource.labels.service_name="account-api" AND textPayload:"xff-check@example.invalid"' \
  --project account-504419 --limit 1 --format='value(textPayload)'
```

It ends `client=169.254...`, the platform's proxy. That's today's shared
budget.

**Undo:** the previous revision, per `Ideas/ROLLBACK.md`.

**Result, 2026-10-08:** the two routes and the six partner routes answer 401 against
a 404 control. The negative control answered 401 and logged
`client=169.254.169.126`, so the forged `203.0.113.7` was ignored.

### 2. Flip the switch (yours: a Cloud Run setting; instant to undo)

```sh
gcloud run services update account-api --region us-west1 --project account-504419 \
  --update-env-vars TRUSTED_PROXY_HOPS=1
```

This makes a new revision with the same image. Later deploys keep the
setting, because `gcloud run deploy --image` leaves environment variables
alone.

**Verify.** Send the same request as in step 1, then read both the audit line
and Cloud Run's own record of it:

```sh
gcloud logging read 'resource.labels.service_name="account-api" AND textPayload:"xff-check@example.invalid"' \
  --project account-504419 --limit 1 --format='value(textPayload)'
gcloud logging read 'resource.labels.service_name="account-api" AND httpRequest.requestUrl:"/api/auth/login"' \
  --project account-504419 --limit 1 --format='value(httpRequest.remoteIp)'
```

**What the result means:**
- **Pass:** the `client=` in the first equals the `remoteIp` in the second.
  That is your own address. It is neither `203.0.113.7` nor `169.254…`.
- **`client=203.0.113.7`:** the switch is reading the forgeable end. Undo it
  at once (below). The code is wrong, and I need to know.
- **`client=` is a Google address** (`35.191…` or `130.211…`): the front end
  appends a second entry. Set `TRUSTED_PROXY_HOPS=2` and check again.

**Undo:** instant.

```sh
gcloud run services update account-api --region us-west1 --project account-504419 \
  --remove-env-vars TRUSTED_PROXY_HOPS
```

**Result, 2026-10-10:** on since `00041-r88`. The forged request's `client=`
equalled Cloud Run's `remoteIp`, the caller's real address: a pass.

## The item 10 batch: accountability partners and invite links (D22). DEPLOYED 2026-10-08 (`867938d`, `account-api-00040-w6n`)

| What | Commits | Schema change |
|---|---|---|
| Item 10: invites, partnerships, four definer functions | on `phase2` | **New tables `invites`, `partnerships`; four new functions** |

Runs after the 12a and 14 batch, or together with it. Same order as Part A:
backup, schema (yours), then `deploy.run.sh all`.

### 1. Apply the schema (adds two tables and four functions; nothing is dropped)

```sh
git checkout phase2
cd Application/backend
set -a; source ../.env; set +a
DATABASE_URL="$SUPABASE_DATABASE_URL" .venv/bin/python -m app._database.schema
```

**What this adds:**
- **`invites`:** per-user, with a unique token hash.
- **`partnerships`:** per-user, with a database-level `ON DELETE CASCADE` on
  the partner column.
- **The four functions:** `account_invite_preview`,
  `account_accept_partner_invite`, `account_end_partnership` and
  `account_partner_figures`. Each is revoked from everyone but `account_app`,
  including Supabase's by-name grants.

**Verify, in the SQL editor:**
1. **Only the API's role can call the new functions.** This should return
   four rows, each `{postgres=X/postgres,account_app=X/postgres}` or similar.
   `anon` and `authenticated` must not appear:

   ```sql
   SELECT p.proname, p.proacl FROM pg_proc p
   WHERE p.proname IN ('account_invite_preview', 'account_accept_partner_invite',
                       'account_end_partnership', 'account_partner_figures');
   ```

2. **Both tables have the per-user policy.** This should return two rows,
   each `{account_app}` and `ALL`:

   ```sql
   SELECT tablename, roles, cmd FROM pg_policies WHERE tablename IN ('invites', 'partnerships');
   ```

The deploy's schema gate also refuses to deploy if any of the four functions
is missing.

**Undo:** not needed. The tables are new, and the old API never calls the
functions.

**Result, 2026-10-08:** both checks matched: four functions callable by
`postgres` and `account_app` only, and two `{account_app} | ALL` policies.
The deploy's gate reported row-level security on for 40 of 40 tables.
Part A's grant check 2 also passed: two rows, `account_app | SELECT`.

### 2. Before anyone uses it (yours)

Whoever you invite must be able to sign in. Until open signup (D19), add
their address to `ALLOWED_SIGNUP_EMAILS` on Cloud Run.

## The item 9a batch: shared tasks (D23). DEPLOYED 2026-10-10 (`97a3858`, `account-api-00043-s9h`)

| What | Commits | Schema change |
|---|---|---|
| Item 9a: task links, members, six definer functions | on `phase2` | **New tables `task_members`, `task_invites`; six new functions; a read-and-delete grant on `task_members`** |

Same order as before: backup, schema (yours), then `deploy.run.sh all`.
Nothing existing is altered: `tasks`, `events` and `invites` keep their shape
and their policies.

### 1. Apply the schema (adds two tables and six functions; nothing is dropped)

```sh
git checkout phase2
cd Application/backend
set -a; source ../.env; set +a
DATABASE_URL="$SUPABASE_DATABASE_URL" .venv/bin/python -m app._database.schema
```

**What this adds:**
- **`task_members`:** who is on a task, hung under the task. The task's
  owner alone can see or delete these rows, and the API's role can't insert
  or update them at all.
- **`task_invites`:** a task's link, hung under the task, with a unique token
  hash.
- **The six functions:** `account_task_invite_preview`,
  `account_accept_task_invite`, `account_shared_tasks`,
  `account_set_shared_task_done`, `account_edit_shared_task` and
  `account_leave_shared_task`. Each is revoked from everyone but
  `account_app`.

**Verify, in the SQL editor:**
1. **Only the API's role can call the new functions.** This should return
   six rows, each `{postgres=X/postgres,account_app=X/postgres}`, with no
   `anon` or `authenticated`:

   ```sql
   SELECT proname, proacl FROM pg_proc
   WHERE proname IN ('account_task_invite_preview', 'account_accept_task_invite',
                     'account_shared_tasks', 'account_set_shared_task_done',
                     'account_edit_shared_task', 'account_leave_shared_task');
   ```

2. **Both tables have the per-user policy.** This should return two rows,
   each `{account_app}` and `ALL`:

   ```sql
   SELECT tablename, roles, cmd FROM pg_policies WHERE tablename IN ('task_members', 'task_invites');
   ```

3. **The API's role can read and delete memberships, never write them.** This
   should return exactly two rows for `task_members`, `DELETE` and `SELECT`,
   and four for `task_invites`:

   ```sql
   SELECT table_name, privilege_type FROM information_schema.role_table_grants
   WHERE grantee = 'account_app' AND table_name IN ('task_members', 'task_invites')
   ORDER BY 1, 2;
   ```

**Undo:** not needed. The tables are new, and the old API never calls the
functions.

### 2. Deploy (after the schema step and its checks)

```sh
git checkout phase2
./Application/deploy.run.sh all
```

The deploy's schema gate refuses if either table or any of the six
functions is missing.

**Verify:** the 9 new routes answer 401 against a 404 control:
- `GET`, `/api/tasks/<id>/tasks/<task>/sharing`
- `POST` and `DELETE`, `/api/tasks/<id>/tasks/<task>/sharing/link`
- `DELETE`, `/api/tasks/<id>/tasks/<task>/sharing/members/<member>`
- `GET`, `/api/tasks/<id>/shared-tasks`
- `POST`, `/api/tasks/<id>/shared-tasks/invites/preview` and `/accept`
- `PATCH` and `DELETE`, `/api/tasks/<id>/shared-tasks/<task>`

Then open one of your own one-off tasks: the editor has a Share section.

**Rollback:** both halves together, per `Ideas/ROLLBACK.md`. The schema
stays: the older API never reads either table. Memberships and links stay
stored for a redeploy.

### 3. Before anyone uses it (yours)

Whoever you share with must be able to sign in. Until open signup (D19),
add them with `./invite.sh their@address`.

**Result, 2026-10-10:** the three read-backs matched (`task_members`: SELECT
and DELETE only). The gate reported row-level security on for 42 of 42
tables; the 9 routes answer 401 against two 404 controls; no errors in the
logs; the live site matches the build (33 files).

## The item 9b batch: shared events (D24). DEPLOYED 2026-10-11 (`f884f69`, `account-api-00044-vn2`)

| What | Commits | Schema change |
|---|---|---|
| Item 9b: event links, members, four definer functions | on `phase2` | **New tables `event_members`, `event_invites`; four new functions; a read-and-delete grant on `event_members`** |

Same order as 9a: backup, schema (yours), then `deploy.run.sh all`. Nothing
existing is altered.

### 1. Apply the schema (adds two tables and four functions; nothing is dropped)

```sh
git checkout phase2
cd Application/backend
set -a; source ../.env; set +a
DATABASE_URL="$SUPABASE_DATABASE_URL" .venv/bin/python -m app._database.schema
```

**Verify, in the SQL editor:**
1. **Only the API's role can call the new functions.** This should return
   four rows, each `{postgres=X/postgres,account_app=X/postgres}`:

   ```sql
   SELECT proname, proacl FROM pg_proc
   WHERE proname IN ('account_event_invite_preview', 'account_accept_event_invite',
                     'account_shared_events', 'account_leave_shared_event');
   ```

2. **Both tables have the per-user policy.** This should return two rows,
   each `{account_app}` and `ALL`:

   ```sql
   SELECT tablename, roles, cmd FROM pg_policies WHERE tablename IN ('event_members', 'event_invites');
   ```

3. **The API's role can read and delete event memberships, never write
   them.** This should return two rows for `event_members` (`DELETE`,
   `SELECT`) and four for `event_invites`:

   ```sql
   SELECT table_name, privilege_type FROM information_schema.role_table_grants
   WHERE grantee = 'account_app' AND table_name IN ('event_invites', 'event_members')
   ORDER BY 1, 2;
   ```

**Undo:** not needed. The tables are new, and the old API never calls the
functions.

### 2. Deploy

```sh
./Application/deploy.run.sh all
```

**Verify:** the 8 new routes answer 401 against a 404 control: `GET`, `POST`
and `DELETE` on `/api/calendar/<id>/events/<event>/sharing` (and `/link`,
`/members/<member>`); `GET /api/calendar/<id>/shared-events`; `POST`
`/shared-events/invites/preview` and `/accept`; `DELETE
/shared-events/<event>`. Then open one of your own one-off events: the editor
has a Share section.

**Rollback:** both halves together, per `Ideas/ROLLBACK.md`. The schema stays.

**Result, 2026-10-11:** the three read-backs matched (`event_members`: SELECT
and DELETE only). The gate reported row-level security on for 44 of 44
tables; the 8 routes answer 401 against two 404 controls; no errors in the
logs; the live site matches the build (34 files).

## The item 13 batch: end-of-term reviews and the sealed grade count (D25). NOT YET RUN

| What | Commits | Schema change |
|---|---|---|
| Item 13: term reviews, the sealed counts table, the recount function | on `phase2` | **New tables `term_reviews`, `grade_distributions` (sealed); one new function** |

Same order as before: backup, schema (yours), then `deploy.run.sh all`.
Nothing existing is altered.

### 1. Apply the schema (adds two tables and one function; nothing is dropped)

```sh
git checkout phase2
cd Application/backend
set -a; source ../.env; set +a
DATABASE_URL="$SUPABASE_DATABASE_URL" .venv/bin/python -m app._database.schema
```

**Verify, in the SQL editor:**
1. **Nobody but the owner can touch the counts.** This should return no rows
   at all: not `account_app`, not `anon`, not `authenticated`:

   ```sql
   SELECT grantee, privilege_type FROM information_schema.role_table_grants
   WHERE table_name = 'grade_distributions'
     AND grantee <> (SELECT tableowner FROM pg_tables WHERE tablename = 'grade_distributions');
   ```

2. **The counts have row security and no policy; reviews have the per-user
   one.** The first should return `t`; the second one row, `{account_app}`
   and `ALL`:

   ```sql
   SELECT relrowsecurity FROM pg_class WHERE relname = 'grade_distributions';
   SELECT tablename, roles, cmd FROM pg_policies WHERE tablename IN ('term_reviews', 'grade_distributions');
   ```

3. **Only the API's role can run the recount:**

   ```sql
   SELECT proname, proacl FROM pg_proc WHERE proname = 'account_recount_grade_distributions';
   ```

   One row, `{postgres=X/postgres,account_app=X/postgres}`.

**Undo:** not needed. The tables are new, and the old API never reads them.

### 2. Deploy

```sh
./Application/deploy.run.sh all
```

**Verify:** the 4 review routes answer 401 against a 404 control (`GET
/api/grades/<id>/term-reviews`, `PUT` and `DELETE`
`/term-reviews/<course>`, `POST /term-reviews/<course>/skip`), and `POST
/api/internal/distributions/recount` answers 403 without the secret.

### 3. The daily recount (yours, whenever you like; nothing depends on it before Phase 3)

```sh
gcloud scheduler jobs create http account-grade-recount --location=us-west1 --project=account-504419 \
  --schedule="30 9 * * *" --time-zone="UTC" --http-method=POST \
  --uri="https://account-api-210502804146.us-west1.run.app/api/internal/distributions/recount" \
  --headers="X-Cron-Secret=$(gcloud secrets versions access latest --secret=cron-secret --project=account-504419)"
```

The second of Cloud Scheduler's three free jobs. Daily, so the counts never
change in step with one person's choice.

**Verify:** `gcloud scheduler jobs run account-grade-recount --location=us-west1
--project=account-504419`, then the job's last attempt shows `200`. The answer
is a number of rows, never their contents.

**Undo:** `gcloud scheduler jobs delete account-grade-recount --location=us-west1
--project=account-504419`.

## The item 11 batch: teams (D26). NOT YET RUN

| What | Commits | Schema change |
|---|---|---|
| Item 11: teams, team links, members, games, eleven definer functions | on `phase2` | **New tables `teams`, `team_members`, `team_invites`, `games`; eleven new functions; read-and-delete grants on `team_members` and `games`** |

Ships with item 13 in one go: see **Both together** below.

**Verify after the schema step, in the SQL editor:**
1. **Only the API's role can call the new functions.** This should return
   eleven rows, each `{postgres=X/postgres,account_app=X/postgres}`:

   ```sql
   SELECT proname, proacl FROM pg_proc
   WHERE proname IN ('account_on_team', 'account_team_invite_preview', 'account_accept_team_invite',
                     'account_my_teams', 'account_team_games', 'account_record_team_game',
                     'account_confirm_team_game', 'account_dispute_team_game',
                     'account_correct_team_game', 'account_delete_team_game', 'account_leave_team');
   ```

2. **All four tables have the per-user policy.** Four rows, each
   `{account_app}` and `ALL`:

   ```sql
   SELECT tablename, roles, cmd FROM pg_policies
   WHERE tablename IN ('teams', 'team_members', 'team_invites', 'games');
   ```

3. **Memberships and games are read and deleted, never written, by the API's
   role.** `games` and `team_members` should each show only `DELETE` and
   `SELECT`; `teams` and `team_invites` all four:

   ```sql
   SELECT table_name, privilege_type FROM information_schema.role_table_grants
   WHERE grantee = 'account_app' AND table_name IN ('teams', 'team_members', 'team_invites', 'games')
   ORDER BY 1, 2;
   ```

**After the deploy, verify:** the 16 team routes answer 401 against a 404
control (`/api/teams/<id>` and everything beneath it), then open **Fitness** in
the sidebar (or press G then F), make a team, and record a game.

**Rollback:** both halves together, per `Ideas/ROLLBACK.md`. The schema
stays: the older API never reads the new tables.

## Both together: items 13 and 11, one morning (yours, then mine)

One backup, one schema run (it creates both items' tables and functions at
once), the read-backs, one deploy.

1. **Say "deploy".** I take the backup and confirm it.
2. **The schema step**, as before:

   ```sh
   cd ~/VS_Code/Account/Application/backend
   git checkout phase2
   set -a; source ../.env; set +a
   DATABASE_URL="$SUPABASE_DATABASE_URL" .venv/bin/python -m app._database.schema
   ```

3. **The read-backs:** item 13's three (the counts table has no grants at all
   and no policy; reviews have the per-user policy; the recount callable by
   `account_app` only), and item 11's three above. Screenshots are fine.
4. **I run `deploy.run.sh all`** and verify both batches' routes against a 404
   control, the logs, and the live site against the build.
5. **Optional, any time:** item 13's daily recount job (one `gcloud` line, in
   the item 13 section). Nothing depends on it before Phase 3.

Anyone you want on a team must be able to sign in: `./invite.sh their@address`.

