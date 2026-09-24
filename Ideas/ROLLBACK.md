# If it is broken

Written to be read while something is down and you are stressed. Commands
first, reasoning second. Every figure here was re-checked against the live
deployment on **2026-09-22**, including that traffic is on `LATEST`.

> **Shipping a change rather than fixing one?** `shipping.md` is the loop —
> build, verify, deploy, in the order the steps have to happen. This file is
> for when something is already broken.

## What is where

| | |
|---|---|
| Frontend | https://account-2a7.pages.dev — Cloudflare Pages, builds from `main` |
| API | https://account-api-210502804146.us-west1.run.app — Cloud Run `account-api`, region `us-west1` |
| API (alias) | `https://account-api-oqrza5qxqq-uw.a.run.app` — the same service. Cloud Run answers on both forms; `gcloud` prints this one |
| Database | Supabase project `kujxxairehpwhxhnkbct`, region `us-west-2`, Postgres 17.6 |
| Backups | GitHub Actions artifacts, `Backup database` workflow, 90-day retention |
| Secrets | Google Secret Manager: `jwt-secret`, `database-url` |
| Current image | `…/backend:d635bf5` — revision `account-api-00014-zxv`, serving 100% |
| Previous image | `…/backend:0224d31` — revision `account-api-00013-lst` |
| GCP project | `account-504419`, registry `us-west1-docker.pkg.dev/account-504419/account` |
| Repo | `fawwaz9/Account` — a push to `main` rebuilds the **frontend** only |

> **There is a second Supabase project, `ommqbgaasrusrlizzyzm`.** It was created
> for the step 34 restore test and holds **a full copy of every user's financial
> data and password hashes**. Its password has been rotated. It is not production
> and nothing points at it — but do not confuse the two when restoring, and
> delete it when the restore drill is no longer needed.

## First: what kind of broken?

```sh
curl -s https://account-api-210502804146.us-west1.run.app/health
```

- `{"status":"ok","database":"ok"}` — the API is up and can reach the database.
  If **everything** is broken, it is the frontend, CORS or Google sign-in — skip
  to **Frontend**. If **one page** is broken and the rest work, it is a schema
  change that never reached Supabase — see **One endpoint 500s after a deploy**.
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

> ### After rolling back, put traffic back on LATEST
>
> ```sh
> gcloud run services update-traffic account-api --region=us-west1 --to-latest
> ```
>
> **`--to-revisions` pins the service to that exact revision permanently.** It
> does not mean "serve this one now"; it means "stop following new deploys".
> Every subsequent `gcloud run deploy` then builds, pushes, creates a revision,
> reports **`has been deployed and is serving 100 percent of traffic`** — and
> changes nothing, because the traffic policy still names the old revision.
>
> This is not hypothetical: it happened here while *testing* the rollback
> command against the revision already serving, on the assumption that was a
> no-op. It is not a no-op. The next deploy silently did nothing, and the only
> symptom was that the fix it contained was still missing.
>
> **Check which revision is actually serving after any deploy:**
> ```sh
> gcloud run services describe account-api --region=us-west1 \
>   --format="value(status.traffic[].revisionName, status.traffic[].percent)"
> ```
> `LATEST (currently …)` is healthy. A bare revision name means you are pinned.

**It now fixes bad code too.** Eleven image tags exist: `d635bf5` (current),
`0224d31`, `ca86a3e`, `1ceb30f`, `e494729`, `89a7c22`, `18e3376`, `7c1531a`, `18205eb`, `f6f7c32` and `26e249f`. Keep at least two — do not delete
the older tags, and do not rely on `latest`, which by definition points at
whatever just broke.

> ### Rolling the API back alone now breaks the frontend
>
> As of `18205eb` this is no longer a safe standalone move. The frontend calls
> `GET /{user_id}/net-worth`, which exists only from that image onward, and it
> is fetched inside the same `Promise.all` as the accounts and the summary — so
> one 404 fails the whole batch and **the budget page and dashboard both go
> blank**, not just the net worth panel.
>
> If you roll the API back past `18205eb`, roll the frontend back too:
> Pages dashboard → the project → *Deployments* → the matching deployment →
> **Rollback**. Do the frontend first, so there is never a window where a new
> page is talking to an old API.
>
> The database column `accounts.counts_toward_net_worth` can stay either way.
> Older code ignores it, so there is nothing to undo there.

