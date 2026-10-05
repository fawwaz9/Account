# Phase 0 — production runbook

Written for: you, carrying out the production steps for the Phase 0 work on
the `phase0` branch. Nothing here has been run. Every step either changes
nothing for the live app or can be reverted in one command, and each one says
which.

**Order matters:** pre-flight, then schema, then API, then frontend, then the
connection switch, then push. Stop at any step that doesn't verify; nothing
later depends on hurrying.

What ships, in one line each:
- **The isolation test suite and the RLS proofs.** These are tests and change
  nothing in production.
- **Row-level security.** Policies on every table plus five sign-in and lookup
  functions. Inert until step 5.
- **Bug fixes:**
  - the email wildcard (an account-takeover path)
  - three deletes that 500ed
  - PATCH transaction returning 500
- **Usage counts.** A new `usage_events` table, `users.created_at`, the visit
  counter, and the report script.
- **Push notifications.** A new `push_subscriptions` table, `reminders.pushed_at`,
  the service worker, the scheduler endpoint, and the Settings control.

---

## 0. Pre-flight (read-only, changes nothing)

In the Supabase SQL editor for project `kujxxairehpwhxhnkbct`:

```sql
-- Who owns the tables, and does that role bypass RLS?
SELECT tableowner, count(*) FROM pg_tables WHERE schemaname = 'public' GROUP BY 1;
SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname IN ('postgres', 'account_app');
```

**Proceed only if every table's owner is the role in today's `database-url`
secret (normally `postgres`).** RLS is enabled without `FORCE`, which leaves
the owner unaffected. If some other role owns the tables and lacks BYPASSRLS,
step 2 would cut today's API off from them. Stop and tell me instead.

Then take a fresh backup: GitHub → Actions → **Backup database** → Run workflow.

## 1. Create the restricted role (one statement, reversible)

Generate a password locally (`openssl rand -base64 32 | tr -d '/+=' | cut -c1-32`),
then in the SQL editor:

```sql
CREATE ROLE account_app LOGIN PASSWORD '<the password>'
    NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
```

- **Undo:** `DROP ROLE account_app;` works until step 2 grants to it.
- **Changes nothing for the live app.** Nothing connects as this role yet.

## 2. Apply the schema (additive; live app unaffected)

```sh
cd Application/backend
git checkout phase0
set -a; source ../.env; set +a
DATABASE_URL="$SUPABASE_DATABASE_URL" .venv/bin/python -m app._database.schema
```

What this adds:
- **Tables:** `usage_events` and `push_subscriptions`.
- **Columns:** `users.created_at` and `reminders.pushed_at`.
- **Indexes** for the new tables.
- **The seven `account_*` functions,** plus because the role now exists, a
  policy on every table and grants to `account_app`.

Nothing is dropped or rewritten.

**Verify** with the schema gate, using the read-only `ci_reader` URL:

```sh
SCHEMA_CHECK_URL="<session pooler URL as ci_reader>" .venv/bin/python scripts/check_schema_conformance.py
```

Expect `Every table and column this code selects is present` and
`Row-level security: on for 28 of 28 tables; role account_app exists`.

**Why the live app is unaffected:**
- Today's API connects as the owner, which RLS doesn't bind without `FORCE`.
- The new tables and columns are unused by the old code.

**Undo, if ever needed:** `ALTER TABLE <t> DISABLE ROW LEVEL SECURITY` per table.
The new tables and columns can simply stay.

## 3. Deploy the API (needs your go-ahead, per your standing rule)

```sh
git push origin phase0:ship
```

The workflow backs up first, checks the schema (it refuses if step 2 hasn't
run), smoke-tests, deploys and verifies. The API still connects as the owner
at this point.

**Verify:**
- Sign in with Google and with a password.
- Open each module.
- Create and delete a task.
- Delete a test job that has a confirmed shift. It used to 500.

**Rollback:** the usual one in `Ideas/ROLLBACK.md` (previous revision
`account-api-00028-jwz`). That's safe, because the schema from step 2 is
additive.

## 4. Push `main` (frontend)

Merge `phase0` into `main`, rebasing as you prefer, and push. Pages builds:
- the visit counter
- the Settings → Account "Notifications" and "Usage counts" rows
- the manifest and service worker

Onboarding is already live.

**Verify:** the live chunks against a production-URL build, as usual.

## 5. Switch the API to the restricted role (this turns isolation on)

