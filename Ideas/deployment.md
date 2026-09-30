# Deployment

**This is done. The app is live and a second person is using it.** What follows
is the record of how it got there, kept because the commands, the traps and the
things that went wrong are what you need when you change any of it.

To get out of trouble right now, read [ROLLBACK.md](ROLLBACK.md) instead — it is
written to be read while something is down.

**To ship a feature, read [shipping.md](shipping.md).** That is the loop you run
every time: build, verify, deploy, record. This file is the one-off history of
how the deployment was built, and it is long because it argues with itself.

**The target:** Google Cloud Run (the API) + Supabase (Postgres) + Cloudflare
Pages (the frontend), free, for about twenty invited people.

**Why that target,** and every alternative rejected along the way, is in
`Ideas/plan-a-decisions.md` — 34 decisions with their reasoning and what would
change my mind. This file is the *doing*; that one is the *why*. Where a step
below is contestable it names the decision, so `D2.3` means go and argue there.

---

## Where this stands

**Steps 1 to 38 are done.** Only 39 (invite the rest) remains, and that is a
decision rather than work. Step 38's week has long passed — see the step for what
the watch actually showed.

| | |
|---|---|
| Backend tests | **940 on SQLite**. The Supabase run was 730 + 2 skipped at 740 and has not been repeated |
| Frontend | `tsc --noEmit` and `vite build` clean, **142 vitest cases in 17 files** |
| Frontend URL | `https://account-2a7.pages.dev` — Cloudflare Pages, builds from `main` |
| API URL | `https://account-api-210502804146.us-west1.run.app` |
| Serving | revision `account-api-00018-2zp`, image `backend:8f73dca`, traffic on **LATEST** |
| Database | Supabase `kujxxairehpwhxhnkbct`, `us-west-2`, Postgres 17.6. **26 tables live, 25 in the schema** — the 26th is `category_budgets`, left behind by a rollback; see `session-handoff.md` |
| Size | 912 rows, 13 MB against a 500 MB cap — measured 2026-09-28 |
| Backups | nightly GitHub Action, 09:00 UTC, 90-day artifacts — **restored once, for real** |
| Monitoring | UptimeRobot on `/health` and on the frontend |
| Part 1 (local code changes) | **Done** — steps 1–15, green light passed |
| Part 2 (the Postgres port) | **Done** — steps 16–21, 588 rows moved and verified by value |
| Part 3 (deploy) | **Done** — steps 22–32, tested from mobile data |
| Part 4 (before others join) | **Done** — steps 33–36 |
| Part 5 (people) | **Step 37 done**, three addresses. 38 and 39 outstanding |

**Still carried, deliberately, and each written up below:**

- **Step 12a / D5.5** — every rate limiter keys on the peer address, which behind
  Cloud Run is Google's front end. Confirmed in production: 99 of 99 requests
  arrived from `169.254.169.126`. The limits are therefore one shared budget.
  Tolerable at three users; fix it before the invite list opens.
- **The Dockerfile does not honour `$PORT`**, which is why `--port=8000` is
  mandatory on every deploy.
- **One copy of each backup**, in GitHub artifacts only, expiring at 90 days.
- **A second Supabase project exists** (`ommqbgaasrusrlizzyzm`) holding a full
  copy of everyone's data from the step 34 restore test. Its password has been
  rotated. Delete it or treat it as production.

Phase 0 was run against a `VACUUM INTO` copy on ports 8200/5273. It confirmed the
images build, the stack works, auth works end to end, data survives
`down && up`, the image carries no real data or secrets, and the container runs
as non-root. It also found **B8** below, which nothing else would have.

---

## The architecture, in one paragraph

Cloudflare Pages serves the built JavaScript to the browser and holds no data and
no secrets. The browser then calls Cloud Run, on a different origin, with a
bearer token. Cloud Run holds all the logic and is the only thing that knows the
database password. Supabase holds all 25 tables and is the only thing that
remembers anything. **The browser never talks to Supabase** — this is deliberate,
and `plan-a-decisions.md` D2.0 explains why using Supabase the usual way would be
wrong here. A full trace of one request is in the "How Account Moves Data"
artifact.

---

## Before you start

Accounts you will need, all free, none needing a card except Google Cloud:

- **Google Cloud** — a billing account with a card is required even for the
  always-free tier. It is used for identity verification and is not charged while
  you stay inside the free limits.
- **Supabase** — no card.
- **Cloudflare** — no card.

Have to hand: the Google OAuth client ID this app already uses, and access to its
console to add an origin later (step 32).

**Work through this in order.** Parts 1 and 2 happen entirely on your machine and
are reversible. Nothing reaches the internet until Part 3.

---

## Part 1 — Code changes, all local

Nothing here needs a cloud account. Do it all before creating one, because every
one of these is easier now than over SSH or through a console.

### 1. Land PR #39 (soft delete) — **DONE**

**Do:** merge it, rebase as usual.

**Why it is first:** until it lands, `DELETE /users/{id}` is an immediate,
irreversible cascade across every table. That is the wrong thing to have live the
moment somebody other than you has an account. This is audit finding **S11**.

**Verify:** suite still green.

### 2. Decide on the other six PRs — **DONE, all merged**

**#40** (accessibility) is small and worth taking. **#28–#32** are feature work —
subscriptions, blind spots, PDF export, the priority badge, the recurring split.
None blocks deployment.

**Recommendation:** land #40, and decide #28–#32 on whether you would rather your
friends see them now or later. Landing them after deployment is a good way to
prove the deploy path works twice.

### 3. Fix `connect_args` so a Postgres URL does not crash — **DONE** (`361c2a5`)

**Do:** in `app/_database/db.py`, parse the URL rather than passing the
SQLite-only argument unconditionally.

```python
from sqlalchemy.engine import make_url

url = make_url(DATABASE_URL)
connect_args = {"check_same_thread": False} if url.get_backend_name() == "sqlite" else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
```

**Why:** `check_same_thread` is SQLite-only and psycopg rejects it, so *any*
non-SQLite `DATABASE_URL` currently crashes at import — despite
`docker-compose.yml` advertising the variable as configurable. This is a live
bug. See **D1.1**.

**Verify:** `DATABASE_URL=postgresql://x python -c "import app.main"` should fail
on *connection*, not on an invalid argument.

### 4. Add the Postgres driver — **DONE** (`361c2a5`, done with step 3 since it is what verifies it)

**Do:** add `psycopg[binary]==3.*` to `requirements.txt`.

**Why psycopg 3 and not psycopg2 or asyncpg:** **D1.2**.

**Verify:** rebuild the venv from `requirements.txt` alone and run the suite. This
also fixes the stale-venv problem (**S9**) — yours currently has 64 packages
installed against 9 declared.

### 5. Make the test database configurable — **DONE** (`6a1926f`)

**Do:** in `tests/conftest.py`, read `TEST_DATABASE_URL`, defaulting to the
current SQLite setup so the fast local loop is unchanged.

**Why:** step 19 runs the whole suite against Postgres, and that is the step that
makes the port trustworthy rather than merely importable. **D1.5**.

**Verify:** 669 still pass with the variable unset.

### 6. Add `/health` — **DONE** (`6a1926f`)

**Do:** a route that runs `SELECT 1` and returns `{"status": "ok"}`.

**Why it must touch the database:** a check that only proves the process is
listening reports healthy while every request fails on a dead connection. **D6.1**.
Audit finding **B6**.

**Verify:** `curl localhost:8000/health` returns 200; stop the database and
confirm it returns 503 rather than 200.

### 7. Turn off the docs endpoints in production — **DONE** (`6a1926f`)

**Do:** `FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)`
when an environment variable says production, keeping them on locally.

**Why:** they are public today — Phase 0 confirmed `/docs` returns 200 — which
publishes the shape of all 133 routes to anyone. Audit finding **B3**.

**Verify:** with the variable set, `/docs` returns 404; without it, 200.

### 8. Stop re-checking the schema on every cold start — **DONE** (`0a09615`)

**Do:** gate the `lifespan` body behind an environment variable, so
`create_all`, `ensure_schema` and `ensure_indexes` run when you ask them to
rather than on every boot. Run them as a deploy step instead.

**Why:** measured, those three issue **278 statements** — 247 of them from
checking all 49 indexes. Against a local SQLite file that is free. Against
Postgres over a network at 2 ms a round trip it adds roughly **half a second to
every cold start**, paid by whoever arrives first after a quiet spell, to
re-confirm a schema that was already correct four minutes ago.

**Verify:** with the variable unset the server starts without issuing DDL; with
it set, it does.

