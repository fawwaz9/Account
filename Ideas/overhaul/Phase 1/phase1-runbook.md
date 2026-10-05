# Phase 1 — production runbook

Written for: you, deploying the Phase 1 work on the `phase1` branch. Nothing
here has been run. Each step says what it changes and how to undo it. Follows
`Ideas/overhaul/template.md`.

**Already live, frontend only:** items 2 and 3 (D7, D8), and the subscriptions
"until when?" prompt (D21). They need nothing.

**Rebased onto `main` on 2026-10-05** (`26db894`). Both `ship` and `main`
fast-forward to it, and CI passed on it. The duplicated `.subsUntil` replay was
dropped. Commit ids in the table below are from before the rebase; the
messages are unchanged.

**Deploys run through `Application/deploy.run.sh`** (one command per step, and
it prints the failed logs if a run fails). It never applies the schema, so
step 0 stays yours.

## The backend batch: DEPLOYED 2026-10-05

Steps 0-2 are done: the schema step (yours), then the API (`account-api-00034-54q`)
and frontend, both at `26db894`. The two attempts GitHub's outage cancelled were
re-run once Actions recovered. Steps 3 and 4 (AI key, bucket) remain, and both are
optional.

### The batch, as it was

| What | Commits | Schema change |
|---|---|---|
| Item 9: forecast, runway and run-rates (D9) | `08dec4a` backend, `e532e63` card | None |
| Item 10: year plan and hours-to-goal solver (D10); the forecast counting card purchases | `f942221` backend, `e099325` card | None |
| Item 11: paycheque verification, BC overtime and vacation pay (D11) | `39df632` backend, `c65ffff` frontend | None |
| Item 13: prompted visits and the disappointment question (D12) | `84bc4bc` backend, `b4bbc77` frontend | **New table `survey_responses`** |
| Item 2, backend half: Attention says what the final needs (D13) | `fd59fbb` | None |
| Item 7: CSV import, duplicates, undo (D14) | `d33e34e` backend, `002814d` frontend | **New table `imports`; new column `transactions.import_id` (UUID) and its index** |
| Item 8: category suggestions in the import (D15) | `ad0c190` backend, then the frontend | None of its own |
| Item 1: syllabus intake (D16) | `b40ebcd` backend, `3060c43` frontend | **New table `syllabus_parses`**; and **a provider key** (step 3) |
| Item 6: the omnibox suggests a category (D17) | `414d50f` | None |
| Item 4: grading schemes (D18) | `81b0778`, `05be778` backend, `3d82e28` frontend | **New table `grading_schemes`** |
| The course section, and Attention asking for it (D22) | `7513b18` | **New column `courses.section`** |
| Keeping the original syllabus file (D24) | `bdb2ac3` | None of its own (two columns on the new `syllabus_parses`); **a bucket** (step 4) |

### 0. Apply the schema (item 13 adds a table; nothing is dropped or rewritten)

Pre-flight is the same as Phase 0's: a backup, via **Backup database** → Run
workflow. Then, from `Application/backend` on the `phase1` branch:

```sh
git checkout phase1
set -a; source ../.env; set +a
DATABASE_URL="$SUPABASE_DATABASE_URL" .venv/bin/python -m app._database.schema
```

**What this adds:**
- The `survey_responses` table and its unique index.
- The `imports` table, with an index on `account_id`.
- The `syllabus_parses` table, with indexes on `user_id` and `course_id`.
- The `grading_schemes` table, with an index on `course_id`. Its row policy reads the owning course's `user_id`.
- `ALTER TABLE transactions ADD COLUMN import_id UUID`, plus its index. It is
  nullable, so existing rows read NULL and nothing is backfilled. On a table of
  about a thousand rows it takes a moment. There is no foreign-key constraint on
  this added column, the same as the other added `_id` columns. The app
  enforces it.
- `ALTER TABLE courses ADD COLUMN section VARCHAR`. Nullable and not
  backfilled: nobody has recorded a section yet, so every current course will
  show "No section" in Attention until you fill it in.
- Because `account_app` exists, the table's row policy and grant. Install runs
  for every model table, so this also re-asserts the existing policies, revokes
  the definer functions from everyone but the owner and `account_app` (the
  Phase 0 D11 fix), and re-applies the per-table grants.

**Verify:**
- The deploy's schema gate passes in step 1. It refuses if this step hasn't run.
- In the SQL editor, this returns `t` four times:
  `SELECT relname, relrowsecurity FROM pg_class WHERE relname IN ('survey_responses', 'imports', 'syllabus_parses', 'grading_schemes');`
- `SELECT data_type FROM information_schema.columns WHERE table_name = 'transactions' AND column_name = 'import_id';`
  returns `uuid`.
- `SELECT data_type FROM information_schema.columns WHERE table_name = 'courses' AND column_name = 'section';`
  returns `character varying`.