```sh
# The new connection string: the transaction pooler, as account_app.
# Username form: account_app.kujxxairehpwhxhnkbct, port 6543.
printf '%s' "postgresql://account_app.kujxxairehpwhxhnkbct:<password>@<pooler host>:6543/postgres" | \
  gcloud secrets create database-url-app --data-file=- --project=account-504419
gcloud secrets add-iam-policy-binding database-url-app --project=account-504419 \
  --member="serviceAccount:account-api@account-504419.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Check it connects before pointing anything at it. The checker reads
# SUPABASE_DATABASE_URL from the env file it is given, so use a throwaway one:
umask 077; printf 'SUPABASE_DATABASE_URL=%s\n' "<the account_app URL>" > /tmp/app-role.env
.venv/bin/python scripts/check_db_connection.py /tmp/app-role.env
rm /tmp/app-role.env

gcloud run services update account-api --region=us-west1 --project=account-504419 \
  --update-secrets=DATABASE_URL=database-url-app:latest
```

**Verify immediately:**
- `/health` is ok.
- Sign in.
- Every module loads your data.
- Logs show no `permission denied` and no `row-level security`:

```sh
gcloud logging read 'resource.labels.service_name="account-api" severity>=WARNING' \
  --project=account-504419 --freshness=15m --limit=50
```

**Rollback (instant):**

```sh
gcloud run services update account-api --region=us-west1 --project=account-504419 \
  --update-secrets=DATABASE_URL=database-url:latest
```

The whole isolation suite already passes with the API connected as this role
(`tests/test_rls.py`), so I expect this to be uneventful. The rollback is
there because "expected" isn't "verified in production".

## 6. Push notifications (optional to do now; nothing breaks without it)

Without these settings the app says "Not set up on the server yet" in Settings
and the scheduler endpoint returns 404.

```sh
cd Application/backend
# 1. A VAPID key pair. The private half is a secret; the public half is derived from it.
.venv/bin/python -c "from app.Notifications.services.webpush import generate_keys; print(generate_keys()[0], end=\"\")" | \
  gcloud secrets create vapid-private-key --data-file=- --project=account-504419
# 2. The scheduler's shared secret.
openssl rand -hex 32 | tr -d '\n' | gcloud secrets create cron-secret --data-file=- --project=account-504419
for s in vapid-private-key cron-secret; do
  gcloud secrets add-iam-policy-binding $s --project=account-504419 \
    --member="serviceAccount:account-api@account-504419.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
done
gcloud run services update account-api --region=us-west1 --project=account-504419 \
  --update-secrets=VAPID_PRIVATE_KEY=vapid-private-key:latest,CRON_SECRET=cron-secret:latest

# 3. The scheduler: every 5 minutes (Cloud Scheduler's free tier is 3 jobs).
gcloud services enable cloudscheduler.googleapis.com --project=account-504419
gcloud scheduler jobs create http account-reminders --location=us-west1 --project=account-504419 \
  --schedule="*/5 * * * *" --http-method=POST \
  --uri="https://account-api-210502804146.us-west1.run.app/api/internal/reminders/dispatch" \
  --headers="X-Cron-Secret=$(gcloud secrets versions access latest --secret=cron-secret --project=account-504419)"
```

**Verify:**
- In Settings → Account → Notifications, press **Turn on for this device**,
  then **Send a test**.
- Create a reminder two minutes out, close the tab, and wait for it.
- On iPhone, add the site to the Home Screen first.

**Undo:**
- `gcloud scheduler jobs pause account-reminders`
- Remove the two secrets from the service with `--remove-secrets`.

**About the shared secret:** it's stored in the scheduler job's definition,
which anyone with viewer access to the GCP project can read. That's acceptable
here, where only you have project access. The stronger alternative is an OIDC
token from a scheduler service account, verified by the endpoint. Ask if you
want it.

## 7. Analytics report (when you want numbers)

```sh
USAGE_REPORT_URL="<session pooler URL>" .venv/bin/python scripts/usage_report.py --weeks 8
```

- **Read-only:** the server refuses writes on that connection.
- **Aggregates only:** no names, emails or ids are printed.
- **It is a read of production data.** You previously chose not to pursue
  per-user production reads; this reads usage counters to produce totals.
  Whether and when to run it is your call.
- `users.created_at` is NULL for accounts made before step 2, so time-to-first-
  value only counts accounts created after it.

## After all of the above

Phase 0's exit criteria (`Ideas/overhaul/phase0.md`) would then stand at:

- [x] Database isolation live, with the enumerated two-user test passing in CI
      (after step 5).
- [x] Surplus copies deleted (you, 2026-10-04).
- [x] Analytics reporting (after steps 2–4, and running step 7).
- [x] Push delivering (after step 6).
- [ ] Time to first value under 5 minutes. Measurable after step 2, but it
      needs new signups to measure, and onboarding is the lever.