### 9. Make `ALLOWED_ORIGINS` actually configurable — **DONE**

**Do:** in `docker-compose.yml`, change the hardcoded
`ALLOWED_ORIGINS: http://localhost:5173` to `${ALLOWED_ORIGINS}`, and add the
variable to `.env.example` with a comment saying what breaks when it is wrong.

**Why:** it is not merely unset — it is *hardcoded*, so it cannot be changed per
environment without editing the compose file. Audit finding **B2**, and Phase 0
reproduced the failure live: serving the frontend on 5273 while this said 5173
gave HTTP 400 on the preflight from the real origin and 200 from the stale one.
It presents as "the API is down" and appears nowhere in the API's logs.

**Verify:** set it to a wrong value and confirm the preflight fails; set it right
and confirm it passes.

### 10. Collapse the two `.env` files into one — **DONE** (`1f742c6`)

**Do:** keep one, have both the compose file and local runs read it.

**Why:** `Application/.env` and `Application/backend/.env` hold the same secrets
and are byte-identical today with nothing keeping them so. When they drift, the
symptom is tokens signed with one key and verified with another — which reads to
a user as being randomly logged out. Audit finding **B7**.

### 11. Add the invite gate — **DONE** (`1f742c6`)

**Do:** an `ALLOWED_SIGNUP_EMAILS` environment variable, checked in
`create_local_user` **and in the Google sign-in path**.

**Why both doors:** an allowlist that only guards `create_local_user` leaves
`POST /auth/google` wide open, because `get_or_create_user_by_google_id` creates
accounts too. Audit finding **B5**; reasoning and the rejected Cloudflare Access
alternative in **D5.1**.

**Verify:** an address on the list can register, one off it gets a clear refusal,
and the same is true through Google.

### 12. Rate-limit `/register` — **DONE** (`5aae710`)

**Do:** apply the existing `SlidingWindowLimiter` to the register route.

**Why:** only `/login` is limited today. The mechanism already exists. Audit
finding **S4**.

**What it actually spends, which is the reason the limit differs from login's.**
Login guards a secret, so it counts *failures* and clears a key on success.
Registration has no secret: an accepted call costs a database row and a ~200ms
password hash, and a refused one still answers whether an address is taken or
invited. Counting only failures would bound the enumeration and leave the flood
— the larger problem — unbounded. So every attempt counts, success included.
**D5.4.**

**20 an hour, not 5.** Every key is `request.client.host`, and a shared network
is one key. See step 12a: behind a proxy *everybody* is one key, so a ceiling
tuned for one person is a ceiling for the whole invited group signing up on the
same evening.

**Verify:** done live against the container — 20 attempts answered normally, the
21st refused with `Retry-After: 3592`, a sign-in during the block still reaching
the password check rather than a 429, and the audit log reading
`19 rejected / 1 success / 1 throttled`.

### 12a. Read the caller's real address — **CONFIRMED IN PRODUCTION, still not fixed**

**The problem:** every limiter in this app keys on `request.client.host`, the
peer address. On Cloud Run the peer is Google's front end, not the person. So in
production these limiters collapse from one budget per caller towards **one
budget shared by everyone** — including `/login`, which has behaved this way
since it was written and has simply never been deployed behind a proxy before.

**Why it is not fixed here:** the fix is to read `X-Forwarded-For`, and an
unvalidated forwarded-for header is attacker-controlled — trusting it hands
anyone an unlimited supply of fresh keys, which is strictly worse than the
shared budget. Doing it correctly means knowing exactly how many hops the
platform appends and trusting only that many, which is a decision about Cloud
Run specifically and is worth making with the deployed thing in front of you.

**What to do in the meantime:** nothing breaks. An unbounded loop still stops,
which is the property step 12 was added for. Revisit after step 32, and see
**D5.5**.

> **Confirmed in production, no longer a prediction.** Cloud Run's request logs
> show **99 of 99** requests arriving from `169.254.169.126` — one address for
> every caller. So `per_client`, `per_account` and `per_client_registration` are
> all keyed on a single value: the register limit is 20 an hour **across
> everyone**, and `/login`'s per-client limit is effectively global. That is
> survivable at twenty invited users and is the first thing to fix if the list
> ever opens up.

### 13. Add a React error boundary — **DONE** (`5aae710`)

**Do:** wrap the router in one, showing something a person can act on.

**Why:** any render exception is currently a white screen. On your own machine
you read the console; a friend just sees a broken app and stops using it. Audit
finding **S3**.

**Placed outside `AuthProvider`, not just around the routes:** a boundary inside
the provider cannot catch the provider itself throwing, and "it failed while
working out whether you are signed in" is exactly the case that would otherwise
be a white screen.

**What it does not catch,** stated so nobody assumes more than it does: errors in
event handlers, in `setTimeout`, and in rejected promises never interrupt a
render, so React does not route them here. A failed fetch is still handled by the
error state each page already keeps.

**Verify:** `getDerivedStateFromError` turns a thrown error into fallback state,
children pass through untouched when there is none, and the fallback renders the
message, the component stack, both actions and `role="alert"` — checked by
rendering the component, not by reading it.

### 14. Write the security headers for Pages — **DONE** (`5aae710`)

**Do:** a `_headers` file in the frontend build output with HSTS, CSP,
`X-Content-Type-Options`, `Referrer-Policy` and `X-Frame-Options`.

**Why a `_headers` file and not `nginx.conf`:** in this architecture nginx is
gone — Pages serves the bundle. The finding survived; its fix moved. **D4.2**,
audit finding **S1**.

**Generated at build time, not checked in.** Every directive is fixed except
`connect-src`, which has to name the API's origin — and that origin differs
between local, preview and production. A checked-in file could only be right for
one of them, and when it is wrong the browser refuses the request before it is
sent, so the API's logs stay empty while the app looks down. That is the same
shape as the CORS bug Phase 0 found. `securityHeaders.ts` derives it from the
same `VITE_API_BASE_URL` the bundle is built with, so the two cannot drift.
**D4.3.**

**One deliberate concession:** `style-src` allows `'unsafe-inline'`, because
about thirty components set a `style={{...}}` attribute (progress-bar widths,
mostly) and CSP counts a style attribute as inline style. `script-src` stays
strict, and that is the directive that stops XSS.

**Verify:** confirmed inside the built image that the `connect-src` origin and
the URL inlined in the bundle are the same string. **Still to check on the real
deploy — see step 29a.**

### 15. Green light — **DONE** (`5aae710`)

**Do:** run the whole suite, `npx tsc --noEmit`, `npm run build`, and one
`docker compose up --build` to confirm nothing here broke the image.

**Stop here if anything is red.** Everything after this point is harder to debug.

**Result:** 710 passed on SQLite, 708 passed + 2 skipped on Postgres 16,
`tsc --noEmit` clean, `vite build` clean, and the full compose stack up with
`/health` 200, `/docs` 404, the invite gate refusing a stranger and the register
limit refusing the 21st attempt. The real `data/app.db` was checksummed before
and after and is byte-identical: the run was pointed at a scratch directory.

---

## Part 2 — The Postgres port, still local

### 16. Create the Supabase project — **DONE**

**Do:** new project, free plan. **Choose the region nearest your users and write
it down** — Cloud Run goes in the matching one at step 27.

> **The region is `us-west-2`** (host `aws-0-us-west-2.pooler.supabase.com`).
> Cloud Run goes in the matching one at step 27 — `us-west1` is the nearest GCP
> region. Read back off the connection string rather than remembered, and
> `scripts/check_db_connection.py` prints it every time it runs.
>
> Postgres **17.6**, not 16 — worth knowing, since the local rehearsals ran
> against a 16 container.

**Why region matters:** every request makes several round trips, and the
dashboard makes five queries. A careless pairing can cost half a second on a page
the performance work already got down to five queries. **D2.1**.

### 17. Take the **pooled** connection string — **DONE**

**Do:** copy the pooled connection string (Supavisor), not the direct one.

**Where, because this step used to assume you knew:** the **Connect** button at
the top of the project page. Older dashboards put it at Settings → Database →
Connection string. It offers three, and they are told apart by host and port:

| | Shape | |
|---|---|---|
| Direct connection | `db.<ref>.supabase.co:5432` | **No** — IPv6 only, Cloud Run cannot reach it |
| Session pooler | `...pooler.supabase.com:5432` | No |
| **Transaction pooler** | `...pooler.supabase.com:`**`6543`** | **This one** |

The tell is `pooler.supabase.com` in the host and `6543` on the end.
`[YOUR-PASSWORD]` is a placeholder for the database password set when the
project was created; if it is lost, Settings → Database → Reset database
password.

