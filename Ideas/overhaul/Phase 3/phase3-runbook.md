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

## Batch 1: the application tracker (item 1, D2–D5), pay on set days of the month, and D6. NOT YET DEPLOYED

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
