# If it is broken

Written to be read while something is down and you are stressed. Commands
first, reasoning second. Every figure here was re-checked against the live
deployment on **2026-09-28**, including that traffic is on `LATEST`.

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
| Current image | `…/backend:aaf93c4` — revision `account-api-00037-9p8`, serving 100% since 2026-10-06 06:56 UTC (Phase 1 review loops: projection against result, task timer and estimate ratio, saved plans). Digest verified by the deploy. **Roll back both halves together**: Cloud Run to `account-api-00036-qbx` (`81d099c`) and Pages to the `9466f97` deployment. The schema stays, because the older API never reads the four new columns or `saved_plans`. The API alone leaves the new timer and "Save as my plan" failing with an error and the new cards empty. The frontend alone loses no data: timers, answers, saved plans and projections stay stored |
| Previous (Phase 1, second batch + cap fix) | `…/backend:81d099c` — revision `account-api-00036-qbx`, serving 100% since 2026-10-06 03:21 UTC. `d81dfea` plus the syllabus-cap fix (`606a11a`); API and frontend are both at `81d099c`. Digest verified by the deploy. **Rolls back to `00035-cvz` alone safely**: the only difference is the cap, which needs the AI key to matter. Further back, see the next row |
| Previous (Phase 1, second batch) | `…/backend:d81dfea` — revision `account-api-00035-cvz`, serving 100% since 2026-10-06 03:02 UTC (Phase 1 second batch: scheme as the grade, add-only syllabus merge, degree audit, the purge fix). Digest verified by the deploy. **Roll back both halves together**: Cloud Run to `account-api-00034-54q` (`26db894`) and Pages to the `dbd78e1` deployment. The schema stays, because the older API never reads the new column or tables. Either half alone loses no data but degrades: see phase1-runbook.md, "Next batch", Rollback. **Rolling back the API also brings back the startup purge crash (D33)**, possible from about 2026-10-25 |
| Previous (Phase 1, first batch) | `…/backend:26db894` — revision `account-api-00034-54q`, serving 100% since 2026-10-05 21:59 UTC (Phase 1: forecast, year plan, paycheque check, CSV import, syllabus intake, grading schemes, course section, survey). Digest verified by the deploy. **Rolling back to `d081828` alone:** the schema can stay, since the six Phase 1 additions are new tables and nullable columns the older image never reads. The Phase 1 cards were built to hide on a failed read, so they disappear rather than break. But a course section typed in is silently dropped, so **prefer rolling back both halves** (Pages to `1992ff0`). This was reasoned from the code, not rehearsed |
| Previous (Phase 0) | `…/backend:d081828` — revision `account-api-00033-8sx`. Connected as `account_app` (isolation ON), VAPID_PRIVATE_KEY and CRON_SECRET set. Send a test reaches only the device that pressed it. **Rolls back to 238c122 alone safely** (a test then reaches every device again). **Before rolling back to any image older than 9f1f3cb, switch DATABASE_URL back to `database-url` FIRST**: older APIs never set `app.user_id`, so as `account_app` they see no rows |
| Previous (app code) | `…/backend:238c122` (`00032-vxd`): VAPID key stripped. Before it `9f1f3cb` (`00029`–`00031`), whose push returns 500 on the stored key; before that `be4f1d7` (`00028-jwz`) — needs the DATABASE_URL switch-back first |
| Previous image | `…/backend:6b3dcce` — revisions `account-api-00022-vmx` and `00023-jzr`, the latter an allowlist change on the same image. **The last functionally different release** |
| Deployer | `github-deployer@account-504419.iam.gserviceaccount.com`, via Workload Identity Federation (pool `github`, provider `github`). No key. Tokens only for `refs/heads/ship` of this repo. Roles: `artifactregistry.writer` on the `account` repo, `run.developer` on `account-api`, `iam.serviceAccountUser` on `account-api@…` |
| GCP project | `account-504419`, registry `us-west1-docker.pkg.dev/account-504419/account` |
| Repo | `fawwaz9/Account` — a push to `main` rebuilds the **frontend**; a push to `ship` deploys the **API** (`deploy-api.yml`) |

> **The production Supabase project is the only one.** The second project
> (`ommqbgaasrusrlizzyzm`, "Account_backup"), created for the step 34 restore test
> and holding a full copy of every user's data, was **deleted on 2026-10-04**. A
> future restore drill should restore into a project created for it, and delete
> that project when the drill is done.

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