**Put it in `Application/.env` as `SUPABASE_DATABASE_URL`** — not as
`DATABASE_URL`. That file is gitignored, and this is a place to keep the string,
not a setting.

**Why not `DATABASE_URL`:** that is the variable the *application* reads.
Setting it here points your local dev server at Supabase, and until step 20 that
database is empty — so the app you have been building would come up with no
courses, no transactions and no accounts. Nothing would actually be lost, and
there would be nothing on screen to tell you that.

To add it without the string appearing on screen or in your shell history:

```sh
cd Application
read -rs "?Paste the transaction pooler string: " url && \
  printf '\nSUPABASE_DATABASE_URL=%s\n' "$url" >> .env && echo "saved to .env"
```

(bash: `read -rsp "Paste the transaction pooler string: " url`.)

**Then check it, before anything depends on it:**

```sh
cd Application/backend && .venv/bin/python scripts/check_db_connection.py
```

It reads the string, names the region, confirms the pooler and the port, connects,
and runs six queries — six because psycopg starts preparing statements at the
fifth, so anything less never exercises the one setting transaction-mode pooling
requires. It prints nothing secret: the password is described, never shown.

**What it caught here, which is what this check is for.** The string looked
perfect and authentication failed. Not a wrong password — the brackets from
`[YOUR-PASSWORD]` were still around it. `[` and `]` are reserved characters in a
URL, so the generic advice ("percent-encode them") is *true* and completely
useless; the answer is to delete two characters. The checker now says that
specifically, and there is a test holding the two diagnoses in that order.

Other failures it names rather than leaves you to guess at: the direct connection
instead of the pooler, session mode instead of transaction mode, a username
truncated on paste, and `DATABASE_URL` used where `SUPABASE_DATABASE_URL` was
meant.

**Why pooled:** Cloud Run runs many independent instances, each with its own
pool. Without a pooler, three instances at five connections each is fifteen
connections for a handful of concurrent queries — and at the limit, requests are
*refused* rather than merely slow. **D2.3**.

### 18. Configure the engine for a connection that can go away — **DONE** (`5af5592`)

**Do:** `pool_pre_ping=True`, `pool_size` around 2–5, a modest `max_overflow`.

**Why:** poolers drop connections at their own discretion, Cloud Run instances
are torn down constantly, and Supabase pauses after seven idle days. Pre-ping
costs one trivial round trip per checkout and removes a whole class of
intermittent error. **D2.4**.

**Two things the string from step 17 would have broken, neither of which this
step originally mentioned.**

1. **It says `postgresql://`, with no driver.** SQLAlchemy resolves that to
   **psycopg2**, which is not installed and never will be — D1.2 chose psycopg 3.
   Pasted verbatim it gives `ModuleNotFoundError: No module named 'psycopg2'` at
   import, which says nothing about the real problem. `normalize_database_url`
   now rewrites the bare form to `postgresql+psycopg://`. An explicit
   `postgresql+psycopg2://` is left alone, because that spelling is a preference
   rather than an omission.
2. **Transaction-mode pooling and prepared statements do not mix.** psycopg
   starts using server-side prepared statements after the **fifth** execution of
   a query. Supavisor in transaction mode hands each transaction whichever
   backend connection is free, so the connection that PREPAREd is usually not the
   one asked to EXECUTE — `prepared statement ... does not exist`. It survives
   every smoke test and appears under real use. `prepare_threshold=None` for
   psycopg turns it off. **D2.6.**

**Also set:** `pool_timeout` 10s rather than SQLAlchemy's 30, so a starved
request fails visibly instead of looking like a hang; `pool_recycle` 1800, so
nothing in the path gets to close a connection out from under us first. All of it
is empty for SQLite — the in-memory test database gets a `SingletonThreadPool`,
which has no concept of overflow and would reject the argument.

**Verify:** the whole suite run against a Postgres 16 container through a
**bare** `postgresql://` URL — the exact shape the dashboard hands you — where
before this step the same URL failed on `ModuleNotFoundError`. 717 passed,
2 skipped.

### 19. Run the suite against Postgres — **DONE**

**Do:** point `TEST_DATABASE_URL` at the Supabase string and run the suite.

```sh
cd Application/backend
set -a; source ../.env; set +a
TEST_DATABASE_ALLOW_REMOTE=1 TEST_DATABASE_URL="$SUPABASE_DATABASE_URL" \
  .venv/bin/python -m pytest tests/ -q
```

**`TEST_DATABASE_ALLOW_REMOTE` is not decoration.** `_pg_engine` runs
`drop_all` before the first test and again after the last, because a run that
inherits rows from the previous one is not a clean run. That is correct against
a container and unrecoverable against a database with real data in it — and
after step 20, this database has real data in it. The suite now **refuses** a
remote host at collection unless that variable says the target is disposable.
Right now it is; from step 20 onward it is not.

**This is the real work of the port.** The suite is the only description of the
app's behaviour you have; if it has never run against Postgres you know the port
imported, not that it works.

**Expect failures, and expect most to be real:** ordering that SQLite happened to
give you without an `ORDER BY`, integer-versus-boolean comparisons, stricter type
handling. Each is a latent bug SQLite was hiding.

**Verify:** green against Postgres *and* still green against SQLite.

> **Already proven, ahead of schedule.** While doing step 5 a throwaway
> Postgres 16 container was running, so the whole suite was pointed at it:
> **683 passed and 2 skipped on the first attempt**, against 685 on SQLite. The
> two skips are tests about SQLite itself rather than about the app. No
> application code needed changing — only three pieces of test scaffolding.
> Repeated after step 18 with the real pooling settings and a bare
> `postgresql://` URL: **717 passed, 2 skipped**, against 719 on SQLite.
>
> That is a much better result than this step assumed, and it means the port is
> a known quantity rather than a risk. What remains is to repeat it against
> *Supabase* specifically, since a pooled connection over a network is not the
> same thing as a local container.

**And repeated against Supabase: 730 passed, 2 skipped, in 6m 58s.** No
failures and no application change. Worth separating what that proved from what
the container run had already proved:

- **Postgres 17.6**, not the 16 every local rehearsal used.
- **A real pooled connection**, at ~22 ms a round trip instead of a local
  socket. That is the whole reason this step exists separately — the container
  run could not have caught a pooler problem.
- **Transaction-mode pooling specifically**, which is where `prepare_threshold`
  (**D2.6**) either works or produces `prepared statement does not exist` on the
  fifth execution of a query. It works.

The two skips are the `sqlite_only` tests. Seven minutes rather than twenty
seconds is the network, not the database.

### 20. Move the data — **script written and rehearsed** (`4a4291c`)

**Do:**

```sh
cd Application/backend
sqlite3 data/app.db "VACUUM INTO '/tmp/app-copy.db'"
set -a; source ../.env; set +a
.venv/bin/python scripts/migrate_to_postgres.py --source /tmp/app-copy.db
```

**`VACUUM INTO`, not `cp`.** SQLite in WAL mode keeps recent writes in a sidecar
file, so a plain copy of the main file can be missing whatever has not been
checkpointed. `VACUUM INTO` produces a consistent single file whatever the
writer is doing. The script **refuses to open `data/app.db` at all**, comparing
resolved paths so a symlink cannot walk around it.

**Why through SQLAlchemy rather than a SQL dump:** `sqlalchemy.types.Uuid` stores
as `CHAR(32)` on SQLite and as native `uuid` on Postgres; `Boolean` is `0`/`1`
against `false`/`true`; `JSON` is text against `jsonb`. Reading and writing
through the same metadata converts each column on the way through. A dump
carries the SQLite spelling across and produces either a type error or — far
worse — valid-looking wrong data. **D1.4**.

**One thing this step did not know about, found by looking rather than by
failing.** `course_category_weights.id` is an integer autoincrement primary key
— the only one; everything else keys on a UUID the application generates. On
Postgres that is backed by a sequence, and **inserting explicit ids does not
advance it**. Without a reset the migration succeeds perfectly and the first
category weight anyone adds afterwards asks for `id = 1`, collides, and keeps
colliding forever. Demonstrated both ways against a real copy: with the reset the
next insert got `224`; without it, `duplicate key value violates unique
constraint`. The script derives the list from the models rather than naming the
table, so a future one is covered. **D1.6.**

**Rehearsed in full** against a `VACUUM INTO` copy of the real database into a
throwaway Postgres 16: 588 rows across 17 tables, every table matching. Native
`uuid`, `bool`, `dict` and `date` on the far side. The live database was
checksummed before and after and is byte-identical.

