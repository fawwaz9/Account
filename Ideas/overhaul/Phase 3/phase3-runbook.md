# Phase 3 — runbook

Written for: you, running Phase 3's production steps in order. Each step says
what it changes, the exact commands, how to verify it with a negative control,
and how to undo it. Follows `Ideas/overhaul/template.md`.

The first batch, below, carries the job application tracker (item 1) and pay
on set days of the month (a `next.md` item, decided 2026-10-03), so one backup
and one schema run cover both.

## Done before Phase 3 opened

- **The daily grade recount** (Phase 2 item 13's optional step), created
  2026-10-12: `account-grade-recount`, 09:30 UTC daily. A test run returned
  `200` from `Google-Cloud-Scheduler` in the API's request log. It feeds item
  3. **Undo:** `gcloud scheduler jobs delete account-grade-recount
  --location=us-west1 --project=account-504419` (instant).

## Batch 1: the application tracker (item 1, D2–D5), pay on set days of the month, and D6. DEPLOYED 2026-10-13 (`72bb9f2`, `account-api-00046-5dl`)

| What | Commits | Schema change |
|---|---|---|
| Item 1: the tracker | `e11ddbd` on `phase3` | **New tables `job_applications`, `application_steps`** (a per-user table and its child; existing row-security kinds) |
| D6: no role but the API's keeps a grant | on `phase3` | **Grants only:** every model table loses `anon`, `authenticated` and `service_role`. No data, no columns |
| Pay on set days of the month | `682da15` on `phase3` (cherry-picked from `76c3a5e`) | **Four columns on `jobs`:** `pay_month_days`, `pay_last_day` (not null, default false), `pay_nth_weekdays`, `pay_weekend`. Nothing is backfilled; every job keeps paying by its rule |

Same order as Phase 2: backup, schema (yours), read-backs, then
`deploy.run.sh all`. Nothing existing is altered or dropped. Rehearsed
2026-10-12 on a throwaway Postgres 17: with the four columns and both tables
dropped, the schema command put them all back, with the policy and grants
below.

### 1. Apply the schema (two new tables, four new columns; nothing dropped)

```sh
cd ~/VS_Code/Account/Application/backend
git checkout phase3
set -a; source ../.env; set +a
DATABASE_URL="$SUPABASE_DATABASE_URL" .venv/bin/python -m app._database.schema
```

**Verify, in the SQL editor:**

A. **Both tables have row security, with the per-user policy for the API's role
only.** Two rows, each `{account_app}` and `ALL`:

```sql
SELECT tablename, roles, cmd FROM pg_policies
WHERE tablename IN ('job_applications', 'application_steps') ORDER BY 1;
```

B. **Only the API's role has grants, and only the ordinary four.** Two rows, each
`account_app` with `DELETE,INSERT,SELECT,UPDATE`. No `anon`, no
`authenticated`, no `service_role`.

> **First run, 2026-10-12: did not match.** `anon`, `authenticated` and
> `service_role` held every privilege, as they do on every per-user table
> (D6). Fixed in the install; re-run the schema step (same command), then
> this check, and B2 below.

```sql
SELECT table_name, grantee, string_agg(privilege_type, ',' ORDER BY privilege_type)
FROM information_schema.role_table_grants
WHERE table_name IN ('job_applications', 'application_steps')
  AND grantee <> (SELECT tableowner FROM pg_tables WHERE tablename = table_name)
GROUP BY 1, 2 ORDER BY 1, 2;
```

B2. **No role but the API's has a grant on any model table** (D6). Rows for
`category_budgets` only, if any: the empty orphan from 2026-09-24, not a model
table, so the install leaves it alone (ROLLBACK.md, "Two orphaned schema
objects"). Anything else is a mismatch:

```sql
SELECT DISTINCT table_name, grantee FROM information_schema.role_table_grants
WHERE table_schema = 'public'
  AND grantee IN ('anon', 'authenticated', 'service_role', 'PUBLIC')
ORDER BY 1, 2;
```

C. **The pay columns are there.** Four rows; `pay_last_day` is `NO` and `false`:

```sql
SELECT column_name, is_nullable, column_default FROM information_schema.columns
WHERE table_name = 'jobs'
  AND column_name IN ('pay_month_days', 'pay_last_day', 'pay_nth_weekdays', 'pay_weekend')
ORDER BY 1;
```

**Undo:** not needed. The tables and columns are new, and the old API never
reads them.

### 2. Deploy (mine, after the read-backs)

```sh
./Application/deploy.run.sh all --yes
```

**Verify:** the 7 tracker routes (`/api/jobs/<id>/applications`,
`/applications/stats`, `/applications/<id>`, `/applications/<id>/steps`,
`/applications/<id>/steps/<step>`) answer 401 against a 404 control; the gate
reports row-level security on for 52 of 52 tables; no errors in the new
revision's logs; the live site matches the build.

**Rollback:** both halves together. Cloud Run to `account-api-00045-hp9`,
Pages to the `d638bcf` deployment. The schema stays: the older API never reads
the new tables or columns. A job saved with days of the month would read as a
plain monthly rule on the older API until redeployed, and applications stay
stored.

**Result, 2026-10-13.** The schema step was run twice, the second time for D6.
- The backup before the second run held 53 tables and 1,166 rows.
- Read-backs A and C matched first time. B did not (D6); after the fix, B2
  showed only `category_budgets`, and B's first re-run pane was stale. Its real
  re-run matched.
- The gate reported row-level security on for 52 of 52 tables.
- Health ok. The 7 routes answer 401 against two 404 controls.
- No errors in the new revision's logs. All nine settings carried over.
- The live site matches the build (38 files).

## Batch 2: application seasons (D7). DEPLOYED 2026-10-14 (`e5d5eb6`, `account-api-00048-985`)

| What | Schema change |
|---|---|
| Seasons: named, month to month; the list, figures and Sankey filtered by one | **New table `application_seasons`** (per-user; existing row-security kind). Nothing altered |

Rehearsed 2026-10-13 on a throwaway Postgres with Supabase's default privileges
switched on, so the new table was granted to `anon`, `authenticated` and
`service_role` the moment it was made. The same schema run took those grants
back (D6), leaving `account_app` alone.

### 1. Apply the schema (one new table)

```sh
cd ~/VS_Code/Account/Application/backend
git checkout phase3 && git pull
set -a; source ../.env; set +a
DATABASE_URL="$SUPABASE_DATABASE_URL" .venv/bin/python -m app._database.schema
```

**Verify, in the SQL editor:**

A. **Row security, with the per-user policy for the API's role only.** One row,
`{account_app}` and `ALL`:

```sql
SELECT tablename, roles, cmd FROM pg_policies WHERE tablename = 'application_seasons';
```

B. **Only the API's role has grants.** One row, `account_app` with
`DELETE,INSERT,SELECT,UPDATE`:

```sql
SELECT grantee, string_agg(privilege_type, ',' ORDER BY privilege_type)
FROM information_schema.role_table_grants
WHERE table_name = 'application_seasons'
  AND grantee <> (SELECT tableowner FROM pg_tables WHERE tablename = 'application_seasons')
GROUP BY 1;
```

**Undo:** not needed. The table is new, and the current API never reads it.

### 2. Deploy (mine, after the read-backs and your go-ahead)

```sh
./Application/deploy.run.sh all --yes
```

**Verify:** the 4 season routes (`GET`/`POST /api/jobs/<id>/applications/seasons`,
`PUT`/`DELETE /applications/seasons/<season>`) and `?season_id=` on the list and
stats answer 401 against a 404 control; the gate reports row-level security on
for 53 of 53 tables; no errors in the logs; the live site matches the build.

**Rollback:** both halves together, Cloud Run to `account-api-00047-z5d`, Pages to
the `72bb9f2` deployment. The table stays; the older API never reads it.

**Result, 2026-10-14.**
- The backup held 54 tables and 1,571 rows.
- Read-backs A and B matched first time.
- The gate reported row-level security on for 53 of 53 tables.
- Health ok. The 6 season requests answer 401 against two 404 controls.
- No errors in the logs. Settings carried over.
- The live site matches the build (38 files).

## Batch 3: Part B, items 2-13 (D10-D13). DEPLOYED 2026-10-28

**Done.** Your schema run, then read-backs A, B and C matched exactly (19
tables with row security, the five sealed ones without a policy or a grant,
`account_app` the only grantee; the five team columns, both flags `NO` and
`false`). Then `deploy.run.sh all --yes` at `9b5a4bd`:
- The backup held 72 tables and 2,251 rows.
- The gate reported row-level security on for 72 of 72 tables, so every
  function was there (D).
- API `account-api-00049-smp`, digest-verified `sha256:0c63e2f9...`, serving
  100% since 2026-10-29 05:49 UTC. Health ok; all nine settings carried over.
- Six new routes answer 401 against two 404 controls (they answered 404 or 405
  on the old API); the recount door answers 403 without its secret.
- A manual run of `account-grade-recount` answered `200` from
  `Google-Cloud-Scheduler` in 0.45 s. The route doesn't log its body, so the
  six keys stand on the tests; a `200` means every rebuild ran, since any
  failure is a 500.
- No errors and no 5xx in the new revision's logs.
- Frontend `main` at `9b5a4bd`, matching a production build file by file (40
  files).

Built 2026-10-28 on `phase3` (`c501b90` to `06c6726`), every item in one schema
run. Nothing existing is altered or dropped except five new columns on `teams`.
The redocumentation commits (`4a65dcc`, `b0d143f`) ride in this batch, because
`phase3` was based on `redoc`.

| What | Schema change |
|---|---|
| Item 3: grade distributions shown | None: a read function on the sealed counts |
| Item 5: course intel | **New sealed table `course_intel`** |
| Item 11: office-hours radar | **New `office_hour_checkins`** (per-user), **sealed `office_hour_slots`** |
| Item 12: co-op salaries | **New `salary_shares`** (per-user), **sealed `salary_figures`** |
| Item 4: shared merchant map | **Sealed `merchant_categories`**; a preference, no column |
| Item 2: shared outlines | **New `outline_offers`** (per-user), **shared-read `shared_outlines`** |
| Item 13: gym buddy | **New `gym_buddies`** (per-user) |
| Items 6-7: exertion and goals | **New `activities`** (per-user); the goal is a preference |
| Items 8-9: boards and directory | **Five columns on `teams`** (`listed`, `level`, `area`, `looking_for_players`, `blurb`); **new `team_join_requests`** (per-user, no direct write); **sealed `campus_board`** |
| Item 10: clubs | **New `clubs`** (per-user), `club_members` (child, no direct write), `club_invites`, `club_posts`, `club_polls`, `club_events` (children), `club_votes` (per-user, no direct write) |

19 new tables in all, 53 → 72. 22 new definer functions (59 in `rls.FUNCTIONS`),
plus four plain helpers only they call (`account_term_counted`,
`account_employer_key`, `account_merchant_key`, `account_listed_team_ids`).

**The scheduler needs nothing new.** `account-grade-recount` already calls
`POST /api/internal/distributions/recount` daily at 09:30 UTC; that route now
runs every rebuild (`_database/recounts.py`) and answers with a count per
aggregate: `rows`, `course_intel`, `office_hours`, `salaries`,
`merchant_categories`, `campus_board`.

### 1. Apply the schema (19 new tables, five columns on `teams`; nothing dropped)

```sh
cd ~/VS_Code/Account/Application/backend
git checkout phase3 && git pull
set -a; source ../.env; set +a
DATABASE_URL="$SUPABASE_DATABASE_URL" .venv/bin/python -m app._database.schema
```

**Verify, in the SQL editor:**

A. **Every new table has row security; the sealed ones have no policy.** 19 rows.
`shared_outlines` shows `SELECT`; the five sealed tables show no policy (NULL);
every other row is `{account_app}` and `ALL`:

```sql
SELECT c.relname, c.relrowsecurity, p.cmd, p.roles
FROM pg_class c LEFT JOIN pg_policies p ON p.tablename = c.relname
WHERE c.relname IN ('course_intel','office_hour_checkins','office_hour_slots','salary_shares',
  'salary_figures','merchant_categories','outline_offers','shared_outlines','gym_buddies','activities',
  'team_join_requests','campus_board','clubs','club_members','club_invites','club_posts','club_polls',
  'club_votes','club_events')
ORDER BY 1;
```

B. **Grants follow each kind.** No row at all for the five sealed tables;
`shared_outlines` `SELECT` only; `team_join_requests`, `club_members` and
`club_votes` `DELETE,SELECT`; every other new table `DELETE,INSERT,SELECT,UPDATE`;
and only `account_app` anywhere:

```sql
SELECT table_name, grantee, string_agg(privilege_type, ',' ORDER BY privilege_type)
FROM information_schema.role_table_grants
WHERE table_name IN ('course_intel','office_hour_checkins','office_hour_slots','salary_shares',
  'salary_figures','merchant_categories','outline_offers','shared_outlines','gym_buddies','activities',
  'team_join_requests','campus_board','clubs','club_members','club_invites','club_posts','club_polls',
  'club_votes','club_events')
  AND grantee <> (SELECT tableowner FROM pg_tables WHERE tablename = table_name)
GROUP BY 1, 2 ORDER BY 1, 2;
```

C. **The team columns are there.** Five rows; `listed` and `looking_for_players`
are `NO` with default `false`:

```sql
SELECT column_name, is_nullable, column_default FROM information_schema.columns
WHERE table_name = 'teams'
  AND column_name IN ('listed', 'level', 'area', 'looking_for_players', 'blurb')
ORDER BY 1;
```

D. **Every function exists.** The schema gate in the deploy checks the 59 names,
so a missing one stops the deploy before traffic moves.

**Undo:** not needed. The tables are new and the current API never reads them;
the team columns default to off.

### 2. Deploy (mine, after the read-backs and your go-ahead)

```sh
./Application/deploy.run.sh all --yes
```

**Verify:**
- The gate reports row-level security on for 72 of 72 tables.
- A sample of the new routes answers 401 against a 404 control: `/api/grades/<id>/courses/<course>/class-figures`, `/api/fitness/<id>/exertion`, `/api/clubs/<id>`, `/api/jobs/<id>/applications/salaries`.
- A manual run of the recount door answers the six keys above.
- No errors in the new revision's logs; the live site matches the build.

**Rollback:** both halves together, Cloud Run and Pages to the revisions
`ROLLBACK.md` records as current when you deploy. The schema stays: the older
API never reads the new tables, and ignores the new team columns.
