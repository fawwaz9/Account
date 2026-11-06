# Phase 4 — runbook

Written for: you, running Phase 4's one schema step and the deploy after it.
Each step says what it changes, the exact commands, how to verify it with a
negative control, and how to undo it. Follows `Ideas/overhaul/template.md`.

## Already live, no schema step

Deployed from this phase without touching the schema (D3), each recorded in
`Ideas/shipped.md` and `Ideas/ROLLBACK.md`:

| Batch | Commit | API revision | Items |
|---|---|---|---|
| 1 | `863cfcf` | `account-api-00050-fqt` | CGPA including this term (item 1) |
| 2 | `97f94a4` | `account-api-00051-6s2` | Grade scenarios, deadline risk, exam countdown, the digest and Today card (items 10, 3, 5, 6) |
| 3 | `ce9eba9` | `account-api-00052-x7s` | Course-drop, next-term, money what-if, term simulator, correlations, the guard's detection (items 11, 12, 14, 9, 8, 13) |

**Never deploy `phase4` beyond `ce9eba9` before step 1 below.** Every commit
after it needs a table or a column production lacks. The deploy's schema gate
would refuse it before traffic moved, but don't lean on that.

## Batch 4: the schema items. SHIPPED 2026-11-04, see the result at the end

| What | Commit on `phase4` | Schema change |
|---|---|---|
| Item 7: bring your own AI (D20) | `7f48825` | **New table `assistant_tokens`** (per-user); **new definer function `account_assistant_token_user`** |
| Item 6: the daily briefing push (D21) | `7f48825` | **New column `users.briefing_sent_on`** (date, nullable); **new definer function `account_users_with_briefing`** |
| Item 2: the weekly planner (D7, D22) | `320cd4a` | **New columns `events.source`** (varchar, nullable) and **`events.planned_task_id`** (uuid, nullable, no foreign key) |
| Item 4: focus sessions (D23) | `0d7ffc6` | **New table `focus_sessions`** (per-user) |
| Item 13: setting money aside for a crunch week (D24) | `f214ebf` | **New table `crunch_allocations`** (per-user) |
| Item 15: self-employed support (D25) | `662ab43` | **New tables `clients`, `invoices`** (per-user); **new column `transactions.business_percent`** (integer, nullable) |

Five new tables (72 → 77), four new nullable columns, two new definer functions
(59 → 61 in `rls.FUNCTIONS`). Nothing existing is altered or dropped, and
nothing is backfilled: every new column starts null, which every reader takes
as "not set".

**These ride along, with no schema of their own:** the walkthrough fixes (D26,
`f360bb6`) and transfers that carry a category (D27). D27 uses
`transactions.category_id` and `recurring_transactions.category_id`, which
production already has.

**The scheduler needs nothing new.** The briefing push rides the existing
reminder dispatch (`POST /api/internal/reminders/dispatch`), whose answer gains a
`briefings` count.

**Rehearsed** 2026-11-01 on this session's throwaway Postgres 16, never
production, with the `account_app`, `anon`, `authenticated` and `service_role`
roles present: the schema command at `ce9eba9` built the live shape (72
tables), then the same command on `phase4` took it to 77. Read-backs A to E
below all matched as written. The row-security walk (`tests/test_rls.py`)
passes on the same server.

### 0. Backup (yours: reads production into the backup bucket)

As before every schema step: **Actions → Backup database → Run workflow**, or
from your laptop:

```sh
gh workflow run backup.yml --repo fawwaz9/Account
```

**Verify:** the run succeeds, and its table count is 72 (Phase 3 batch 3's held
72 tables and 2,251 rows on 2026-10-28). The deploy workflow takes another of
its own before it moves traffic.

### 1. Apply the schema (yours: five new tables, four new columns, two functions)

```sh
cd ~/VS_Code/Account/Application/backend
git fetch origin phase4 && git checkout phase4 && git pull
set -a; source ../.env; set +a
DATABASE_URL="$SUPABASE_DATABASE_URL" .venv/bin/python -m app._database.schema
```

**Verify, in the SQL editor:**

A. **Every new table has row security, with the per-user policy for the API's
role only.** Five rows, each `true`, `ALL` and `{account_app}`:

```sql
SELECT c.relname, c.relrowsecurity, p.cmd, p.roles
FROM pg_class c LEFT JOIN pg_policies p ON p.tablename = c.relname
WHERE c.relname IN ('assistant_tokens', 'focus_sessions', 'crunch_allocations', 'clients', 'invoices')
ORDER BY 1;
```

B. **Only the API's role has grants, the ordinary four.** Five rows, each
`account_app` with `DELETE,INSERT,SELECT,UPDATE`. No `anon`, `authenticated` or
`service_role` (D6 of Phase 3):

```sql
SELECT table_name, grantee, string_agg(privilege_type, ',' ORDER BY privilege_type)
FROM information_schema.role_table_grants
WHERE table_name IN ('assistant_tokens', 'focus_sessions', 'crunch_allocations', 'clients', 'invoices')
  AND grantee <> (SELECT tableowner FROM pg_tables WHERE tablename = table_name)
GROUP BY 1, 2 ORDER BY 1, 2;
```

C. **The four columns are there, all nullable with no default.** Four rows:
`events.planned_task_id` `uuid`, `events.source` `character varying`,
`transactions.business_percent` `integer`, `users.briefing_sent_on` `date`;
every one `YES` and a null default:

```sql
SELECT table_name, column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE (table_name, column_name) IN (('users', 'briefing_sent_on'), ('events', 'source'),
  ('events', 'planned_task_id'), ('transactions', 'business_percent'))
ORDER BY 1, 2;
```

D. **Both functions exist, run as their owner, and only the API's role may call
them.** Two rows, each `prosecdef` `true` and `can_call` `true`; then the
negative control, two rows each `false`:

```sql
SELECT p.proname, p.prosecdef, has_function_privilege('account_app', p.oid, 'EXECUTE') AS can_call
FROM pg_proc p WHERE p.proname IN ('account_assistant_token_user', 'account_users_with_briefing');

SELECT p.proname, has_function_privilege('anon', p.oid, 'EXECUTE') AS anon_can_call
FROM pg_proc p WHERE p.proname IN ('account_assistant_token_user', 'account_users_with_briefing');
```

E. **No role but the API's holds a grant on any model table** (Phase 3 D6). Rows
for `category_budgets` only, if any (the 2026-09-24 orphan the install leaves
alone):

```sql
SELECT DISTINCT table_name, grantee FROM information_schema.role_table_grants
WHERE table_schema = 'public'
  AND grantee IN ('anon', 'authenticated', 'service_role', 'PUBLIC')
ORDER BY 1, 2;
```

**Undo:** not needed. The tables, columns and functions are new, and the live
API (`ce9eba9`) never reads them. If you want them gone anyway, that's a
`DROP` each, and it waits until nothing deployed reads them.

### 2. Deploy (after the read-backs match)

Either from your laptop:

```sh
cd ~/VS_Code/Account
git checkout phase4 && git pull
./Application/deploy.run.sh all --yes
```

or, as this phase's earlier batches went, by pushing `phase4` to `ship` (the
API workflow) and to `main` (Pages). Tell me which, and I'll run and record it.

**Verify:**
- The gate reports row-level security on for 77 of 77 tables, and all 61
  functions present.
- Health ok; the new revision serves 100%; the digest matches the commit.
- New routes answer 401 against a 404 control (they answer 404 on the old API):
  `GET /api/assistant/digest`, `GET /api/briefing/<id>/assistant-token`,
  `GET /api/calendar/<id>/planner`, `GET /api/tasks/<id>/focus`,
  `POST /api/finances/<id>/spending-guard/allocate`, `GET /api/jobs/<id>/invoices`,
  `GET /api/jobs/<id>/self-employment`.
- `POST /api/assistant/mcp` with a made-up token answers 401, not 500.
- The scheduler's next run of `POST /api/internal/reminders/dispatch` answers
  `200`; its body now carries a `briefings` count.
- No errors or 5xx in the new revision's logs; all settings carried over.
- The live site matches the build.

**Rollback:** both halves together. Cloud Run to `account-api-00052-x7s`, Pages
to the `ce9eba9` deployment. The schema stays: the older API never reads the new
tables or columns. What's lost until redeployed: any assistant token (its
holder's AI stops reading; nothing leaks, because the table is only read
through the new API), planned blocks stay in the calendar as ordinary events,
and invoices, focus sessions and set-aside marks stay stored, unread.