**And then done for real.** 588 rows into Supabase, every table matching by
count and by value. Checked first that `purge_expired_users` — which the app
lifespan runs on startup, and which *deletes* — would be a no-op: no user has
`deleted_at` set, so it removes nothing. That check is worth repeating before
pointing anything at a database that now holds the only copy.

### 21. Verify the move — **DONE, and folded into step 20**

**Do:** nothing separately. The script verifies before it reports success, and
exits non-zero if anything disagrees.

**Plus the check this step originally asked for, which is worth more than it
sounds.** Two instances of the real application were started side by side — one
against Supabase, one against the SQLite copy the move read from — and six
endpoints were fetched from each for all three real users, then compared:
`grades/dashboard`, `budget-summary`, `tasks`, `events`, `jobs`, `users`.

**All 18 payloads identical.** Compared by digest rather than printed, since they
carry real grades and transactions. This is a different claim from "every row
matches": it exercises the joins, the aggregations and the serialisation, so it
would catch a Postgres result ordering that SQLite happened to give for free.

**Counting rows is not enough**, which is why this was its own step and is no
longer. A count proves a table is not missing; it says nothing about whether a
boolean arrived as the right boolean or a UUID kept its bytes — and those are
precisely the failures a type conversion produces. So every table is also
**fingerprinted by value**: each row hashed across all columns, the digests
combined by XOR so neither side needs an `ORDER BY`. Floats are compared to 12
significant figures and JSON with sorted keys, so two equal values spelled
differently still compare equal.

Mutation-tested: appending one character to a single transaction description
leaves all 95 counts identical and the fingerprint reports `DIFFER`.

**The numbers to match** (as of the last check — re-count first, they move):
3 users, 27 courses, 126 grades, 95 transactions, 10 accounts, 43 spend
categories, 223 category weights. **588 rows in total.**

A migration that "looks fine" is how you discover a missing table in March.

---

## Part 3 — Deploy

### 22. Create the Google Cloud project — **DONE**

Project **`account-504419`**, with Cloud Run and Artifact Registry enabled.

**Do:** new project, attach a billing account, enable the Cloud Run and Artifact
Registry APIs.

**Note:** the card is required even for the always-free tier. It verifies
identity and is not charged inside the free limits.

### 22a. Install the `gcloud` CLI — **DONE**

**Do:** `brew install --cask google-cloud-sdk`, then `gcloud init` and
`gcloud auth login`.

**Why it is its own step:** nothing from 24 onward works without it. Step 24
needs `gcloud auth configure-docker` to let Docker push to Artifact Registry at
all, and step 27 is `gcloud run deploy`. The console can create the repository
but cannot push to it.

### 23. Create an Artifact Registry repository — **DONE**

Repository **`account`**, Docker format, in **`us-west1`**. Images are pushed as
`us-west1-docker.pkg.dev/account-504419/account/backend:<sha>`.

In the **same region** you chose at step 16 — for `aws-0-us-west-2` that is
**`us-west1`**. Both are Oregon; they are about 100 miles apart.

**Only the backend image goes here.** The frontend is a static bundle and goes
to Cloudflare Pages at step 29 (**D4.1**), so it never becomes a registry
artifact.

**The form, field by field:**

| Field | Choose | Why |
|---|---|---|
| Name | `account` | It becomes part of the image URL: `us-west1-docker.pkg.dev/<project>/account/backend` |
| Format | **Docker** | You are pushing container images, not Maven or npm packages |
| Mode | **Standard** | *Remote* is a caching proxy for an upstream registry; *Virtual* fans one endpoint out across several repos. Neither applies |
| Location type | **Region** | Multi-region costs more and buys nothing for one service |
| Region | **`us-west1`** | Cloud Run pulls the image on every cold start. Same region means a fast pull and no egress charge; a different one means both, on the path users actually wait on |
| Encryption | **Google-managed key** | Customer-managed means creating a Cloud KMS key, paying for it, and owning its rotation |
| Immutable image tags | **Off** | See below |
| Cleanup policies | **Set one** | See below — this is the one that matters |

**Immutable tags, off — but tag properly anyway.** With them on, a tag can never
be moved, so pushing `:latest` a second time fails, mid-deploy, with an error
that does not obviously mean "this is the setting you chose". Leave it off *and*
tag every image with the git SHA regardless, because **D3.1**'s rollback plan is
"redeploy the previous tag" and `:latest` alone gives you nothing to roll back
to.

**Cleanup policy, because the free tier is 0.5 GB.** Measured rather than
guessed: the backend image is 416 MB locally but **~86 MB stored**, since layers
are compressed. The number that actually matters is what a *rebuild* adds — the
Python base and the 154 MB virtualenv layer are reused, and only
`COPY . .` changes, which is **4 MB**. So code changes are nearly free and a
`requirements.txt` change is not.

Set a policy that keeps the most recent 3 versions and deletes untagged
artifacts older than 30 days. **Start it in dry-run mode** and look at what it
says it would delete before switching it to delete — a policy that removes the
image Cloud Run is currently serving takes the service down, and "keep most
recent" is what prevents that.

**Check that vulnerability scanning is off.** Artifact Analysis charges per
image scanned, and it can already be on if the Container Scanning API got
enabled with the others at step 22. It is not part of the free tier.

**Or skip the form entirely:**

```sh
gcloud artifacts repositories create account \
  --repository-format=docker \
  --location=us-west1 \
  --description="Account backend images"
```

**Verify:** `gcloud artifacts repositories list --location=us-west1` shows it.

### 24. Build for `linux/amd64` and push — **DONE** (`26e249f`, then `f6f7c32`)

```sh
cd Application/backend
gcloud auth configure-docker us-west1-docker.pkg.dev

IMG=us-west1-docker.pkg.dev/account-504419/account/backend
SHA=$(git rev-parse --short HEAD)

docker build --platform linux/amd64 --provenance=false \
  -t "${IMG}:${SHA}" -t "${IMG}:latest" .

docker push "${IMG}:${SHA}" && docker push "${IMG}:latest"
```

**Why `--platform linux/amd64`:** your Mac is Apple Silicon, so Phase 0's images
were `linux/arm64` — verified, not assumed. **Cloud Run runs `amd64`.** Without
the flag you deploy an image the platform cannot execute and find out at deploy
time. Audit finding **B8**, decision **D3.0**.

**D3.0's open question is answered: emulation is not slow.** It asked whether an
emulated amd64 build would be annoying enough to make `gcloud run deploy
--source` the better trade. Measured: **31 seconds to build, 14 seconds to
push.** It is not. Deploy the prebuilt image as D3.1 says.

**Why `--provenance=false`:** buildx otherwise wraps the image in an OCI *index*
and adds a provenance attestation, so one push produces **three** registry
versions — the index (tagged) plus two untagged children. That is tidy enough on
its own, but it collides with the cleanup policy step 23 recommends: those
children are untagged, and a "delete untagged" rule can remove manifests the
tagged index still needs. With the flag it is one plain manifest and the problem
does not exist.

**Use `${IMG}`, not `$IMG`, when a colon follows.** In zsh `$VAR:l` is a
parameter *modifier* meaning "lowercase", so `"$IMG:latest"` expands to
`...backendatest` — a real, silently-created, wrongly-named tag. Braces are not
optional here.

**Run the image before pushing it.** A successful build proves the layers
assembled, not that the thing starts:

```sh
docker run --rm --platform linux/amd64 -p 127.0.0.1:8302:8000 \
  -e DATABASE_URL="sqlite:////app/data/app.db" \
  -e JWT_SECRET="$(python3 -c 'import secrets;print(secrets.token_hex(32))')" \
  -e GOOGLE_CLIENT_ID="placeholder.apps.googleusercontent.com" \
  -e RUN_SCHEMA_ON_STARTUP=1 "${IMG}:${SHA}"
```

**This is how `GOOGLE_CLIENT_ID` was found to be mandatory.** It has no default
in `config.py`, so without it `Settings()` raises during import and the
container exits **1** before serving anything. On Cloud Run that surfaces as
"the container failed to start and listen on the port", which does not mention
the variable. It is now in step 27's table.

**Verify, all four:**

```sh
docker image inspect "${IMG}:${SHA}" --format '{{.Architecture}}/{{.Os}}'   # amd64/linux
docker exec <container> uname -m                                            # x86_64
docker manifest inspect "${IMG}:${SHA}" | grep mediaType                    # image.manifest, not index
gcloud artifacts docker images list "$IMG" --include-tags                   # one version, two tags
```

