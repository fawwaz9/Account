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

4. **Negative control.** Run the query from check 2 against an existing per-user
   table, `courses`. It still shows `account_app` with all four verbs, so the
   check above is telling `SELECT`-only apart from the usual grant.

**Undo:** not needed. The tables are new, and the old API never reads them.
Dropping them would also be safe while they are empty.