**Undo:** not needed. The table is new, and the old API never reads it.

### 1. Deploy the API

```sh
git checkout phase1
./Application/deploy.run.sh api
```

It waits for CI on the commit, asks before pushing `ship`, then watches the
Deploy API run to the end.

The workflow backs up, checks the schema (nothing new is needed), smoke-tests,
deploys and verifies. The API keeps connecting as `account_app`; nothing about
isolation changes.

**Verify:**
- `/api/finances/<your id>/forecast` answers 401 without sign-in, against a 404
  for a made-up route.
- No errors in the logs.

**Rollback:** the previous revision, per `Ideas/ROLLBACK.md`. It is safe, because
nothing in the schema changed.

### 2. Push `main` (frontend)

```sh
./Application/deploy.run.sh web
```

It asks before pushing `main`, then waits until the live site matches a
production build of the commit, file by file.

**Verify:**
- The live files match a production-URL build.
- Open Budget: the "Where this is heading" card appears under safe-to-spend.

**Order matters.** The card calls the new route, so the API goes first. Pushed
first, the card would get a 404 and stay hidden (it says nothing on a failed
read). Harmless, but pointless.


### 3. Turn on syllabus reading (optional; nothing breaks without it)

Without these, "From a syllabus" doesn't appear, and the route answers 503.

**What you choose:**
- **A provider:** `openai`, `gemini` or `anthropic`.
- **A model:** that provider's model name. §13.21 suggests GPT-5 mini
  (`gpt-5-mini`) for extraction.
- **A paid-tier API key.** Never a free tier for real documents (D2).

```sh
# The key goes into Secret Manager without being echoed:
echo -n "API key: "; read -rs KEY; echo
printf '%s' "$KEY" | gcloud secrets create llm-api-key --data-file=- --project=account-504419
unset KEY
gcloud secrets add-iam-policy-binding llm-api-key --project=account-504419 \
  --member="serviceAccount:account-api@account-504419.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
gcloud run services update account-api --region=us-west1 --project=account-504419 \
  --update-secrets=LLM_API_KEY=llm-api-key:latest \
  --update-env-vars=LLM_PROVIDER=openai,LLM_MODEL_EXTRACT=gpt-5-mini
```

**Verify:**
- Grades shows "From a syllabus".
- Read one of your own syllabi, check the verification screen against the PDF,
  and create the course.
- Tell me how it went. This is the first live call through the adapter, and
  `syllabus_parses.fields_changed` will show what it got wrong.

**Undo:**
```sh
gcloud run services update account-api --region=us-west1 --project=account-504419 \
  --remove-secrets=LLM_API_KEY
```

### 4. Keep syllabus files (optional; nothing breaks without it) (D24)

Without this, a syllabus is read and its extraction kept, but not the file.
One private bucket, next to the API, that only the API's own identity can
reach. No key is created.

```sh
gcloud storage buckets create gs://account-504419-syllabi --project=account-504419 \
  --location=us-west1 --uniform-bucket-level-access --public-access-prevention \
  --soft-delete-duration=0
gcloud storage buckets add-iam-policy-binding gs://account-504419-syllabi \
  --member="serviceAccount:account-api@account-504419.iam.gserviceaccount.com" \
  --role="roles/storage.objectUser"
gcloud run services update account-api --region=us-west1 --project=account-504419 \
  --update-env-vars=SYLLABUS_BUCKET=account-504419-syllabi
```

- **Public access prevention** means the bucket can never be made public by
  mistake.
- **Soft delete is off,** so deleting an account deletes its files. Otherwise
  they would be recoverable for 7 days. Syllabi can be re-uploaded, so nothing
  of value is lost.
- **`objectUser`** on this bucket only: read, write and delete objects, and
  nothing else in the project.

**Verify:** read a syllabus and create the course. The course page shows
"Syllabus · <file>", and downloading it gives back the PDF.

**Undo:**
`gcloud run services update account-api --region=us-west1 --project=account-504419 --remove-env-vars=SYLLABUS_BUCKET`.
Files already kept stay in the bucket, and account deletion still removes them
only while the variable is set. So if you turn this off, delete the bucket too.

### Optional, recommended: close `category_budgets` to the public roles (D23)

You decided to keep `category_budgets`. It stays as it is: no model builds it,
so `account_app` has no grant on it and the API can't read it. What is left is
Supabase's default grant to `anon` and `authenticated` (Phase 0 D11). With the
Data API disabled nothing can use that grant today, but turning the Data API
back on would expose the table, since it has no row policy. This removes the
grant without touching a row. In the Supabase SQL editor:

```sql
REVOKE ALL ON category_budgets FROM anon, authenticated;
```

**Verify:** `SELECT has_table_privilege('anon', 'category_budgets', 'SELECT');`
returns `f`.

