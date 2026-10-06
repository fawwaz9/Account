# Phase 2 — production runbook

Written for: you. **Nothing here has been run.** Each step is written as the
work it deploys is built, per the template. Part A deploys as one batch once its
items are built and you say "deploy". The steps below grow with each item. A new
role for automatic approval (D5) would come later.

## 0. Send the calendar request (yours; changes nothing in the app)

The draft and who to send it to are in `Ideas/overhaul/calender-request.md`.
Tell me when UBC answers.

## The Part A batch: NOT YET RUN

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