Checking the manifest is not paranoia: `.Architecture` on a *local* image is
right even when the thing pushed is an index that could resolve to something
else. Confirm what the registry holds, since that is what Cloud Run pulls.

**One number not to read too much into:** bcrypt took **448 ms** inside the
emulated container against 203 ms natively. That is Rosetta, not Cloud Run —
real amd64 hardware will be nearer the native figure.

### 25. Put the secrets in Secret Manager — **DONE**

Two secrets, `jwt-secret` and `database-url`, both referenced by the service
rather than copied into its environment. `JWT_SECRET` was rotated to a fresh
64-byte value, so the August one in the working tree is no longer live anywhere.

**Do:** `JWT_SECRET` and the Supabase connection string as secrets.

**Generate a fresh `JWT_SECRET`.** Not the one that has been in your working tree
since August. Rotating it signs everyone out once, which is correct and costs
nothing right now.

**Why not plain environment variables:** they are visible in the console, in
`gcloud run services describe` and in deploy logs. These two values are the ones
that matter most — one reads all the data, the other forges any session.
Non-secret config stays a plain variable. **D3.5**.

### 25a. Give it an identity of its own — **DONE**

**Do:** a dedicated service account, with access to the two secrets and nothing
else.

```sh
gcloud iam service-accounts create account-api \
  --display-name="Account API (Cloud Run)"

for secret in jwt-secret database-url; do
  gcloud secrets add-iam-policy-binding $secret \
    --member="serviceAccount:account-api@account-504419.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
done
```

**Why this is not optional, checked rather than assumed.** Cloud Run defaults to
the Compute Engine service account, and on this project that account holds
**`roles/editor`** — verified with `get-iam-policy`. That is the identity a
compromised container would be running as: able to read every secret in the
project, delete the registry, and create resources that cost money. Step 25 put
the two most dangerous values behind Secret Manager precisely so they were not
casually readable; running as Editor hands them back.

`account-api` has **no project-level roles at all** and two secret-scoped
grants. **D3.7.**

### 26. Run the schema creation once — **DONE**

**Do:** run `python -m app._database.schema` against Supabase once, with
`DATABASE_URL` pointing at it. It was 23 tables and 49 indexes when this step
was first run; it is **25 and 55** now, and it is idempotent, so a retried deploy
is harmless — which is what makes it safe to re-run after each table this
project has added since. The deployed service then runs with
`RUN_SCHEMA_ON_STARTUP=0`.

### 27. Deploy to Cloud Run — **DONE**

```sh
gcloud run deploy account-api \
  --image=us-west1-docker.pkg.dev/account-504419/account/backend:26e249f \
  --region=us-west1 --port=8000 \
  --service-account=account-api@account-504419.iam.gserviceaccount.com \
  --min-instances=0 --max-instances=3 --concurrency=40 \
  --cpu=1 --memory=512Mi --allow-unauthenticated \
  --set-secrets="JWT_SECRET=jwt-secret:latest,DATABASE_URL=database-url:latest" \
  --set-env-vars="GOOGLE_CLIENT_ID=...,ALLOWED_ORIGINS=https://placeholder.invalid,RUN_SCHEMA_ON_STARTUP=0,ALLOWED_SIGNUP_EMAILS=..."
```

**Service URL: `https://account-api-210502804146.us-west1.run.app`** — this is
what step 29's `VITE_API_BASE_URL` needs, with `/api` on the end.

**`--port=8000` is mandatory and not in the table below.** Cloud Run's contract
is that the container listens on whatever `$PORT` says, defaulting to **8080**.
This Dockerfile ends `CMD ["uvicorn", ..., "--port", "8000"]` — hardcoded. Without
`--port=8000` the service deploys, never passes its startup probe, and reports
that the container failed to listen. The cleaner fix is an image that honours
`$PORT`; that needs a rebuild and a push, so it is a follow-up rather than a
blocker.

**`--allow-unauthenticated` is correct here, despite how it reads.** It turns off
*Google IAM* on the endpoint, which has to be off — a browser cannot present a
Google IAM token, so with it on nobody could reach the API at all. The app's own
auth is untouched: every route still requires a JWT, and **step 11's invite gate
still decides who may create an account**. Confirmed against the live URL:
`stranger@example.com` is refused with 400.

**Pinned to the SHA, not `latest`.** `26e249f` is what rolls back to at step 36;
`latest` gives you nothing to roll back *to*.

Settings that are not the defaults, and why:

| Setting | Value | Why |
|---|---|---|
| Region | same as Supabase | step 16 |
| `min-instances` | **0** | scale to zero is the whole point; cold starts are 200 ms–2 s (**D3.2**) |
| `max-instances` | **3** | the default is **100** — a crawler or a bug could burn a month's allowance in an afternoon, and every instance holds a connection pool (**D3.3**) |
| `concurrency` | **40** | the default is 80, but FastAPI runs your synchronous routes in a 40-thread pool. At 80, forty requests queue *inside your process* where the autoscaler cannot see them, so it never starts another instance (**D3.4**) |
| `GOOGLE_CLIENT_ID` | **required** | no default in `config.py`, so `Settings()` raises during import and the container exits 1 before serving. Cloud Run reports only "failed to start and listen on the port", which does not name it. Found at step 24 by running the image |
| Secrets | from step 25 | |
| `ALLOWED_ORIGINS` | placeholder for now | corrected at step 30 |
| `RUN_SCHEMA_ON_STARTUP` | **0** | the schema was built at step 26; re-checking it costs 278 statements per cold start (**step 8**) |
| `ENABLE_DOCS` | unset | off is the default, but set nothing rather than something wrong |
| `ALLOWED_SIGNUP_EMAILS` | **the invited addresses** | unset means anyone who finds the hostname can register; startup warns while it is (**step 11**) |

### 28. Confirm the API is alive — **DONE**

**Do:** `curl https://<cloud-run-url>/health`.

**Verify:** 200 with `{"status": "ok"}`. If it is 503 the container is running but
cannot reach Supabase — which is exactly what step 6 was for.

**Result — `{"status":"ok","database":"ok"}`.** The `database: ok` half is the
one that matters: it means Cloud Run in `us-west1` reached Supabase in
`us-west2` through the transaction pooler, using a password it read from Secret
Manager as a service account with no other permissions. Every piece of Part 3 is
exercised by that one response.

| | |
|---|---|
| First request | 666 ms, including DNS and TLS |
| Warm | ~171 ms, most of it the round trip from here |
| `/docs`, `/redoc`, `/openapi.json` | 404 — step 7 holding in production |
| `stranger@example.com` on `/register` | 400, invitation only — step 11 holding |
| Preflight from a wrong origin | 400 — which is step 30 still to do |

**Not yet measured: a real cold start.** These figures are from an instance that
was already warm. **D3.2** claims 200 ms–2 s after scaling to zero, and that
number only becomes real after ~15 minutes idle. Step 38 is where it gets
checked honestly.

### 29. Deploy the frontend to Cloudflare Pages — **DONE**

**Live at `https://account-2a7.pages.dev`**, built by Pages from the GitHub repo
on push. Settings used:

| | |
|---|---|
| Root directory | `Application/frontend` |
| Build command | `npm run build` |
| Output directory | `dist` |
| `VITE_API_BASE_URL` | `https://account-api-210502804146.us-west1.run.app/api` |
| `VITE_GOOGLE_CLIENT_ID` | the same client id the backend has |
| `NODE_VERSION` | **22** |

**`NODE_VERSION` is not optional.** Vite 7.3.6 requires
`^20.19.0 || >=22.12.0`, and a too-old Node fails with an error that never
mentions the version. Now also declared in `package.json` under `engines`, so
any other CI hits it loudly rather than mysteriously.

**Verified against the deployed site:** the bundle is byte-identical to the local
build (467,735 bytes, same content hash), it contains the Cloud Run URL and no
`localhost`, and **all six security headers from step 14 are live** — which is
the first time that file has ever been exercised, since nginx locally does not
read it.

**A caution learned by getting it wrong.** `*.pages.dev` is a shared namespace:
while looking for this deployment, `account-frontend.pages.dev` and
`account-app.pages.dev` both answered 200 and belonged to strangers. A 200 on a
guessed hostname proves nothing — check the bundle for your own API URL.

### 29a. Open the console and read the CSP violations — **DONE**

**Neither predicted failure happened.** The policy written at step 14 was correct
first time: Google Sign-In renders and completes against the documented `/gsi/`
prefixes, and `connect-src` matched because both it and the bundle are generated
from the same `VITE_API_BASE_URL`. All six headers are live and were re-confirmed
on 2026-09-14:

```sh
curl -sI https://account-2a7.pages.dev | grep -i strict-transport
# strict-transport-security: max-age=31536000; includeSubDomains
```

That is the first and only test this file has ever had — nginx locally does not
read `_headers`, so nothing before this point exercised it.

**Do:** load the Pages URL with devtools open, sign in with Google, and watch the
console for `Refused to …` lines.

**Why this is its own step:** the security headers written in step 14 are the one
piece of this that **cannot be verified locally**. The local docker stack serves
through nginx, which does not read `_headers` at all, so nothing before this
point has ever had the policy applied to it. A CSP that is slightly too strict
does not warn — it silently refuses a request and the feature just does not work.

**The two most likely:**

- **Google Sign-In.** The policy uses the prefixes Google documents
  (`.../gsi/client`, `.../gsi/`, `.../gsi/style`). If the button does not render
  or the popup does nothing, widen those three to `https://accounts.google.com`
  and try again.
- **`connect-src`.** If every API call fails while `/health` answers when curled
  directly, the origin baked into `_headers` does not match the one in the
  bundle. Both come from `VITE_API_BASE_URL`, so the fix is at step 29, not here.

**Verify:** sign in, load each of the six pages, and finish with an empty console.

### 30. Point `ALLOWED_ORIGINS` at the Pages URL — **DONE**

```sh
gcloud run services update account-api --region=us-west1 \
  --update-env-vars=ALLOWED_ORIGINS=https://account-2a7.pages.dev
```

**Never a wildcard.** `https://*.pages.dev` would let any of those strangers'
sites call this API with a signed-in user's token.

**Verified from five origins:**

| Origin | | |
|---|---|---|
| `https://account-2a7.pages.dev` | **200** | the real frontend |
| `https://placeholder.invalid` | 400 | the old value, now refused |
| `https://account-frontend.pages.dev` | 400 | a stranger's Pages site |
| `http://localhost:5173` | 400 | local dev, correctly refused in production |
| `https://abc123.account-2a7.pages.dev` | 400 | a Pages preview URL — different origin by design |

`access-control-allow-origin` comes back as exactly the one hostname.

**Note for later:** every Pages preview deployment is its own origin and will
fail CORS. That is correct behaviour and confusing the first time — a preview
link looks broken when it is only unlisted.

### 31. Add the Pages origin to Google OAuth — **DONE**

**Do:** in the Google Cloud console, add the Pages URL to the client ID's
authorised JavaScript origins.

**Why now:** Google checks the calling origin. Miss this and sign-in fails with a
message that never mentions origins. Second most likely hour-loser, and it fails
the same way as step 30. **D5.3**.

### 32. Test it properly — **DONE, and it works**

**Do:** open the Pages URL on your phone **with wifi off, on mobile data.** Sign
in, load the dashboard, add a grade, reload.

**Why mobile data:** testing from your own network proves nothing about whether
the thing is actually reachable from the internet.

**It left a trace, which is the proof.** The database held 95 transactions at
migration time and holds 96 now — the row added during this test. It travelled
from a phone on mobile data, through Cloudflare Pages, to Cloud Run, to Supabase,
and the backup taken minutes later contains all 96. Nothing in that path is
theoretical any more.

---

## Part 4 — Before anyone else touches it

Do not skip this part to get friends in a day earlier.

### 33. Set up backups — **DONE** (`.github/workflows/backup.yml`)

**Do:** a scheduled nightly `pg_dump` to storage you control, off Supabase.

Runs on GitHub Actions at 09:00 UTC daily, plus `workflow_dispatch` for taking
one before anything risky. Artifacts retained 90 days. **Proven by running it:**
23 tables, 589 rows, a 22 KB gzipped artifact, downloaded and checked.

**Three details that each needed testing rather than assuming:**

1. **The SESSION pooler (5432), not the transaction pooler (6543) the app
   uses.** `pg_dump` takes a snapshot and depends on staying on one backend
   connection for the whole dump; transaction pooling may move it between
   statements, risking a dump that succeeds and is internally *inconsistent* —
   the worst kind, because it restores cleanly and is wrong. Both modes were
   tested and both produced byte-identical output, so this is a consistency
   argument rather than an observed failure; the safer mode costs nothing.
2. **`--schema=public`.** Without it the dump also carries Supabase's own
   `auth`, `storage` and `realtime` schemas: **58** `CREATE TABLE` instead of 23,
   none of it restorable into a fresh project because the platform manages it.
3. **`pg_dump` runs inside `postgres:17-alpine`.** The server is 17.6 and
   GitHub's runner image ships client 16, which refuses a newer server outright.

**It refuses to archive a dump it does not believe:** under 2 KB, fewer than 20
tables, or zero data rows fails the run. A dump that connected, found nothing and
exited 0 would otherwise be archived nightly, look healthy in the logs, and be
discovered empty on the one day it mattered.

**Two things to decide later, flagged rather than silently chosen.** The dump is
**not encrypted** — it holds every user's financial data and their bcrypt
password hashes, in a private repository's artifact storage. Encrypting it means
a passphrase whose loss makes every backup unreadable, which for this threat
model is a worse failure than the one it prevents. And **90 days is not
forever**: if you want a copy that outlives that, the dump needs a home you own,
such as a Cloud Storage bucket.

**This is not optional on Supabase free.** There are **no automated backups** on
that plan and point-in-time recovery is a $100/month feature. Skipping this means
the consequence of any mistake is "you lose everything" rather than "you lose a
day". **D2.5** — and D2.0's choice of Supabase over Neon is only a good decision
if this step actually happens.

### 34. Restore one — **DONE, and it caught a real failure**

**Do:** restore last night's dump into a second Supabase project — the free plan
allows two — and open the real app against it.

```sh
cd Application/backend
gh run download --repo fawwaz9/Account --name account-db-YYYY-MM-DD --dir /tmp
set -a; source ../.env; set +a          # sets the production guard
./scripts/restore_backup.sh /tmp/account-YYYY-MM-DD.sql.gz "<second project, port 5432>"
```

**An unrestored backup is a belief, not a backup.** This is the step everyone
skips and the only one that proves the others — and here it earned its place on
the first attempt.

**The backup did not restore.** `psql` aborted on line 26 with
`ERROR: schema "public" already exists`, and under `--single-transaction` that
rolls back everything. The dump is perfectly good: `pg_dump` emits
`CREATE SCHEMA public` and a fresh Supabase project already has one. Nothing
about step 33 hinted at it — the artifact is the right size, the right table
count, the right row count. **It would have been discovered in an emergency.**

**The fix is `DROP SCHEMA IF EXISTS public CASCADE` and nothing else.** Dropping
*and recreating* fails identically, because then the dump's own `CREATE SCHEMA`
collides with the one you just made. Let the dump create it.

**Verified three ways:**

1. The restored database matches **the dump** exactly, table for table — 589
   rows across 17 tables, every value fingerprinted.
2. Against **live** it differs by one transaction, and that is correct: the row
   was written after the backup was taken at 02:32. A backup is a snapshot, and
   this is what proves it was a real one rather than a live query.
3. The **real application** was started against the restored database and every
   endpoint answered 200 for all three users — dashboard, budget summary, tasks,
   events, jobs.

**`scripts/restore_backup.sh` now holds the procedure**, because the discovery
only helps if it survives. It refuses to run against the production project
(comparing Supabase project references, not whole strings), refuses to run at
all if `SUPABASE_DATABASE_URL` is unset so the guard cannot be checked, warns if
given the transaction pooler instead of the session pooler, runs the Postgres 17
client so a v16 client cannot refuse the 17.6 server, and verifies row counts
against the dump before reporting success. Guard exits verified: 3 for a
production target, 3 for an unusable guard, 2 for a missing dump.

### 35. Put a monitor on `/health` — **DONE**

**Do:** a free external monitor — UptimeRobot, Better Stack — every five minutes.

**Two monitors, and no more:**

| | |
|---|---|
| `https://account-2a7.pages.dev/` | Pages is serving the bundle |
| `https://account-api-…/health` | the whole system — it queries Supabase |

**Refuse the suggested extras.** UptimeRobot offers to monitor common paths
(`/login`, `/cart`, `/pricing`, `/wp-admin`, `/blog`, …) and eight were accepted
here. **Every one of them returned an identical 200** — same 466 bytes, same
`<title>App</title>` — including a nonsense path invented to test it. That is
Cloudflare Pages' SPA fallback working correctly for a React Router app: any
unmatched path gets `index.html`.

So those monitors check one static file, nine times. **They would all report UP
with the API dead, Supabase deleted and every user locked out.** The harm is not
the wasted quota, it is that "9 of 10 monitors UP" reads like broad coverage
when it is one file.