**It now fixes bad code too.** Twenty image tags exist, newest first:
`2ee1e0e` (current), `6b3dcce`, `88500e6`, `df1d9bd`, `147d08b`, `8f73dca`, `da6ac93`, `394cb7c`, `93c9d73`,
`d635bf5`, `0224d31`, `ca86a3e`, `1ceb30f`, `e494729`, `89a7c22`, `18e3376`,
`7c1531a`, `18205eb`, `f6f7c32` and `26e249f`. Keep at least two — do not delete the
older tags, and do not rely on `latest`, which by definition points at whatever just
broke.

> **Only the current and previous exist locally** — `2ee1e0e` and `latest` (the
> same digest) plus `6b3dcce`. Everything older is cleared after each deploy, which
> is the standing housekeeping rule; the registry is the rollback source and holds
> all twenty. `docker pull` first if you need to inspect an older one.

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

> ### `2ee1e0e` rolls back cleanly, and rolling back brings a real bug with it
>
> Deployed 2026-10-02. Every figure anchored to "today" now resolves through the
> student's `timezone` preference instead of the server's clock, which on Cloud Run
> is UTC. Twenty-five call sites; the naive `shared/dates.today()` was deleted.
>
> **No schema change, no stored data, no contract change.** Every field keeps its
> shape; only which calendar day a figure is anchored to differs. Safe in both
> directions against any frontend, which sends browser-local dates either way.
>
> **But `6b3dcce` has the bug.** Roll back and free time disappears after 18:00 in
> Regina again, because UTC has rolled over and the day the client asked about
> reads as already past. The quick-capture parser mis-resolves "tomorrow" in the
> evening, and the finance month defaults can land a month early on the 1st. So
> this is one to roll *forward* out of, not back into: if someone reports an
> off-by-one-day figure, check which revision is serving first.

> ### `6b3dcce` rolls back cleanly, but takes a figure's MEANING with it
>
> Deployed 2026-10-02. An investment card's headline became what the holding is
> worth (`balance + difference_amount`) instead of the ledger balance, with the
> ledger figure on a `.sectorPaidIn` line beneath it. The account page header
> matches, from a new `AccountActivity.all_time_return`.
>
> **No schema change and no stored data involved** — both figures are derived on
> every read from rows that already existed under `88500e6`. Roll the API and the
> frontend back together and everything still works.
>
> **What changes is what "balance" means on that card.** Under `6b3dcce` the cards
> sum to net worth. Under `88500e6` they do not, because net worth included the
> gain and the cards did not — which is the bug `6b3dcce` exists to fix, reported
> within an hour of `88500e6` going live. So rolling back reintroduces it. If
> someone says the numbers do not add up, check which of these is serving before
> looking for anything else.
>
> **A mixed pair degrades rather than breaks.** A new frontend against `88500e6`
> finds no `all_time_return`, so the account page header falls back to the plain
> ledger balance and says "balance today" — the card still shows market value
> because it builds that from `Account.investment_return`, which `88500e6` does
> send. The two would disagree for one account, which is ugly and not broken.