**Result:** SHIPPED 2026-11-04.
- **The schema step, run by you:**
  - Your manual backup before it (2026-11-02 20:35 UTC) held 72 tables. The next
    scheduled one held 77.
  - Read-backs A to E all matched as written.
- **The deploy, run by you with `deploy.run.sh all`:**
  - The API is at `94d8532` on `account-api-00053-l5t`, serving 100% from 00:02 UTC.
  - The gate: 77 of 77 tables with row security.
  - Its backup: 77 tables, 2,332 rows. Health ok.
- **Verified after:**
  - The seven new routes answer 401, against a 404 control.
  - MCP with a made-up token answers 401.
  - The dispatch answered 200 three times on the new revision.
  - No errors or 5xx in the new revision's logs.
  - The settings carried over: the same nine as before.
  - The live site matches the build, 44 files.
- **Not read:** the dispatch's `briefings` count. It is in the response body, which
  the logs don't hold.
- **Rollback, should you need it:** both halves together, Cloud Run to
  `account-api-00052-x7s` and Pages to the `ce9eba9` deployment.

## D29: subcategory weights. Waiting on your schema step

| What | Branch | Schema change |
|---|---|---|
| Subcategory weights, and even sharing (D29) | `subcategory-weights` | **New column `grades.subcategory_weight`** (float, nullable, no default) |

One new nullable column. Nothing existing is altered, dropped or backfilled by the
schema step. The averages change at deploy, and step 3 brings the stored ones over.

**It can share a schema session with audit batch 1** (`audit-batch-1`, its own runbook).
Each step adds only what its branch declares, and neither branch reads the other's columns.

### 0. Backup (yours)

```sh
gh workflow run backup.yml --repo fawwaz9/Account
```

**Verify:** the run succeeds with 77 tables. This backup holds every course's average under
the old rule, which is the way back for step 3.

### 1. Apply the schema (yours: one column)

```sh
cd ~/VS_Code/Account/Application/backend
git fetch origin subcategory-weights && git checkout subcategory-weights && git pull
set -a; source ../.env; set +a
DATABASE_URL="$SUPABASE_DATABASE_URL" .venv/bin/python -m app._database.schema
```

**Verify, in the SQL editor.** One row: `double precision`, `YES`, a null default. Then
the second query returns 0, since every grade starts even:

```sql
SELECT data_type, is_nullable, column_default FROM information_schema.columns
WHERE table_name = 'grades' AND column_name = 'subcategory_weight';

SELECT count(*) FROM grades WHERE subcategory_weight IS NOT NULL;
```

**Undo:** not needed. The live API never reads the column.

### 2. Deploy (after the read-back matches)

```sh
cd ~/VS_Code/Account
./Application/deploy.run.sh all --yes
```

**Verify:**
- Gate: 77 of 77 tables with row security. Health ok, the new revision at 100%, and the
  digest matches the commit.
- `PUT /api/grades/<id>/courses/<id>/subcategory-weights` answers 401 unauthenticated,
  against a 404 control. The old API answers 404.
- No errors or 5xx in the new revision's logs, and the same nine settings.
- The live site matches the build.

### 3. Bring the stored averages over (yours: reads every course, then writes)

Straight after the deploy, so the old API can't write an old-rule average back in between.
It runs as the tables' owner, with the same URL as the schema step. First the listing,
which writes nothing:

```sh
cd ~/VS_Code/Account/Application/backend
RECOMPUTE_URL="$SUPABASE_DATABASE_URL" .venv/bin/python scripts/recompute_averages.py
```

It prints one line per course whose average moves: the id's first eight characters, the
code, the term, and old → new. It marks any course with a recorded final grade, whose
letter and GPA don't move. Read it. If it looks right:

```sh
RECOMPUTE_URL="$SUPABASE_DATABASE_URL" .venv/bin/python scripts/recompute_averages.py --apply
```

**Verify:** it ends "Wrote N." with the N the listing gave, and a second listing says
"Nothing to change".

**Rollback:** Cloud Run to the revision before, and Pages to its deployment. The column
stays. The old API ignores it, and any splits come back on redeploy. The recomputed
averages stay at their new values: the old API rewrites each course's average under the
old rule the next time one of its grades is saved, and step 0's backup holds every old
figure exactly.