**`/health` is the only endpoint that proves anything**, because it queries the
database — so it catches a paused project, rotated credentials, or an exhausted
pool, none of which a static page can see.

**It caught something within minutes of being enabled:**

```
20:20:23  DOWN  405 Method Not Allowed
20:25:28  UP    200 OK
```

`@app.get` registers GET alone — a plain Starlette route adds HEAD for you,
FastAPI's does not — and UptimeRobot sends **HEAD** by default. A healthy
service was being reported as down. `/health` now answers GET and HEAD, and
still refuses anything that writes.

**Poll as often as you like.** That caution only ever applied to Neon, where
polling kept the compute awake and drained the budget. Supabase has no compute
budget, and the polling doubles as insurance against the seven-day idle pause.
**D6.2**.

**Why five minutes is fine now:** it would not have been on Neon, where polling
kept the database awake and burned the compute budget. Supabase is always on with
no compute budget, so poll freely. Side benefit: regular polling counts as
activity, so the seven-day pause will never trigger. **D6.2**.

### 36. Write down how to roll it back — **DONE** (`Ideas/ROLLBACK.md`)

**It found a real fault while being tested.** Running the rollback command
against the revision already serving looked like a no-op and was not:
`--to-revisions` **pins** the service, and the next `gcloud run deploy` then
reported success and changed nothing. Fixed with `--to-latest`, and the service
now reports `latestRevision: true`. ROLLBACK.md leads with that warning.

**Do:** one short note — the previous image tag, the command to redeploy it, and
where the backups are.

**Why:** you will need this while something is broken and you are stressed, which
is the worst time to work it out. Keep it next to this file.

---

## Part 5 — Let people in

### 37. Add yourself and two friends — **DONE**

`ALLOWED_SIGNUP_EMAILS` holds **four** addresses as of revision
`account-api-00006-rtl` — the original three plus `david.ibie23@gmail.com`. The
second person has signed in and their accounts seeded, which is the first time
any of this ran for someone who did not build it.

**Do:** put three addresses in `ALLOWED_SIGNUP_EMAILS`. Not twenty.

**Adding one later** is `--update-env-vars`, which replaces that variable whole
rather than appending to it — so read the current value first and pass every
address back, or the people already invited quietly stop being able to create an
account. Existing accounts keep working either way: the list gates creation, not
sign-in.

```sh
gcloud run services describe account-api --region=us-west1 \
  --format="value(spec.template.spec.containers[0].env)" | tr ';' '\n' | grep ALLOWED_SIGNUP
gcloud run services update account-api --region=us-west1 \
  --update-env-vars='^##^ALLOWED_SIGNUP_EMAILS=<every address, including the new one>'
```

Then confirm `spec.traffic[].latestRevision` is still `True` — a pinned service
takes the new revision and serves the old one, so the invite appears to have
been ignored.

### 38. Watch for a week — **DONE**

Started 2026-09-14, read again 2026-09-28. **Nothing in it argued for changing
anything.** Cloud Run logged **16,202 entries in the trailing seven days** — that
is log lines rather than requests, so it over-counts, and even read as requests
it is about 69k a month against a 2 million free allowance. The service has taken
four more deploys since (`93c9d73`, `394cb7c`, `da6ac93`, `8f73dca`) and traffic
is still on `LATEST`.

The commands are kept because they are what you re-run, not because the watch is
still open:

**Three numbers, and the commands that give them:**

```sh
# requests, against 2M/month free
gcloud run services describe account-api --region=us-west1 \
  --format="value(status.traffic[].revisionName)"
gcloud logging read \
  'resource.type=cloud_run_revision AND resource.labels.service_name=account-api' \
  --freshness=7d --format="value(timestamp)" | wc -l

# failed sign-ins: auth.* at WARNING
gcloud run services logs read account-api --region=us-west1 --limit=200 | grep -i 'auth\.'
```

Database size is on the Supabase dashboard. **500 MB is the cap and 588 rows is
the current load**, so size is not the number to worry about — it would take
years of this to matter. Requests are the same story at three users. The one
number that is genuinely unknown is the third:

- **Cold-start latency has still never been measured.** D3.2 claims 200 ms–2 s
  and that figure is an estimate, not an observation. Every timing so far was
  taken against a warm container. To measure it honestly: leave it 15 minutes
  untouched, then `curl -w '%{time_total}\n' -o /dev/null -s <url>/health`.
  UptimeRobot polling every 5 minutes may be keeping it warm, which would make
  the number unobtainable while monitoring is on — and is worth knowing either
  way, because it means your friends rarely pay for a cold start.

**What the first days already showed:** the second person signed in, their six
accounts seeded on first read, and they have entered nothing since. The seeding
path ran for someone who did not build the app, which is the only part of this
that had never been exercised by anyone but its author.

**Why three people first:** everything in this plan is reasoning, not
measurement. A week of real use tells you which parts were wrong while the blast
radius is three people who will forgive you.

### 39. Invite the rest

Add the remaining addresses to `ALLOWED_SIGNUP_EMAILS`:

```sh
gcloud run services update account-api --region=us-west1 \
  --update-env-vars=^##^ALLOWED_SIGNUP_EMAILS=a@x.com,b@y.com,c@z.com
```

**The `^##^` is not decoration.** `--update-env-vars` splits on commas, so a
value that contains commas needs a different delimiter declared up front or
gcloud reads each address as a separate variable.

**Before you do:** fix step 12a / D5.5 first. Twenty people behind one shared
rate-limit budget is a different proposition from three — one person hitting the
login limit would lock out the other nineteen.

---

## Housekeeping — prune Docker after every deployment

**Run this at the end of every deploy**, not when the disk complains. It is the
last step of the loop in `shipping.md`, and it is here because the reasoning is
longer than the step.

### On the dev machine — do this every time

```sh
docker builder prune -f      # the one that actually reclaims
docker image prune -f        # dangling images, the untagged <none> rows
docker system df             # confirm it went
```

**Measured 2026-09-30:** 10 images at 1.0 GB, 45 build-cache entries at 1.3 GB,
about **595 MB reclaimable that minute** — and this is a machine that had already
been cleaned once. Before that clean it had reached **7.6 GB, of which 5.5 GB was
build cache nothing ever clears on its own.** `docker builder prune` reclaimed
5.1 GB in one command.

**This costs no rollback path.** Deleting a local image tag does not touch the
registry copy — the registry is the rollback source, and it is untouched by
everything in this block. Local dev data is also never at risk: `docker-compose`
bind-mounts `./backend/data`, so the SQLite file lives on disk rather than in a
volume.

### In the registry — leave it alone

**Do not prune Artifact Registry as part of this.** Two reasons, and the first is
the one that decides it:

- **Those tags are the rollback path.** `ROLLBACK.md` requires keeping at least
  two, and never relying on `latest`, which by definition points at whatever just
  broke. A registry tag deleted to save space is a rollback you cannot perform
  during an outage.
- **There is nothing to save.** All **15 tags occupy 0.22 GB** across 76 blobs,
  because every image shares the same base layers — so fifteen images cost
  barely more than one. The free tier is 0.5 GB. Measured 2026-09-30:

  ```sh
  gcloud artifacts files list --repository=account --location=us-west1 \
    --format=json | python3 -c \
    "import json,sys; r=json.load(sys.stdin); \
     print(sum(int(x['sizeBytes']) for x in r)/1073741824, 'GB in', len(r), 'blobs')"
  ```

**If the registry ever does need pruning** — it will not for a long while — keep
the newest several and never fewer than two, do it as its own deliberate act, and
update `ROLLBACK.md`'s tag list in the same commit. Never in the same motion as
the local prune: one is free and reversible, the other is neither.

> **`docker system df` is how you check, not `docker ps`.** And note that
> **`timeout` does not exist on macOS** — a `cmd || echo DOWN` wrapped in
> `timeout` once reported the local stack down when the `||` had actually fired
> on command-not-found. If a health check here reads as a failure, confirm the
> command exists before believing it.

---

## Reference — audit findings, and where each is handled