> ### `18e3376` is safe to roll back on its own, unlike `18205eb`
>
> Checked rather than assumed, because the rule above is not general — it is a
> fact about how each feature fetches. `18e3376` adds three things the frontend
> reads, and every one of them degrades instead of breaking:
>
> - **Cheapest path** is its own request with its own `.catch`, and the panel
>   renders nothing when it has no answer. A 404 hides the panel.
> - **Course links** are read as `course.links ?? []` at both call sites, so a
>   response without the field is an empty list, not a crash.
> - **The year suggestion** is one more field on `/me`; absent, the Settings
>   button simply does not offer itself.
>
> The difference from `18205eb` is that net worth was fetched inside a shared
> `Promise.all`, where one 404 failed the whole batch. Nothing here shares a
> request with anything else.
>
> `courses.links` and `users.first_year_calendar_year` can stay in either case.
> Older code never selects them, and both have a usable default.
>
> **`89a7c22` is safe in both directions too.** It changed the shape of one
> response: `best_value_grade_id` went away and `remaining_count` arrived. Each
> side tolerates the other's absence — the old page reads the missing field as
> undefined and renders one fewer line, and the new page's `remaining_count >
> items.length` is false against undefined, so it renders one fewer line. No
> database change at all.
>
> **`1ceb30f` is API-only, byte-identical frontend, and rolls back harmlessly.**
> It changes one string: the term heading is derived from the anchor instead of
> the user's `term_label`. Rolling back restores a stale label, not a fault.
>
> **`f98a1b9` is FRONTEND ONLY and rolls back from the Pages dashboard alone.**
> The API is still serving `d635bf5`, and that gap is expected rather than a
> deploy someone forgot: this change touched no backend file.
>
> It splits the budget page's load so a month step fetches only the month's
> summary instead of re-reading eight things and re-sending a write. **No API
> contract changed and no request was added** — the same eight endpoints are
> called, just not all of them every time — so rolling back restores extra
> requests, not correctness.
>
> Its three new dependencies are **dev-only** (`vitest` already, plus `jsdom`,
> `@testing-library/react`, `@testing-library/dom`). Confirmed absent from the
> deployed bundle, so they cost the browser nothing.

> **`d635bf5` rolls back cleanly in both directions.** Two changes, neither of
> which alters a stored value or a response the client reads.
>
> It moved `today()` and `money()` out of thirteen services into
> `app/shared/`, which is a move and not a behaviour change — there is a
> mutation test proving both module families read the one function now — and it
> removed three endpoints nothing has ever called:
> `GET /courses/{id}/statistics`, `/average` and `/letter-grade`. Those answer
> **404 rather than 401** from this image onward, which is the quickest way to
> tell which image is serving. Nothing became unreachable: `average` and
> `letter_grade` both travel on the course itself, which is where the frontend
> already read them.
>
> **No schema change**, so nothing to undo in the database, and an older
> frontend against this API behaves exactly as before.

> **`0224d31` rolls back cleanly in both directions, and is mostly deletion.**
> It removes code nothing called — `get_all_users`, `weekday_code`,
> `app/temp_data/`, `_database/design.txt` — and the five dashboard buttons that
> duplicated the sidebar, with the CSS they orphaned. **No API contract changed
> and no column moved**, so an older frontend against this API and a newer
> frontend against an older API both behave exactly as before.
>
> The one addition is `httpx` in `requirements.txt`, which is a **test**
> dependency: three files use Starlette's `TestClient`, which needs it, and it
> ships only under `fastapi[standard]`. It changes nothing the server does at
> runtime.
>
> **Its `app/_database/` diff is not a schema change**, which matters because
> shipping.md step 11 keys on that directory being untouched. The only file
> there is the deleted `design.txt`, a 95-line DDL sketch nothing read. No
> `.py` under `_database/` moved, so no schema step was run and none is owed.

> **`72f149f` is FRONTEND ONLY -- no image, no revision, nothing to roll back
> on Cloud Run.** The API is still serving `ca86a3e`, and the gap between that
> tag and `main` is expected rather than a deploy someone forgot: this change
> touched no backend file. Roll it back from the Pages dashboard alone
> (*Deployments* -> the previous one -> **Rollback**).
>
> It carries two small fixes worth knowing, neither of which changes an API
> contract or a database column. A term-timeline bar for a one-day course on
> the last day of term was drawn half a percent past its axis; and `originOf`
> in `securityHeaders.ts` returned the *string* "null" for an API base with no
> scheme, which would have put a bare `null` token in `connect-src` and had the
> browser refuse every API call before sending it. Production was never in that
> state -- the live `connect-src` names the Cloud Run URL correctly, checked
> after this deploy -- so rolling back restores a latent bug rather than fixing
> anything.

> **`ca86a3e` rolls back cleanly on its own, in both directions.** Checked
> rather than assumed, the way this section requires. It adds `gross_paid`,
> `deducted` and `net_paid` to each *per-job* row of the earnings windows, so a
> window can say which job its pay came from.
>
> The window-level paid figures are **older than this change** and still arrive
> from an earlier API, so the headline and its "X gross, Y deducted" line keep
> working. The only new reads are behind
> `per_job.filter(job => job.net_paid > 0)` — against an old API that is
> `undefined > 0`, which is `false`, so the list is empty, `paid.length > 1`
> is false and the per-job `formatMoney(job.net_paid)` is never reached. The
> breakdown disappears; nothing renders `NaN` and nothing throws.
>
> Rolling the **frontend** back alone is equally safe: the older page never
> selects the three fields. There is **no database change** in this deploy, so
> there is nothing to undo there either.

> **`e494729` is API-only and rolls back cleanly, but think before you do.** It
> is a behaviour change with no schema and no frontend change — the bundle is
> byte-identical, so Pages has nothing to roll back. Going back to `89a7c22`
> restores the bug where saving a grade with an empty score box unchecks a task
> the student ticked off, and that bug **destroys data**: it nulls
> `completed_at` and un-archives, and a row in that state cannot be told from
> one never completed. Roll back for something else, not for this.

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

## One endpoint 500s after a deploy, and the rest are fine

Almost certainly a **missing column or table**. The deployed service runs with
`RUN_SCHEMA_ON_STARTUP=0`, so **schema changes do not reach Supabase by
deploying** — the new code expects a column the database does not have.

```sh
cd Application/backend
set -a; source ../.env; set +a
DATABASE_URL="$SUPABASE_DATABASE_URL" .venv/bin/python -m app._database.schema
```

Idempotent, so running it when that was not the problem costs nothing. Confirm
in the logs first:

```sh
gcloud run services logs read account-api --region=us-west1 --limit=50 | grep -i 'column\|relation'
```

`UndefinedColumn` or `relation ... does not exist` is this. Rolling the image
back also fixes it, and is the faster move if you are unsure.

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