> ### `88500e6` — the CODE rolls back. The TABLE and NET WORTH do not.
>
> Deployed 2026-10-01. Investment returns: a reading per month of what an
> investment account's holding is worth, a `(+3.2%)` on the account card, a return
> tile replacing Movements on investment accounts, and **recorded gain added to the
> net-worth headline**.
>
> **Rolling the API back is safe and loses no data, but it changes a number.**
> Net worth on `df1d9bd` is the sum of ledger balances; on `88500e6` it is that
> plus each investment account's latest recorded difference. So a rollback makes
> the headline *drop* by the total recorded gain, and rolling forward makes it rise
> again. Nothing is broken in either state — the two are different definitions of
> the same word — but if the figure is what someone is complaining about, this is
> why, and it is not a bug in whichever one they are looking at.
>
> **The table `account_month_values` outlives a rollback, and that is correct.**
> Applied by the schema step before this image deployed. An older image simply
> never queries it, so the rows sit there costing nothing and come back intact when
> you roll forward. **Do not drop it to "finish" a rollback** — that destroys every
> reading anyone has recorded, and no code change requires it. Production now has
> 27 tables where the schema builds 26; the extra is `category_budgets`, which is a
> different and older issue (audit #66).
>
> **The frontend is safe in both directions.** An old page against this API ignores
> the new fields. A new page against an older API gets `investment_return: null` on
> every account and `investment_gain` absent, which renders as no percentage on the
> cards, "Not recorded" in the tile, and no disclosure line under net worth — a
> page with a feature missing, not a broken one. The one thing that will **fail**
> is pressing Save in "What it is worth", because `PUT …/month-value` does not
> exist on an older image: the panel shows "That did not save" and nothing is
> written. So if you roll the API back and leave the frontend, expect that one
> button to be dead rather than silently lying.

> ### `df1d9bd` rolls back cleanly in both directions
>
> Deployed 2026-10-01. It gives a course's grades an order -- alphabetical, case
> ignored, digit runs compared as numbers -- where they previously came back in
> insertion order.
>
> **No schema change, no column moved, no contract changed.** The same fields in
> the same shape; only the sequence of a list differs. Rolling back restores
> insertion order, which is a worse page and not a broken one, and no stored data
> is involved either way: the order is derived from the name on every read, and
> there is deliberately no ordering column behind it.
>
> **Safe in either direction against any frontend.** The client does not sort and
> never did -- the course page groups by category with reduce and push, which
> preserves whatever sequence the API sent. So an old page against this API gets
> sorted grades, and a new page against an older API gets insertion order. Neither
> combination breaks.

> ### `ca4752e` is FRONTEND ONLY — no image, no revision, nothing on Cloud Run
>
> Deployed 2026-10-01. The API is still serving `147d08b`, and that gap is
> expected rather than a deploy someone forgot: nothing under
> `Application/backend/app/` changed. Roll it back from the Pages dashboard alone
> (*Deployments* → the previous one → **Rollback**).
>
> It adds the time-zone control to Settings and a shared `HelpTip`. **No API
> contract changed and no request was added** — `timezone` joins a
> `updatePreferences` payload the Calendar tab was already sending, and the API has
> accepted that key since the schema was written. So rolling back removes the only
> way to set a zone; it does not break anything, and a zone already saved stays
> saved and keeps working, because the services that read it never needed the
> control to exist.

> ### `147d08b` — the API rolls back alone. The FRONTEND does not.
>
> Asymmetric, and the asymmetry is the whole note. Deployed 2026-10-01 with the
> tabbed Settings page.
>
> **The API half is harmless to revert.** It changed one request type:
> `UserUpdate.preferences` became a `UserPreferencesPatch` whose fields are
> optional, so a patch naming three keys no longer writes all fourteen. An older
> image given the same request fills in defaults instead — which is what it did
> before, and what the fix existed to stop. Reverting restores the bug; it breaks
> nothing and loses no data already stored.
>
> **Rolling back the API ALONE, while the new frontend is live, is destructive.**
> Settings now has three tabs with a Save each, and each Save sends only its own
> three preference keys. Against the old API every one of those requests is
> parsed into all fourteen fields — so saving Calendar would reset the credit
> target, the default grade and the CGPA toggle, and saving Academic would reset
> the study window. The tabs are built on this image's behaviour.
>
> So if you roll the API back past `147d08b`, **roll the frontend back first**:
> Pages dashboard → the project → *Deployments* → the deployment before
> `147d08b` → **Rollback**. Frontend first, then API — the same order the
> `394cb7c` removal established, for a different reason.
>
> No schema change, no column moved, so there is nothing to undo in the database.
> `preferences` is an existing JSON column and the patch type is a request shape.
>
> One consequence worth knowing: the stored preferences of anyone who saved
> Settings before this deploy already have all fourteen keys written, because the
> old code wrote them. Nothing needs repairing — the values are now simply left
> alone instead of being overwritten each time.

> ### The category-limits sequence, `93c9d73` → `8f73dca`
>
> Four images in six days, easier to read as one story than as four notes.
> **Two of them add a table, and a table is the one thing rolling back cannot
> undo.**
>
> - **`93c9d73`** shipped category limits across the whole budget. Its API
>   **cannot roll back alone** — recorded at the time, still true.
> - **`394cb7c`** took that feature back out: a limit spanning every account was
>   judged against one account's share of the spending, so anything split across
>   two accounts always looked under budget. **A removal deploys in the inverse
>   order — frontend first, then API** — which is the rule this sequence exists
>   to have taught. **It also left its table behind**: `category_budgets` is
>   still in production with four indexes and two rows, found by counting on
>   2026-09-28 and written up as audit #66. Removing a feature removes the code;
>   the table is a separate decision and this one was never taken.
> - **`da6ac93`** rebuilt it keyed on `(account, category)`, the shape that makes
>   the limit and the spending cover the same money. **Adds
>   `account_category_limits`.**
> - **`8f73dca`** adds `account_category_month_limits`, so one month's limit can
>   differ from the standing one. **A second table.**
>
> **Rolling the API back past `da6ac93` needs the frontend rolled back first.**
> The account page reads `planned_is_derived` and a per-category `limit`; an
> older API returns neither, and the page renders a target it cannot explain.
> Frontend first, then API — the order `394cb7c` established.
>
> **The two tables stay.** Older code never selects them, so they cost nothing
> and orphan nothing, and dropping them would destroy limits the student set. If
> you roll forward again the schema step is still owed, because production runs
> `RUN_SCHEMA_ON_STARTUP=0` — but it is idempotent, so running it against tables
> that already exist is safe.
>
> **`d0cdeda` and `9e7493c` are FRONTEND ONLY** — no image, no revision. The
> first scopes the budget page's list rules so they stop reaching the grades
> page; the second rearranges the account page. Roll either back from the Pages
> dashboard alone. Both are CSS and JSX and neither touches an API contract.

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

**A missing chunk does not 404.** Pages serves `index.html` for any unmatched
path, including `/assets/*.js`, so a chunk that is gone comes back as HTTP 200
with `content-type: text/html`. The browser refuses to run it as a module
(`nosniff` is set), so the dynamic import rejects and the handling below takes
over. Two consequences: a script checking chunks must compare **content-type,
not status** — a status check cannot fail here and so is not a check — and a
`200` in a log is no evidence a chunk exists.

**"The app was updated" screen, or a route that will not open.** Since the
bundle was split, a tab left open across a deploy is holding chunk file names
this release no longer serves. The page reloads itself once and the problem is
gone; that screen only appears if a second failure follows inside ten seconds.
It is not a fault and there is nothing to roll back. If it appears *repeatedly*
on fresh loads, the deploy is genuinely missing files — roll the Pages
deployment back and check the build log.

If the site loads but every request fails, it is almost certainly one of:

- **CORS.** `ALLOWED_ORIGINS` on Cloud Run must be exactly
  `https://account-2a7.pages.dev`. Preview deployments are different origins and
  will always fail — that is correct, not a bug.
- **Google sign-in.** The Pages origin must be in the OAuth client's authorised
  JavaScript origins.

Both fail silently from the server's side: the API's logs stay clean while the
browser console shows everything.

## Live now

> **See "What is where" at the top of this file — that table is the one kept
> current.** This section used to repeat it and had drifted four revisions behind
> (it still named `da6ac93` / `account-api-00017-kwt` on 2026-10-01, when the API
> was on `account-api-00021-z29`). A second copy of the same fact is worse than no
> copy during an outage, because there is no way to tell which one is stale. What
> stays here is only what the top table cannot hold: the per-image notes on what
> can and cannot be rolled back alone.
>
> Most recent schema change: Phase 1, applied 2026-10-05. It added four tables
> (`survey_responses`, `imports`, `syllabus_parses`, `grading_schemes`) and two
> nullable columns (`transactions.import_id`, `courses.section`), all additive.

### `da6ac93` cannot have its API rolled back on its own

The same shape as the last time this was true, and for the same reason. An
older API omits `planned_is_derived` and the category `limit` fields, and the
client tests `entry.limit === null`. `undefined === null` is **false**, so every
category row on an account page would take the has-a-limit branch and render
`$NaN`.

**Roll back both halves together** — the Cloud Run revision *and* the Pages
deployment. Either alone leaves a mismatch.

The schema may stay where it is: `account_category_limits` is a new table that
the older image does not know about, and nothing it reads has moved.

## Two orphaned schema objects, left on purpose

Supabase carries `spend_categories.monthly_limit` and the `category_budgets`
table. **Nothing reads or writes either.** They are what remains of a
per-category spending-limit feature that shipped on 2026-09-24 and was rolled
back the same day, the judgement being that limits belong in the
spending-account section, where Planned spend already sets a per-account target.

They were left rather than dropped, deliberately:

- The column is nullable and **every row is NULL**; the table is **empty**. They
  cost a little catalogue space and nothing else.
- `DROP COLUMN` and `DROP TABLE` against production are irreversible, and the
  backup that would undo a mistake is the one taken before they were *added*.
  Trading a real risk for no measurable gain is a bad trade.
- Migrations in this project are additive by design, and `ensure_schema` only
  ever adds. There is no drop path to reuse, so removing them means hand-written
  DDL against the live database.

The same two objects exist in the local `data/app.db`, which the dev server
migrated on reload, and are equally inert there.

**So: if you are reading the schema and cannot find the code behind these, that
is the reason, and nothing is missing.** If they are ever genuinely in the way,
drop them as their own deliberate change with its own backup — not as
housekeeping bundled into something else.

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