**Undo:** `GRANT ALL ON category_budgets TO anon, authenticated;` (not that you
would want it).

## Next batch (built on `phase1-batch2`, waiting for your go-ahead)

Rebased onto `main` on 2026-10-05 as `phase1-batch2` (the old `phase1-next`
on GitHub is the pre-rebase copy, deleted once this is on `main`), so
`deploy.run.sh` can fast-forward both
`ship` and `main` to it.

| What | Commit | Schema change |
|---|---|---|
| Picking a scheme as the grade (D25, D29), and the required-final fix for courses weighted past 100% | `3dca729`, `46db2df` | **New column `courses.counting_scheme_id` (UUID)** |
| A syllabus adding to an existing course, add-only (D27, D30) | `6f8a5b2` | None |
| The degree audit (D31) | `9d5adfb` | **New tables `degree_requirements`, `course_equivalences`** |
| `deploy.run.sh` pushes the branch so CI runs, and a docs-only commit stands on its code's run | `43f65e7` | None |
| **The purge fix** (below) | `4598a82` | None |

**The purge fix, and why it should not wait long.** The expired-account purge
runs at API startup. It did not reach `account_category_limits`,
`account_category_month_limits` or `account_month_values`, so purging anyone who
had set a category limit or a month value would have the foreign key refuse the
delete of their accounts, and the refusal raised out of startup: an instance
that cannot start serves nothing. It has not happened yet. Category limits
shipped 2026-09-25 and the grace period is 30 days, so **the earliest it could
is about 2026-10-25**, and only for someone who set a limit and then asked to
delete their account. The fix cascades those tables, gives every foreign key a
relationship so the delete order is known (a test holds every key to it), and
makes a refused purge roll back, log, and wait for the next start instead of
raising. It needs no schema step, so it can ship on its own ahead of the rest
if this batch is held up: cherry-pick `4598a82` onto `main` and run
`deploy.run.sh api`.

### 0. Back up, then apply the schema

Run **Backup database** (Actions → Run workflow) and wait for it to pass. Then:

```sh
git checkout phase1-batch2
cd Application/backend
set -a; source ../.env; set +a
DATABASE_URL="$SUPABASE_DATABASE_URL" .venv/bin/python -m app._database.schema
```

**What this adds:**
- `ALTER TABLE courses ADD COLUMN counting_scheme_id UUID`. Nullable and not
  backfilled: every course reads NULL, which means "the course's own weights",
  exactly what it shows today.
- The `degree_requirements` and `course_equivalences` tables, each with an index
  on `user_id`, row security, a policy on `user_id`, and `account_app`'s grant.
- As every time, install re-asserts the existing policies and grants.

Nothing is dropped, rewritten or backfilled.

**Verify** in the SQL editor:
- `SELECT data_type FROM information_schema.columns WHERE table_name = 'courses' AND column_name = 'counting_scheme_id';`
  returns `uuid`.
- `SELECT relname, relrowsecurity FROM pg_class WHERE relname IN ('degree_requirements', 'course_equivalences');`
  returns `t` twice.
- `SELECT tablename, count(*) FROM pg_policies WHERE tablename IN ('degree_requirements', 'course_equivalences') GROUP BY tablename;`
  returns both tables.
- The deploy's schema gate passes in step 1. It refuses if this step has not run.

**Undo:** not needed. The column is nullable and the tables are new; the API
that is live now reads none of them.

### 1. Deploy, API then frontend

```sh
./Application/deploy.run.sh all
```

It checks CI on the commit, asks, pushes `ship` and watches the Deploy API run
(backup, schema gate, smoke test, digest check), then pushes `main` and waits
until the live site matches a build of the same commit.

**Verify:**
- `/api/degree/<your id>` and `/api/grades/<your id>/courses/<a course id>/counting-scheme`
  answer 401 without sign-in, against a 404 for a made-up route.
- Signed in: Grades → **Degree audit** opens (empty until you add a
  requirement). On a course with a second grading scheme, **Count as grade**
  switches the course's grade and says which scheme is counting.
- No errors in the logs.

**Rollback: both halves together** — Cloud Run to `account-api-00034-54q`
(`26db894`), and Pages to the `dbd78e1` deployment. The schema stays: the older
API never reads the new column or tables.

Either half alone loses no data, but each degrades:
- **API alone:** the new pages and buttons show "Couldn't load the audit" /
  "Couldn't change which scheme counts". A scheme someone picked is ignored, so
  that course shows its own weights again until the API comes back, and the
  required-final figure goes back to the old, wrong one past 100%. The purge
  fix goes too, so the 2026-10-25 date above applies again.
- **Frontend alone:** a scheme someone picked still counts on the API, but the
  older course page neither says so nor offers a way to change it.