| | Finding | Step |
|---|---|---|
| B1 | Docker never run end to end | **Done** — Phase 0 |
| B2 | `ALLOWED_ORIGINS` hardcoded and wrong | **Done** — step 9; step 30 sets the real value |
| B3 | `/docs` and `/openapi.json` public | **Done** — step 7 |
| B4 | No TLS | Free from Cloud Run and Pages |
| B5 | `/register` open to anyone | **Done** — step 11, both doors |
| B6 | No health endpoint | **Done** — step 6 |
| B7 | Two `.env` files with duplicate secrets | **Done** — step 10 |
| B8 | Images build arm64; Cloud Run needs amd64 | 24 |
| S1 | No security headers | **Done** — step 14; confirm on the live site at 29a |
| S2 | No backup discipline | 33, 34 |
| S3 | No React error boundary | **Done** — step 13 |
| S4 | `/register` unthrottled | **Done** — step 12; **step 12a** says what it means behind a proxy |
| S5 | No pagination on 27 list endpoints | **Deferred** — fine at this size, revisit if data grows |
| S6 | Migrations additive-only, unversioned | **Deferred** — see D1.3; step 8 strengthens the case for Alembic |
| S7 | README's "Still open" table is stale | **Deferred** — four of eight rows were fixed by merged PRs |
| S8 | Throttle state is per-process | **Accepted** — D3.6, bounded by `max-instances` 3. See also **12a**: the key itself is wrong behind a proxy |
| S9 | Local venv stale vs `requirements.txt` | **Done** — step 4; a clean venv from the file alone is 42 packages and 669 green |
| S10 | Pydantic v3 deprecation | **Deferred** — `app/Tasks/schemas/task.py:77` |
| S11 | Hard user deletion live | **Done** — step 1 |

## Reference — capacity

| Limit | Ceiling | Users |
|---|---|---|
| Cloud Run requests | 2M/month | **~1,100** at ~60 requests per user per day |
| Supabase storage | 500 MB | ~1,900 at ~260 KB per active user |
| Supabase compute | none — always on | not a limit |

Twenty users is comfortable with a great deal of room. Requests bind first.

## Deliberately not doing

- **Pagination** (S5) — 95 transactions does not need it.
- **Alembic** (S6) — but step 8 makes the case stronger than when D1.3 was
  written. Revisit after the first deploy.
- **A shared throttle store** (S8) — adds a dependency and an outage path for a
  service whose absence would block all sign-ins.
- **Moving the JWT out of `sessionStorage`** — an httpOnly cookie introduces a
  CSRF requirement, and there is no XSS vector today.

## History

This plan was Oracle Cloud + SQLite, then Cloud Run + Neon, before arriving here.
Both changes are recorded in `plan-a-decisions.md` rather than quietly edited
away — D2.0 in particular, where the question "why can't we use Supabase?"
reversed a decision and dissolved an unrelated problem downstream. How a plan
changed is usually more instructive than what it changed to.

**Option D — self-hosting on a cheap mini PC — is deferred, not rejected.** It is
the only shape that keeps SQLite, removes every free-tier ceiling, and has no
cold starts. The trigger for revisiting is any of the three numbers in step 38
approaching its limit. Everything you would need is kept in the appendix below
rather than discarded.

---

# Appendix — Option D, if you revisit self-hosting

Kept because this decision is deferred rather than closed, and because the
research behind it does not survive anywhere else.

Worth separating from the rented-VM path that the requirements ruled out. Buying
hardware is a different proposition, and for *this* app it has one decisive
advantage: **it is the only option that keeps SQLite**, so it skips the Postgres
port entirely.

**What to buy.** A **used mini PC** — Dell OptiPlex Micro, HP EliteDesk Mini,
Lenovo ThinkCentre Tiny — is the best value. Roughly £50–100 second-hand, x86 so
the existing images run without an architecture rebuild, usually 8–16 GB of RAM
and an SSD already fitted, and about 10–15 W at idle. A **Raspberry Pi 5** works
too and draws less (~5 W), but once a case, PSU and SSD are added it typically
costs *more* than the used mini PC and is slower. An **old laptop you already
own** is free and has a built-in UPS in its battery.

**What to look for second-hand.** The Lenovo ThinkCentre Tiny / Dell OptiPlex
Micro / HP EliteDesk Mini families are all ex-corporate and all fine. Ranked by
what actually matters for a box that runs continuously:

| Priority | What | Why |
|---|---|---|
| 1 | **Power adapter included** | Proprietary barrel connectors. Sourcing one afterwards costs a third of the machine. |
| 2 | **No BIOS supervisor password** | Ex-lease machines sometimes ship locked. You need BIOS access to set *power on after AC loss*, which Phase 2 depends on. Ask explicitly. |
| 3 | **NVMe SSD**, 256 GB or more | Not a spinning disk, and not an SD card. Most of these have an M.2 slot *and* a 2.5in bay, so OS and data can live apart. |
| 4 | **16 GB RAM**, or 8 GB with a free slot | 8 GB runs this app several times over; 16 GB is what makes the box comfortable for future projects. Usually two SODIMM slots. |
| 5 | **A T-suffix CPU** — i5-8500T, i5-9500T | The 35 W variants rather than 65 W. Most Tiny/Micro/Mini units ship with them, and it is the difference that matters over a year of uptime. |
| 6 | 9th or 10th gen over 8th, if close in price | Marginally better efficiency. Not worth paying much for. |

**Do not pay extra for an i7.** An i5-8500T is already enormous overkill for a
Python web server with twenty users; the money is better spent on RAM or the
SSD. Expect roughly 7–12 W at idle, so about £8–15 a year in electricity.

> **Do not put the database on an SD card.** SQLite in WAL mode writes
> constantly, and SD cards fail from write cycles — usually silently, and
> usually as corruption rather than a clean death. Use an SSD, internal or USB.

**Getting it on the internet.** Two ways, and they differ on cost and on whether
the invite gate needs code:

| | Cloudflare Tunnel | Tailscale Funnel |
|---|---|---|
| Hostname | `app.yourdomain.com` | `box.tailnet.ts.net`, given to you |
| Domain needed | **Yes** — named tunnels require a zone on Cloudflare, about £8/yr at their at-cost registrar | **No** |
| TLS | included | included, real Let's Encrypt |
| Open ports | none | none |
| Invite gate | **Cloudflare Access, free to 50 users — no code** | in the app, `ALLOWED_SIGNUP_EMAILS`, ~15 lines |
| Caveats | quick `trycloudflare.com` tunnels are *not* a substitute — the URL changes on every restart and they are documented as non-production | ports 443/8443/10000 only, and non-configurable bandwidth limits |

Neither needs port forwarding, a static IP, or anything touched on your router.

**Software.** Ubuntu Server LTS or Debian, headless. Docker and Compose. The
tunnel client. `unattended-upgrades` so security patches land without you.
SSH by key only, password auth off. Set the BIOS to power on after a power cut,
and the existing `restart: unless-stopped` in `docker-compose.yml` brings the
stack back by itself.

**Backups — the part self-hosting makes genuinely yours.** Nightly
`VACUUM INTO` to a timestamped file, then **off the machine**: `rclone` to
Backblaze B2 (10 GB free) or similar. A backup sitting on the same disk as the
database is not a backup. Restore one and open the app against it before
believing any of it.

**Watching it.** A free external monitor — UptimeRobot, Better Stack — hitting
`/health` every few minutes, so you find out it is down before the twenty people
do. Self-hosted monitoring on the same box cannot tell you the box is off.

**What it really costs.** £50–100 once, plus about £3–6 a year of electricity,
plus £8/yr for a domain if you take the Cloudflare route. And your time: you are
now the sysadmin, your home internet is the uptime, and a power cut is an
outage.

**What it buys.** No Postgres port. No cold starts, ever. No card anywhere. The
invite gate free and codeless if you take the Cloudflare route. And the app runs
exactly as it was built, which is not nothing after 619 tests written against
that shape.

## The steps would differ from Part 3 onward

Parts 1, 4 and 5 above apply unchanged. What changes:

- **Part 2 disappears entirely.** No Postgres port: SQLite stays, so steps 3–5
  and 16–21 are unnecessary. This is the single biggest argument for Option D.
- **Part 3 becomes:** install Ubuntu Server, Docker, and a reverse proxy; run the
  existing compose stack; put a tunnel in front.
- **Step 8 stops mattering** — the 278 startup statements hit a local file again,
  which costs nothing, and there are no cold starts to pay them on.
- **Step 33 changes** from `pg_dump` to `VACUUM INTO`, still copied off the
  machine.
- **The invite gate (step 11) becomes optional** if you use Cloudflare Access,
  because a single origin makes Access viable again.

## And the multi-project groundwork

If the box is ever to host more than this app, four decisions are cheap now and
annoying later: a reverse proxy (Traefik) owning ports 80 and 443 rather than any
one app; one shared Docker network; a predictable `/srv/<project>/` layout so one
backup script covers everything; and `mem_limit` on every service so a runaway
project starves itself rather than the others.
