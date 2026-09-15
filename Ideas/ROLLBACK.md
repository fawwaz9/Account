# If it is broken

Written to be read while something is down and you are stressed. Commands
first, reasoning second. Every figure here was checked on 2026-09-15.

## What is where

| | |
|---|---|
| Frontend | https://account-2a7.pages.dev — Cloudflare Pages, builds from `main` |
| API | https://account-api-210502804146.us-west1.run.app — Cloud Run `account-api`, region `us-west1` |
| API (alias) | `https://account-api-oqrza5qxqq-uw.a.run.app` — the same service. Cloud Run answers on both forms; `gcloud` prints this one |
| Database | Supabase project `kujxxairehpwhxhnkbct`, region `us-west-2`, Postgres 17.6 |
| Backups | GitHub Actions artifacts, `Backup database` workflow, 90-day retention |
| Secrets | Google Secret Manager: `jwt-secret`, `database-url` |
| Known-good image | `us-west1-docker.pkg.dev/account-504419/account/backend:26e249f` |
| Known-good revision | `account-api-00003-ddz` |

## First: what kind of broken?

```sh
curl -s https://account-api-210502804146.us-west1.run.app/health
```

- `{"status":"ok","database":"ok"}` — the API is fine. The problem is the
  frontend, CORS, or Google sign-in. Skip to **Frontend**.
- `{"status":"unhealthy","database":"unreachable"}` — the container runs but
  cannot reach Supabase. Check Supabase is not paused, then the `database-url`
  secret.
- No response at all — the container is not starting. Go to **API**.

## API: roll back a bad revision

Cloud Run keeps every revision. Rolling back is a traffic switch and takes
seconds — no rebuild, no push.

```sh
gcloud run revisions list --service=account-api --region=us-west1
gcloud run services update-traffic account-api --region=us-west1 \
  --to-revisions=account-api-00002-5sd=100
```

**This fixes a bad *configuration*.** An environment variable, a secret
reference, a concurrency setting.

**It does not fix bad code, today.** All three revisions run the same image
(`sha256:3a44873f…`), so there is no earlier image to return to. **The first
time you deploy new code, the tag you are replacing becomes your only way
back** — do not delete it, and do not rely on `latest`, which by definition
points at the thing that just broke.

```sh
# once a second tag exists:
gcloud run deploy account-api --region=us-west1 --port=8000 \
  --image=us-west1-docker.pkg.dev/account-504419/account/backend:<older-sha>
```

## Container will not start at all

Cloud Run reports only "failed to start and listen on the port", which names
nothing useful. In order of likelihood:

1. **A missing environment variable.** `GOOGLE_CLIENT_ID` and `JWT_SECRET` have
   no defaults — `Settings()` raises during import and the process exits 1
   before serving. Check with
   `gcloud run services describe account-api --region=us-west1`.
2. **`--port=8000` missing.** The image hardcodes uvicorn on 8000; Cloud Run
   defaults to expecting 8080.
3. **Wrong architecture.** The image must be `linux/amd64`. A build on Apple
   Silicon without `--platform linux/amd64` produces arm64, which Cloud Run
   cannot execute.

Real logs:

```sh
gcloud run services logs read account-api --region=us-west1 --limit=50
```

## Frontend

Pages keeps every deployment. Dashboard → the project → *Deployments* → pick
the last good one → **Rollback**. No CLI needed, no rebuild.

If the site loads but every request fails, it is almost certainly one of:

- **CORS.** `ALLOWED_ORIGINS` on Cloud Run must be exactly
  `https://account-2a7.pages.dev`. Preview deployments are different origins and
  will always fail — that is correct, not a bug.
- **Google sign-in.** The Pages origin must be in the OAuth client's authorised
  JavaScript origins.

Both fail silently from the server's side: the API's logs stay clean while the
browser console shows everything.

## Data: restore a backup

**Never restore over production.** Restore into a second Supabase project, check
it, then repoint the app.

```sh
gh run list --workflow=backup.yml --repo fawwaz9/Account
gh run download --repo fawwaz9/Account --name account-db-YYYY-MM-DD --dir /tmp

cd Application/backend
set -a; source ../.env; set +a        # required — it arms the production guard
./scripts/restore_backup.sh /tmp/account-YYYY-MM-DD.sql.gz "<second project URL, port 5432>"
```

The script refuses a production target, refuses to run if the guard variable is
unset, and verifies row counts against the dump before reporting success.

**Use port 5432 (session pooler), not 6543.** A restore runs DDL and long COPYs
in one transaction, which transaction-mode pooling may split across backends.

Once the restored copy checks out, point the app at it:

```sh
printf '%s' "<restored project URL, port 6543>" | \
  gcloud secrets versions add database-url --data-file=-
gcloud run services update account-api --region=us-west1 \
  --update-secrets=DATABASE_URL=database-url:latest
```

Note the port changes back to **6543** here: the app wants the transaction
pooler, only the restore wanted the session one.

## Take a backup right now

Before doing anything risky:

```sh
gh workflow run backup.yml --repo fawwaz9/Account
```

## Things that are not emergencies

- **Supabase paused.** Free projects pause after 7 days with no database
  activity. Un-pause in the dashboard; no data is lost.
- **A cold start.** The first request after an idle period takes a second or two.
  That is `min-instances=0` working as intended.
- **A preview URL failing CORS.** Correct behaviour. Only the production origin
  is allowed.
